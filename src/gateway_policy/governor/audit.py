from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from gateway_policy.governor.store import GovernorStateStore


def record_decision(
    store: GovernorStateStore,
    event_type: str,
    governor_name: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    record = {
        "timestamp": datetime.now(tz=UTC).isoformat(),
        "governor": governor_name,
        **payload,
    }
    store.append_audit(event_type, record)
    return record
