from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

from gateway_policy.models import ModelPrice, SessionBudgetPolicy
from gateway_policy.proxy.store import SessionStateStore
from gateway_policy.proxy.tokens import issue_session_token


@dataclass
class SessionRecord:
    session_id: str
    policy_name: str
    identity: str
    project: str | None
    max_usd: Decimal
    max_total_tokens: int
    spent_usd: Decimal
    spent_tokens: int
    reserved_usd: Decimal
    reserved_tokens: int
    expires_at: datetime
    closed: bool


class SessionManager:
    def __init__(
        self,
        store: SessionStateStore,
        policies: dict[str, SessionBudgetPolicy],
        token_secret: str,
    ) -> None:
        self._store = store
        self._policies = policies
        self._token_secret = token_secret

    def create_session(
        self,
        policy_name: str,
        identity: str,
        project: str | None = None,
    ) -> SessionRecord:
        policy = self._policies[policy_name]
        if policy.allowed_identities and identity not in policy.allowed_identities:
            raise PermissionError(f"identity '{identity}' is not allowed")
        if policy.allowed_projects and project and project not in policy.allowed_projects:
            raise PermissionError(f"project '{project}' is not allowed")
        session_id = str(uuid4())
        expires_at = datetime.now(tz=UTC) + timedelta(seconds=policy.timeout_seconds)
        self._store.create_session(
            session_id=session_id,
            policy_name=policy_name,
            identity=identity,
            project=project,
            max_usd=policy.max_usd,
            max_total_tokens=policy.max_total_tokens,
            expires_at=expires_at,
        )
        return self.get_session(session_id)

    def issue_token(self, session_id: str) -> str:
        session = self.get_session(session_id)
        token = issue_session_token(session.session_id, session.expires_at, self._token_secret)
        return f"gpst_{token}"

    def get_session(self, session_id: str) -> SessionRecord:
        row = self._store.get_session(session_id)
        if row is None:
            raise KeyError(f"unknown session: {session_id}")
        return SessionRecord(
            session_id=row["session_id"],
            policy_name=row["policy_name"],
            identity=row["identity"],
            project=row["project"],
            max_usd=Decimal(row["max_usd"]),
            max_total_tokens=int(row["max_total_tokens"]),
            spent_usd=Decimal(row["spent_usd"]),
            spent_tokens=int(row["spent_tokens"]),
            reserved_usd=Decimal(row["reserved_usd"]),
            reserved_tokens=int(row["reserved_tokens"]),
            expires_at=datetime.fromisoformat(row["expires_at"]),
            closed=bool(row["closed"]),
        )

    def close_session(self, session_id: str) -> None:
        self._store.close_session(session_id)

    def reserve(
        self,
        session_id: str,
        request_id: str,
        model: str,
        estimated_output_tokens: int,
    ) -> tuple[str, Decimal]:
        session = self.get_session(session_id)
        policy = self._policies[session.policy_name]
        price = self._price_for_model(policy.model_prices, model)
        reserved_usd = (Decimal(estimated_output_tokens) / Decimal("1000000")) * price[1]
        reservation_id = str(uuid4())
        if not self._store.reserve_budget(
            session_id,
            reservation_id,
            request_id,
            reserved_usd,
            estimated_output_tokens,
        ):
            raise RuntimeError("session budget exhausted")
        return reservation_id, reserved_usd

    def finalize(
        self,
        reservation_id: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        session_id: str,
    ) -> Decimal:
        policy = self._policies[self.get_session(session_id).policy_name]
        input_price, output_price = self._price_for_model(policy.model_prices, model)
        actual_usd = (Decimal(input_tokens) / Decimal("1000000")) * input_price
        actual_usd += (Decimal(output_tokens) / Decimal("1000000")) * output_price
        self._store.finalize_reservation(
            reservation_id,
            actual_usd,
            input_tokens + output_tokens,
        )
        return actual_usd

    @staticmethod
    def _price_for_model(
        prices: list[ModelPrice],
        model: str,
    ) -> tuple[Decimal, Decimal]:
        for price in prices:
            if price.model == model:
                return price.input_usd_per_million_tokens, price.output_usd_per_million_tokens
        raise KeyError(f"no price configured for model '{model}'")

    def remaining_budget(self, session_id: str) -> dict[str, Any]:
        session = self.get_session(session_id)
        used_usd = session.spent_usd + session.reserved_usd
        used_tokens = session.spent_tokens + session.reserved_tokens
        return {
            "session_id": session.session_id,
            "remaining_usd": str(max(session.max_usd - used_usd, Decimal("0"))),
            "remaining_tokens": max(session.max_total_tokens - used_tokens, 0),
            "spent_usd": str(session.spent_usd),
            "spent_tokens": session.spent_tokens,
            "closed": session.closed,
            "expires_at": session.expires_at.isoformat(),
        }
