from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol


class SessionStateStore(Protocol):
    def create_session(
        self,
        session_id: str,
        policy_name: str,
        identity: str,
        project: str | None,
        max_usd: Decimal,
        max_total_tokens: int,
        expires_at: datetime,
    ) -> None: ...

    def get_session(self, session_id: str) -> dict[str, Any] | None: ...

    def close_session(self, session_id: str) -> None: ...

    def reserve_budget(
        self,
        session_id: str,
        reservation_id: str,
        request_id: str,
        reserved_usd: Decimal,
        reserved_tokens: int,
    ) -> bool: ...

    def finalize_reservation(
        self,
        reservation_id: str,
        actual_usd: Decimal,
        actual_tokens: int,
    ) -> None: ...

    def get_idempotent_response(self, key: str) -> dict[str, Any] | None: ...

    def store_idempotent_response(self, key: str, response: dict[str, Any]) -> None: ...

    def is_proxy_blocked(self, identity: str | None = None) -> bool: ...
