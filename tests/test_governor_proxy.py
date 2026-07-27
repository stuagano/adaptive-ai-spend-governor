from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from gateway_policy.config import load_policy_file
from gateway_policy.governor import SpendSnapshot
from gateway_policy.governor.engine import GovernorEngine
from gateway_policy.governor.forecast import (
    apply_stage_to_policy,
    ewma_daily_burn,
    forecast_month_end,
    select_stage,
)
from gateway_policy.governor.state import GovernorRuntimeState, StateStore
from gateway_policy.governor.telemetry import FakeTelemetryProvider
from gateway_policy.models import GovernorStage
from gateway_policy.proxy.app import create_app
from gateway_policy.proxy.session import SessionManager
from gateway_policy.proxy.tokens import issue_session_token, verify_session_token
from gateway_policy.runtime import session_policy_map

FIXTURES = Path(__file__).parent / "fixtures"


class FakeRateLimitClient:
    def __init__(self) -> None:
        self.gateway: dict[str, Any] = {
            "rate_limits": [
                {"key": "endpoint", "renewal_period": "minute", "calls": 100, "tokens": 100000}
            ]
        }
        self.put_calls = 0

    def get_endpoint_gateway(self, endpoint_name: str) -> dict[str, Any]:
        _ = endpoint_name
        return dict(self.gateway)

    def put_endpoint_gateway(
        self,
        endpoint_name: str,
        ai_gateway: dict[str, Any],
    ) -> dict[str, Any]:
        _ = endpoint_name
        self.put_calls += 1
        self.gateway = ai_gateway
        return ai_gateway


class FakeUpstreamResponse:
    status_code = 200
    text = ""

    def json(self) -> dict[str, Any]:
        return {
            "id": "response-1",
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }


class FakeAsyncClient:
    last_url: str | None = None
    last_headers: dict[str, str] = {}
    last_body: dict[str, Any] = {}

    def __init__(self, timeout: float) -> None:
        _ = timeout

    async def __aenter__(self) -> FakeAsyncClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        _ = args

    async def post(
        self,
        url: str,
        headers: dict[str, str],
        json: dict[str, Any],
    ) -> FakeUpstreamResponse:
        self.__class__.last_url = url
        self.__class__.last_headers = headers
        self.__class__.last_body = json
        return FakeUpstreamResponse()


def _snapshot(
    month_to_date: str,
    daily: list[str],
    stale: bool = False,
) -> SpendSnapshot:
    now = datetime.now(tz=UTC)
    return SpendSnapshot(
        month_to_date_usd=Decimal(month_to_date),
        recent_window_usd=Decimal("0"),
        billing_closed_through=now,
        telemetry_fresh_through=now,
        daily_burn_rates=[Decimal(value) for value in daily],
        is_stale=stale,
    )


def test_ewma_daily_burn() -> None:
    burn = ewma_daily_burn([Decimal("100"), Decimal("200"), Decimal("300")])
    assert burn > Decimal("100")
    assert burn < Decimal("300")


def test_forecast_stale_never_reports_high_confidence() -> None:
    forecast = forecast_month_end(
        _snapshot("1000", ["100", "200", "300", "400", "500"], stale=True),
        Decimal("10000"),
    )
    assert forecast.is_stale is True
    assert forecast.confidence == "low"


    stages = [
        GovernorStage.model_validate(
            {
                "name": "caution",
                "forecastUtilizationPct": 70,
                "qpmMultiplier": 0.75,
                "tpmMultiplier": 0.75,
            }
        ),
        GovernorStage.model_validate(
            {
                "name": "emergency",
                "forecastUtilizationPct": 100,
                "qpmMultiplier": 0.1,
                "tpmMultiplier": 0.1,
            }
        ),
    ]
    forecast = forecast_month_end(_snapshot("15000", ["800", "900"]), Decimal("20000"))
    forecast = forecast.__class__(
        **{**forecast.__dict__, "utilization_pct": Decimal("68")}
    )
    selected = select_stage(forecast, stages, active_stage="caution", hysteresis_pct=Decimal("5"))
    assert selected is not None
    assert selected.name == "caution"


