from __future__ import annotations

import json
import os
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Protocol, cast

import psycopg
from databricks.sdk import WorkspaceClient

from gateway_policy.governor.state import GovernorRuntimeState

SCHEMA = "gateway_governor"


class GovernorStateStore(Protocol):
    def get_governor_state(self, governor_name: str) -> GovernorRuntimeState | None: ...

    def upsert_governor_state(self, state: GovernorRuntimeState) -> None: ...

    def append_audit(self, event_type: str, payload: dict[str, Any]) -> None: ...

    def list_audit(self, limit: int = 100) -> list[dict[str, Any]]: ...


class LakebaseStateStore:
    """Transactional governor state backed by Lakebase Postgres Autoscaling."""

    def __init__(self, connection_factory: Callable[[], Any]) -> None:
        self._connection_factory = connection_factory
        self._init_schema()

    @classmethod
    def from_databricks_app_env(
        cls,
        workspace_client: WorkspaceClient | None = None,
    ) -> LakebaseStateStore:
        workspace = workspace_client or WorkspaceClient()

        def connect() -> Any:
            endpoint_name = os.environ["LAKEBASE_ENDPOINT"]
            token = workspace.postgres.generate_database_credential(
                endpoint=endpoint_name
            ).token
            host = os.environ.get("PGHOST")
            if host is None:
                endpoint = workspace.postgres.get_endpoint(name=endpoint_name)
                if (
                    endpoint.status is None
                    or endpoint.status.hosts is None
                    or endpoint.status.hosts.host is None
                ):
                    raise RuntimeError("Lakebase endpoint did not return a database host")
                host = endpoint.status.hosts.host
            user = os.environ.get("PGUSER")
            if user is None:
                user = workspace.current_user.me().user_name
            return psycopg.connect(
                host=host,
                port=int(os.environ.get("PGPORT", "5432")),
                dbname=os.environ.get("PGDATABASE", "databricks_postgres"),
                user=user,
                password=token,
                sslmode=os.environ.get("PGSSLMODE", "require"),
            )

        return cls(connect)

    def _init_schema(self) -> None:
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
                cursor.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {SCHEMA}.governor_state (
                        governor_name TEXT PRIMARY KEY,
                        active_stage TEXT,
                        last_applied_at TIMESTAMPTZ,
                        baseline_limits_json JSONB NOT NULL,
                        baseline_gateway_json JSONB NOT NULL,
                        block_proxy_traffic BOOLEAN NOT NULL DEFAULT FALSE,
                        emergency_allowlist_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cursor.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {SCHEMA}.audit_log (
                        id BIGSERIAL PRIMARY KEY,
                        created_at TIMESTAMPTZ NOT NULL,
                        event_type TEXT NOT NULL,
                        payload_json JSONB NOT NULL
                    )
                    """
                )
                cursor.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {SCHEMA}.sessions (
                        session_id TEXT PRIMARY KEY,
                        policy_name TEXT NOT NULL,
                        identity TEXT NOT NULL,
                        project TEXT,
                        max_usd NUMERIC(38, 18) NOT NULL,
                        max_total_tokens BIGINT NOT NULL,
                        spent_usd NUMERIC(38, 18) NOT NULL DEFAULT 0,
                        spent_tokens BIGINT NOT NULL DEFAULT 0,
                        reserved_usd NUMERIC(38, 18) NOT NULL DEFAULT 0,
                        reserved_tokens BIGINT NOT NULL DEFAULT 0,
                        expires_at TIMESTAMPTZ NOT NULL,
                        closed BOOLEAN NOT NULL DEFAULT FALSE,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cursor.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {SCHEMA}.reservations (
                        reservation_id TEXT PRIMARY KEY,
                        session_id TEXT NOT NULL REFERENCES {SCHEMA}.sessions(session_id),
                        request_id TEXT NOT NULL,
                        reserved_usd NUMERIC(38, 18) NOT NULL,
                        reserved_tokens BIGINT NOT NULL,
                        finalized BOOLEAN NOT NULL DEFAULT FALSE,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        UNIQUE (session_id, request_id)
                    )
                    """
                )
                cursor.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {SCHEMA}.idempotency (
                        key TEXT PRIMARY KEY,
                        response_json JSONB NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
            connection.commit()

    def get_governor_state(self, governor_name: str) -> GovernorRuntimeState | None:
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT governor_name, active_stage, last_applied_at,
                           baseline_limits_json, baseline_gateway_json,
                           block_proxy_traffic, emergency_allowlist_json
                    FROM {SCHEMA}.governor_state
                    WHERE governor_name = %s
                    """,
                    (governor_name,),
                )
                row = cursor.fetchone()
        if row is None:
            return None
        return GovernorRuntimeState(
            governor_name=str(row[0]),
            active_stage=cast(str | None, row[1]),
            last_applied_at=cast(datetime | None, row[2]),
            baseline_limits_json=json.dumps(row[3]),
            baseline_gateway_json=json.dumps(row[4]),
            block_proxy_traffic=bool(row[5]),
            emergency_allowlist_json=json.dumps(row[6]),
        )

    def upsert_governor_state(self, state: GovernorRuntimeState) -> None:
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    INSERT INTO {SCHEMA}.governor_state (
                        governor_name, active_stage, last_applied_at,
                        baseline_limits_json, baseline_gateway_json,
                        block_proxy_traffic, emergency_allowlist_json, updated_at
                    ) VALUES (
                        %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s::jsonb, NOW()
                    )
                    ON CONFLICT (governor_name) DO UPDATE SET
                        active_stage = EXCLUDED.active_stage,
                        last_applied_at = EXCLUDED.last_applied_at,
                        baseline_limits_json = EXCLUDED.baseline_limits_json,
                        baseline_gateway_json = EXCLUDED.baseline_gateway_json,
                        block_proxy_traffic = EXCLUDED.block_proxy_traffic,
                        emergency_allowlist_json = EXCLUDED.emergency_allowlist_json,
                        updated_at = NOW()
                    """,
                    (
                        state.governor_name,
                        state.active_stage,
                        state.last_applied_at,
                        state.baseline_limits_json,
                        state.baseline_gateway_json,
                        state.block_proxy_traffic,
                        state.emergency_allowlist_json,
                    ),
                )
            connection.commit()

    def append_audit(self, event_type: str, payload: dict[str, Any]) -> None:
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    INSERT INTO {SCHEMA}.audit_log (
                        created_at, event_type, payload_json
                    ) VALUES (%s, %s, %s::jsonb)
                    """,
                    (
                        datetime.now(tz=UTC),
                        event_type,
                        json.dumps(payload),
                    ),
                )
            connection.commit()

    def list_audit(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT created_at, event_type, payload_json
                    FROM {SCHEMA}.audit_log
                    ORDER BY id DESC
                    LIMIT %s
                    """,
                    (limit,),
                )
                rows = cursor.fetchall()
        return [
            {
                "created_at": row[0].isoformat(),
                "event_type": row[1],
                "payload": row[2],
            }
            for row in rows
        ]

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
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    INSERT INTO {SCHEMA}.sessions (
                        session_id, policy_name, identity, project,
                        max_usd, max_total_tokens, expires_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        session_id,
                        policy_name,
                        identity,
                        project,
                        max_usd,
                        max_total_tokens,
                        expires_at,
                    ),
                )
            connection.commit()

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT session_id, policy_name, identity, project,
                           max_usd, max_total_tokens, spent_usd, spent_tokens,
                           reserved_usd, reserved_tokens, expires_at, closed
                    FROM {SCHEMA}.sessions
                    WHERE session_id = %s
                    """,
                    (session_id,),
                )
                row = cursor.fetchone()
        if row is None:
            return None
        return {
            "session_id": row[0],
            "policy_name": row[1],
            "identity": row[2],
            "project": row[3],
            "max_usd": str(row[4]),
            "max_total_tokens": int(row[5]),
            "spent_usd": str(row[6]),
            "spent_tokens": int(row[7]),
            "reserved_usd": str(row[8]),
            "reserved_tokens": int(row[9]),
            "expires_at": row[10].isoformat(),
            "closed": bool(row[11]),
        }

    def close_session(self, session_id: str) -> None:
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"UPDATE {SCHEMA}.sessions SET closed = TRUE WHERE session_id = %s",
                    (session_id,),
                )
            connection.commit()

    def reserve_budget(
        self,
        session_id: str,
        reservation_id: str,
        request_id: str,
        reserved_usd: Decimal,
        reserved_tokens: int,
    ) -> bool:
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT max_usd, max_total_tokens, spent_usd, spent_tokens,
                           reserved_usd, reserved_tokens
                    FROM {SCHEMA}.sessions
                    WHERE session_id = %s
                      AND closed = FALSE
                      AND expires_at > NOW()
                    FOR UPDATE
                    """,
                    (session_id,),
                )
                row = cursor.fetchone()
                if row is None:
                    connection.rollback()
                    return False
                used_usd = Decimal(row[2]) + Decimal(row[4])
                used_tokens = int(row[3]) + int(row[5])
                if used_usd + reserved_usd > Decimal(row[0]):
                    connection.rollback()
                    return False
                if used_tokens + reserved_tokens > int(row[1]):
                    connection.rollback()
                    return False
                cursor.execute(
                    f"""
                    UPDATE {SCHEMA}.sessions
                    SET reserved_usd = reserved_usd + %s,
                        reserved_tokens = reserved_tokens + %s
                    WHERE session_id = %s
                    """,
                    (reserved_usd, reserved_tokens, session_id),
                )
                cursor.execute(
                    f"""
                    INSERT INTO {SCHEMA}.reservations (
                        reservation_id, session_id, request_id,
                        reserved_usd, reserved_tokens
                    ) VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        reservation_id,
                        session_id,
                        request_id,
                        reserved_usd,
                        reserved_tokens,
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
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT session_id, reserved_usd, reserved_tokens, finalized
                    FROM {SCHEMA}.reservations
                    WHERE reservation_id = %s
                    FOR UPDATE
                    """,
                    (reservation_id,),
                )
                row = cursor.fetchone()
                if row is None or bool(row[3]):
                    connection.rollback()
                    return
                cursor.execute(
                    f"""
                    UPDATE {SCHEMA}.sessions
                    SET spent_usd = spent_usd + %s,
                        spent_tokens = spent_tokens + %s,
                        reserved_usd = GREATEST(reserved_usd - %s, 0),
                        reserved_tokens = GREATEST(reserved_tokens - %s, 0)
                    WHERE session_id = %s
                    """,
                    (actual_usd, actual_tokens, row[1], row[2], row[0]),
                )
                cursor.execute(
                    f"""
                    UPDATE {SCHEMA}.reservations
                    SET finalized = TRUE
                    WHERE reservation_id = %s
                    """,
                    (reservation_id,),
                )
            connection.commit()

    def get_idempotent_response(self, key: str) -> dict[str, Any] | None:
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT response_json
                    FROM {SCHEMA}.idempotency
                    WHERE key = %s
                    """,
                    (key,),
                )
                row = cursor.fetchone()
        if row is None:
            return None
        return cast(dict[str, Any], row[0])

    def store_idempotent_response(self, key: str, response: dict[str, Any]) -> None:
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    INSERT INTO {SCHEMA}.idempotency (key, response_json)
                    VALUES (%s, %s::jsonb)
                    ON CONFLICT (key) DO UPDATE SET
                        response_json = EXCLUDED.response_json,
                        created_at = NOW()
                    """,
                    (key, json.dumps(response)),
                )
            connection.commit()

    def is_proxy_blocked(self, identity: str | None = None) -> bool:
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT emergency_allowlist_json
                    FROM {SCHEMA}.governor_state
                    WHERE block_proxy_traffic = TRUE
                    """
                )
                rows = cursor.fetchall()
        if not rows:
            return False
        if identity is None:
            return True
        return not any(identity in row[0] for row in rows if isinstance(row[0], list))
