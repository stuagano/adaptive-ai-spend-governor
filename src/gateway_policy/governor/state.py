from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, cast


@dataclass
class GovernorRuntimeState:
    governor_name: str
    active_stage: str | None
    last_applied_at: datetime | None
    baseline_limits_json: str
    block_proxy_traffic: bool
    emergency_allowlist_json: str
    baseline_gateway_json: str = "{}"


class StateStore:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_schema(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS governor_state (
                    governor_name TEXT PRIMARY KEY,
                    active_stage TEXT,
                    last_applied_at TEXT,
                    baseline_limits_json TEXT NOT NULL,
                    block_proxy_traffic INTEGER NOT NULL DEFAULT 0,
                    emergency_allowlist_json TEXT NOT NULL DEFAULT '[]',
                    baseline_gateway_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    policy_name TEXT NOT NULL,
                    identity TEXT NOT NULL,
                    project TEXT,
                    max_usd TEXT NOT NULL,
                    max_total_tokens INTEGER NOT NULL,
                    spent_usd TEXT NOT NULL,
                    spent_tokens INTEGER NOT NULL,
                    reserved_usd TEXT NOT NULL DEFAULT '0',
                    reserved_tokens INTEGER NOT NULL DEFAULT 0,
                    expires_at TEXT NOT NULL,
                    closed INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS reservations (
                    reservation_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    request_id TEXT NOT NULL,
                    reserved_usd TEXT NOT NULL,
                    reserved_tokens INTEGER NOT NULL,
                    finalized INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS idempotency (
                    key TEXT PRIMARY KEY,
                    response_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(governor_state)").fetchall()
            }
            if "baseline_gateway_json" not in columns:
                connection.execute(
                    "ALTER TABLE governor_state "
                    "ADD COLUMN baseline_gateway_json TEXT NOT NULL DEFAULT '{}'"
                )

    def get_governor_state(self, governor_name: str) -> GovernorRuntimeState | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM governor_state WHERE governor_name = ?",
                (governor_name,),
            ).fetchone()
        if row is None:
            return None
        return GovernorRuntimeState(
            governor_name=row["governor_name"],
            active_stage=row["active_stage"],
            last_applied_at=(
                datetime.fromisoformat(row["last_applied_at"])
                if row["last_applied_at"]
                else None
            ),
            baseline_limits_json=row["baseline_limits_json"],
            block_proxy_traffic=bool(row["block_proxy_traffic"]),
            emergency_allowlist_json=row["emergency_allowlist_json"],
            baseline_gateway_json=row["baseline_gateway_json"],
        )

    def upsert_governor_state(self, state: GovernorRuntimeState) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO governor_state (
                    governor_name, active_stage, last_applied_at,
                    baseline_limits_json, block_proxy_traffic, emergency_allowlist_json,
                    baseline_gateway_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(governor_name) DO UPDATE SET
                    active_stage = excluded.active_stage,
                    last_applied_at = excluded.last_applied_at,
                    baseline_limits_json = excluded.baseline_limits_json,
                    block_proxy_traffic = excluded.block_proxy_traffic,
                    emergency_allowlist_json = excluded.emergency_allowlist_json,
                    baseline_gateway_json = excluded.baseline_gateway_json
                """,
                (
                    state.governor_name,
                    state.active_stage,
                    state.last_applied_at.isoformat() if state.last_applied_at else None,
                    state.baseline_limits_json,
                    int(state.block_proxy_traffic),
                    state.emergency_allowlist_json,
                    state.baseline_gateway_json,
                ),
            )

    def list_audit(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT created_at, event_type, payload_json
                FROM audit_log
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            {
                "created_at": row["created_at"],
                "event_type": row["event_type"],
                "payload": json.loads(row["payload_json"]),
            }
            for row in rows
        ]

    def append_audit(self, event_type: str, payload: dict[str, Any]) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO audit_log (created_at, event_type, payload_json) VALUES (?, ?, ?)",
                (datetime.now(tz=UTC).isoformat(), event_type, json.dumps(payload)),
            )

    def create_session(
        self,
        session_id: str,
        policy_name: str,
        identity: str,
        project: str | None,
        max_usd: Decimal,
        max_total_tokens: int,
        expires_at: datetime,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO sessions (
                    session_id, policy_name, identity, project,
                    max_usd, max_total_tokens, spent_usd, spent_tokens,
                    reserved_usd, reserved_tokens, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, '0', 0, '0', 0, ?)
                """,
                (
                    session_id,
                    policy_name,
                    identity,
                    project,
                    str(max_usd),
                    max_total_tokens,
                    expires_at.isoformat(),
                ),
            )

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        return dict(row) if row else None

    def close_session(self, session_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE sessions SET closed = 1 WHERE session_id = ?",
                (session_id,),
            )

    def reserve_budget(
        self,
        session_id: str,
        reservation_id: str,
        request_id: str,
        reserved_usd: Decimal,
        reserved_tokens: int,
    ) -> bool:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT * FROM sessions
                WHERE session_id = ? AND closed = 0 AND expires_at > ?
                """,
                (session_id, datetime.now(tz=UTC).isoformat()),
            ).fetchone()
            if row is None:
                connection.execute("ROLLBACK")
                return False
            spent_usd = Decimal(row["spent_usd"]) + Decimal(row["reserved_usd"])
            spent_tokens = int(row["spent_tokens"]) + int(row["reserved_tokens"])
            if spent_usd + reserved_usd > Decimal(row["max_usd"]):
                connection.execute("ROLLBACK")
                return False
            if spent_tokens + reserved_tokens > int(row["max_total_tokens"]):
                connection.execute("ROLLBACK")
                return False
            connection.execute(
                """
                UPDATE sessions
                SET reserved_usd = CAST(CAST(reserved_usd AS REAL) + ? AS TEXT),
                    reserved_tokens = reserved_tokens + ?
                WHERE session_id = ?
                """,
                (float(reserved_usd), reserved_tokens, session_id),
            )
            connection.execute(
                """
                INSERT INTO reservations (
                    reservation_id, session_id, request_id,
                    reserved_usd, reserved_tokens, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    reservation_id,
                    session_id,
                    request_id,
                    str(reserved_usd),
                    reserved_tokens,
                    datetime.now(tz=UTC).isoformat(),
                ),
            )
            connection.commit()
            return True

    def finalize_reservation(
        self,
        reservation_id: str,
        actual_usd: Decimal,
        actual_tokens: int,
    ) -> None:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM reservations WHERE reservation_id = ?",
                (reservation_id,),
            ).fetchone()
            if row is None or row["finalized"]:
                connection.execute("ROLLBACK")
                return
            session_id = row["session_id"]
            reserved_usd = Decimal(row["reserved_usd"])
            reserved_tokens = int(row["reserved_tokens"])
            connection.execute(
                """
                UPDATE sessions
                SET spent_usd = CAST(CAST(spent_usd AS REAL) + ? AS TEXT),
                    spent_tokens = spent_tokens + ?,
                    reserved_usd = CAST(
                        MAX(CAST(reserved_usd AS REAL) - ?, 0) AS TEXT
                    ),
                    reserved_tokens = MAX(reserved_tokens - ?, 0)
                WHERE session_id = ?
                """,
                (
                    float(actual_usd),
                    actual_tokens,
                    float(reserved_usd),
                    reserved_tokens,
                    session_id,
                ),
            )
            connection.execute(
                "UPDATE reservations SET finalized = 1 WHERE reservation_id = ?",
                (reservation_id,),
            )
            connection.commit()

    def get_idempotent_response(self, key: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT response_json FROM idempotency WHERE key = ?",
                (key,),
            ).fetchone()
        if row is None:
            return None
        return cast(dict[str, Any], json.loads(row["response_json"]))

    def store_idempotent_response(self, key: str, response: dict[str, Any]) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO idempotency (key, response_json, created_at)
                VALUES (?, ?, ?)
                """,
                (key, json.dumps(response), datetime.now(tz=UTC).isoformat()),
            )

    def is_proxy_blocked(self, identity: str | None = None) -> bool:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT block_proxy_traffic, emergency_allowlist_json
                FROM governor_state
                WHERE block_proxy_traffic = 1
                """
            ).fetchall()
        if not rows:
            return False
        if identity is None:
            return True
        for row in rows:
            allowlist = json.loads(row["emergency_allowlist_json"])
            if isinstance(allowlist, list) and identity in allowlist:
                return False
        return True