def test_apply_stage_to_policy_scales_limits() -> None:
    bundle = load_policy_file(FIXTURES / "governor-policy.yaml")
    governor = bundle.spec.governors[0]
    stage = governor.stages[0]
    baseline = [{"scope": "endpoint", "principal": None, "qpm": 100, "tpm": 100000}]
    adjusted = apply_stage_to_policy(governor, stage, baseline)
    assert adjusted[0]["qpm"] == 75
    assert adjusted[0]["tpm"] == 75000


def test_governor_engine_applies_throttle(tmp_path: Path) -> None:
    bundle = load_policy_file(FIXTURES / "governor-policy.yaml")
    store = StateStore(tmp_path / "state.db")
    fake_client = FakeRateLimitClient()
    telemetry = FakeTelemetryProvider(_snapshot("18000", ["900", "950", "1000"]))
    engine = GovernorEngine(
        bundle,
        store,
        telemetry,
        {"prod": fake_client},
    )
    result = engine.evaluate("monthly-burn", apply=True)
    assert result.applied is True
    assert result.selected_stage in {"caution", "emergency"}
    assert fake_client.put_calls == 1
    assert fake_client.gateway["rate_limits"][0]["calls"] in {75, 10}


def test_governor_engine_skips_stale_telemetry(tmp_path: Path) -> None:
    bundle = load_policy_file(FIXTURES / "governor-policy.yaml")
    store = StateStore(tmp_path / "state.db")
    telemetry = FakeTelemetryProvider(_snapshot("18000", [], stale=True))
    engine = GovernorEngine(bundle, store, telemetry, {"prod": FakeRateLimitClient()})
    result = engine.evaluate("monthly-burn", apply=True)
    assert result.applied is False
    assert result.healthy is False


def test_session_reservation_and_finalize(tmp_path: Path) -> None:
    bundle = load_policy_file(FIXTURES / "governor-policy.yaml")
    store = StateStore(tmp_path / "state.db")
    manager = SessionManager(store, session_policy_map(bundle), "secret")
    session = manager.create_session("agent-session", "alice@example.com", "ml")
    reservation_id, _ = manager.reserve(session.session_id, "req-1", "test-model", 1000)
    manager.finalize(reservation_id, "test-model", 1000, 500, session.session_id)
    remaining = manager.remaining_budget(session.session_id)
    assert Decimal(remaining["remaining_usd"]) < Decimal("10")


def test_session_token_round_trip() -> None:
    expires = datetime.now(tz=UTC) + timedelta(hours=1)
    token = issue_session_token("session-1", expires, "secret")
    assert verify_session_token(token, "secret") == "session-1"


def test_proxy_allows_emergency_allowlist_when_blocked(tmp_path: Path) -> None:
    store = StateStore(tmp_path / "state.db")
    store.upsert_governor_state(
        GovernorRuntimeState(
            governor_name="monthly-burn",
            active_stage="emergency",
            last_applied_at=datetime.now(tz=UTC),
            baseline_limits_json="[]",
            block_proxy_traffic=True,
            emergency_allowlist_json='["platform-oncall@example.com"]',
        )
    )
    assert store.is_proxy_blocked("platform-oncall@example.com") is False
    assert store.is_proxy_blocked("alice@example.com") is True
    assert store.is_proxy_blocked() is True


def test_proxy_rejects_when_blocked(tmp_path: Path) -> None:
    bundle = load_policy_file(FIXTURES / "governor-policy.yaml")
    store = StateStore(tmp_path / "state.db")
    manager = SessionManager(store, session_policy_map(bundle), "secret")
    store.upsert_governor_state(
        GovernorRuntimeState(
            governor_name="monthly-burn",
            active_stage="emergency",
            last_applied_at=datetime.now(tz=UTC),
            baseline_limits_json="[]",
            block_proxy_traffic=True,
            emergency_allowlist_json="[]",
        )
    )
    app = create_app(
        session_manager=manager,
        store=store,
        upstream_headers={},
        default_upstream_base_url="http://upstream.test",
        session_policies=session_policy_map(bundle),
        session_token_secret="secret",
    )
    client = TestClient(app)
    response = client.post("/v1/chat/completions", json={"model": "test-model"})
    assert response.status_code == 429


