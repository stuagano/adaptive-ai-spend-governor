from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from gateway_policy.config import load_policy_file
from gateway_policy.governor import SpendSnapshot
from gateway_policy.governor.engine import GovernorEngine
from gateway_policy.governor.state import GovernorRuntimeState, StateStore
from gateway_policy.governor.telemetry import FakeTelemetryProvider
from gateway_policy.proxy.session import SessionManager
from gateway_policy.runtime import session_policy_map

FIXTURES = Path(__file__).parent / "fixtures"


class RecordingRateLimitClient:
    def __init__(self) -> None:
        self.gateway = {
            "rate_limits": [
                {"key": "endpoint", "renewal_period": "minute", "calls": 100, "tokens": 100000}
            ]
        }
        self.history: list[dict[str, object]] = []

    def get_endpoint_gateway(self, endpoint_name: str) -> dict[str, object]:
        _ = endpoint_name
        return dict(self.gateway)

    def put_endpoint_gateway(
        self,
        endpoint_name: str,
        ai_gateway: dict[str, object],
    ) -> dict[str, object]:
        _ = endpoint_name
        self.gateway = dict(ai_gateway)
        self.history.append(dict(ai_gateway))
        return self.gateway


def test_governor_evaluate_throttle_and_recover(tmp_path: Path) -> None:
    bundle = load_policy_file(FIXTURES / "governor-policy.yaml")
    store = StateStore(tmp_path / "state.db")
    client = RecordingRateLimitClient()
    high_spend = FakeTelemetryProvider(
        SpendSnapshot(
            month_to_date_usd=Decimal("18000"),
            recent_window_usd=Decimal("0"),
            billing_closed_through=datetime.now(tz=UTC),
            telemetry_fresh_through=datetime.now(tz=UTC),
            daily_burn_rates=[Decimal("900")],
            is_stale=False,
        )
    )
    engine = GovernorEngine(bundle, store, high_spend, {"prod": client})
    throttle = engine.evaluate("monthly-burn", apply=True)
    assert throttle.applied is True
    assert throttle.selected_stage is not None

    low_spend = FakeTelemetryProvider(
        SpendSnapshot(
            month_to_date_usd=Decimal("5000"),
            recent_window_usd=Decimal("0"),
            billing_closed_through=datetime.now(tz=UTC),
            telemetry_fresh_through=datetime.now(tz=UTC),
            daily_burn_rates=[Decimal("100")],
            is_stale=False,
        )
    )
    engine = GovernorEngine(bundle, store, low_spend, {"prod": client})
    store.upsert_governor_state(
        GovernorRuntimeState(
            governor_name="monthly-burn",
            active_stage=throttle.selected_stage,
            last_applied_at=datetime.now(tz=UTC) - timedelta(hours=2),
            baseline_limits_json='[{"scope":"endpoint","principal":null,"qpm":100,"tpm":100000}]',
            block_proxy_traffic=False,
            emergency_allowlist_json="[]",
        )
    )
    recovered = engine.evaluate("monthly-burn", apply=True)
    assert recovered.applied is True
    assert recovered.selected_stage is None
    assert client.gateway["rate_limits"][0]["calls"] == 100


def test_session_create_spend_and_reject(tmp_path: Path) -> None:
    bundle = load_policy_file(FIXTURES / "governor-policy.yaml")
    store = StateStore(tmp_path / "state.db")
    manager = SessionManager(store, session_policy_map(bundle), "secret")
    session = manager.create_session("agent-session", "alice@example.com")
    for index in range(20):
        reservation_id, _ = manager.reserve(
            session.session_id,
            f"req-{index}",
            "test-model",
            4000,
        )
        manager.finalize(reservation_id, "test-model", 1000, 4000, session.session_id)
    try:
        manager.reserve(session.session_id, "req-overflow", "test-model", 4000)
        raise AssertionError("expected budget exhaustion")
    except RuntimeError:
        pass