def test_proxy_requires_signed_session_when_mandatory(tmp_path: Path) -> None:
    bundle = load_policy_file(FIXTURES / "governor-policy.yaml")
    store = StateStore(tmp_path / "state.db")
    manager = SessionManager(store, session_policy_map(bundle), "secret")
    session = manager.create_session("agent-session", "alice@example.com")
    app = create_app(
        session_manager=manager,
        store=store,
        upstream_headers={},
        default_upstream_base_url="http://upstream.test",
        session_policies=session_policy_map(bundle),
        session_token_secret="secret",
        require_session=True,
    )
    client = TestClient(app)

    missing = client.post("/v1/chat/completions", json={"model": "test-model"})
    unsigned = client.post(
        "/v1/chat/completions",
        headers={"X-Session-Id": session.session_id},
        json={"model": "test-model"},
    )

    assert missing.status_code == 401
    assert unsigned.status_code == 401


def test_session_creation_uses_trusted_forwarded_identity(tmp_path: Path) -> None:
    bundle = load_policy_file(FIXTURES / "governor-policy.yaml")
    store = StateStore(tmp_path / "state.db")
    manager = SessionManager(store, session_policy_map(bundle), "secret")
    app = create_app(
        session_manager=manager,
        store=store,
        upstream_headers={},
        default_upstream_base_url="http://upstream.test",
        session_policies=session_policy_map(bundle),
        session_token_secret="secret",
        require_session=True,
        trusted_identity_header="X-Forwarded-Email",
    )
    client = TestClient(app)

    missing = client.post(
        "/sessions",
        json={"policy_name": "agent-session", "identity": "spoofed@example.com"},
    )
    created = client.post(
        "/sessions",
        headers={"X-Forwarded-Email": "alice@example.com"},
        json={"policy_name": "agent-session", "identity": "spoofed@example.com"},
    )

    assert missing.status_code == 401
    assert created.status_code == 200
    session_id = created.json()["session_id"]
    assert manager.get_session(session_id).identity == "alice@example.com"


def test_mandatory_proxy_uses_service_identity_and_policy_endpoint(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    bundle = load_policy_file(FIXTURES / "governor-policy.yaml")
    policy = bundle.spec.session_budgets[0]
    policy.model_prices[0].model = policy.endpoint
    store = StateStore(tmp_path / "state.db")
    manager = SessionManager(store, session_policy_map(bundle), "secret")
    session = manager.create_session("agent-session", "alice@example.com")
    token = manager.issue_token(session.session_id)
    monkeypatch.setattr("gateway_policy.proxy.app.httpx.AsyncClient", FakeAsyncClient)
    app = create_app(
        session_manager=manager,
        store=store,
        upstream_headers={},
        default_upstream_base_url="http://unused.test",
        session_policies=session_policy_map(bundle),
        session_token_secret="secret",
        upstream_headers_provider=lambda: {"Authorization": "Bearer service-token"},
        require_session=True,
        upstream_base_urls={
            "/v1/chat/completions": "https://workspace/ai-gateway/mlflow"
        },
        enforce_policy_endpoint=True,
    )
    client = TestClient(app)

    response = client.post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {token}"},
        json={"model": "unapproved-model", "messages": []},
    )

    assert response.status_code == 200
    assert FakeAsyncClient.last_url == (
        "https://workspace/ai-gateway/mlflow/v1/chat/completions"
    )
    assert FakeAsyncClient.last_headers["Authorization"] == "Bearer service-token"
    assert FakeAsyncClient.last_body["model"] == policy.endpoint


def test_session_reservations_are_atomic_under_concurrency(tmp_path: Path) -> None:
    bundle = load_policy_file(FIXTURES / "governor-policy.yaml")
    store = StateStore(tmp_path / "state.db")
    manager = SessionManager(store, session_policy_map(bundle), "secret")
    session = manager.create_session("agent-session", "alice@example.com")

    def reserve(index: int) -> bool:
        try:
            manager.reserve(session.session_id, f"parallel-{index}", "test-model", 20000)
            return True
        except RuntimeError:
            return False

    with ThreadPoolExecutor(max_workers=10) as executor:
        accepted = list(executor.map(reserve, range(10)))

    remaining = manager.remaining_budget(session.session_id)
    assert sum(accepted) == 5
    assert remaining["remaining_tokens"] == 0
