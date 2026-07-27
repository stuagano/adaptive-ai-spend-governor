from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from gateway_policy.config import load_policy_file
from gateway_policy.governor import SpendSnapshot
from gateway_policy.governor.engine import GovernorEngine
from gateway_policy.governor.predictor import ModelServingForecastProvider
from gateway_policy.governor.state import StateStore
from gateway_policy.governor.telemetry import FakeTelemetryProvider
from gateway_policy.omnigent import render_managed_omnigent_config

FIXTURES = Path(__file__).parent / "fixtures"


class GatewayClient:
    def __init__(self) -> None:
        self.gateway: dict[str, Any] = {
            "rate_limits": [
                {
                    "key": "endpoint",
                    "renewal_period": "minute",
                    "calls": 240,
                    "tokens": 240000,
                }
            ],
            "fallback_config": {"enabled": False},
            "guardrails": {"input": {"safety": True}},
        }

    def get_endpoint_gateway(self, endpoint_name: str) -> dict[str, Any]:
        _ = endpoint_name
        return self.gateway

    def put_endpoint_gateway(
        self,
        endpoint_name: str,
        ai_gateway: dict[str, Any],
    ) -> dict[str, Any]:
        _ = endpoint_name
        self.gateway = ai_gateway
        return ai_gateway


def _high_spend() -> SpendSnapshot:
    now = datetime.now(tz=UTC)
    return SpendSnapshot(
        month_to_date_usd=Decimal("19000"),
        recent_window_usd=Decimal("1000"),
        billing_closed_through=now,
        telemetry_fresh_through=now,
        daily_burn_rates=[Decimal("900"), Decimal("950"), Decimal("1000")],
        is_stale=False,
    )


def test_managed_omnigent_renderer_uses_only_builtins() -> None:
    bundle = load_policy_file(Path("gateway-policy.example.yaml"))
    assert bundle.spec.omnigent is not None

    rendered = render_managed_omnigent_config(bundle.spec.omnigent)

    assert rendered["policies"]["session_budget"]["handler"].endswith(".cost_budget")
    assert rendered["policies"]["daily_budget"]["handler"].endswith(
        ".user_daily_cost_budget"
    )
    assert rendered["policies"]["session_budget"]["factory_params"]["max_cost_usd"] == 10


def test_governor_captures_live_baseline_and_preserves_gateway_settings(
    tmp_path: Path,
) -> None:
    bundle = load_policy_file(FIXTURES / "governor-policy.yaml")
    bundle.spec.rate_limits[0].fallback_enabled = True
    bundle.spec.governors[0].stages[0].fallback_enabled = True
    client = GatewayClient()
    engine = GovernorEngine(
        bundle,
        StateStore(tmp_path / "state.db"),
        FakeTelemetryProvider(_high_spend()),
        {"prod": client},
    )

    result = engine.evaluate("monthly-burn", apply=True)

    assert result.applied is True
    assert client.gateway["rate_limits"][0]["calls"] in {180, 120, 24}
    assert client.gateway["fallback_config"]["enabled"] is True
    assert client.gateway["guardrails"] == {"input": {"safety": True}}


class QueryingWorkspace:
    def __init__(self, prediction: dict[str, Any] | None) -> None:
        self._prediction = prediction
        self.serving_endpoints = self

    def query(self, name: str, dataframe_records: list[dict[str, Any]]) -> Any:
        _ = name, dataframe_records
        if self._prediction is None:
            raise RuntimeError("endpoint unavailable")
        return SimpleNamespace(predictions=[self._prediction])


def test_model_serving_forecast_is_advisory_with_safe_fallback() -> None:
    snapshot = _high_spend()
    provider = ModelServingForecastProvider(
        QueryingWorkspace(
            {
                "projected_month_end_usd": 28000,
                "daily_velocity_usd": 900,
                "confidence": "high",
            }
        ),
        "forecast",
    )
    prediction = provider.forecast(snapshot, Decimal("25000"), 30)
    assert prediction.projected_month_end_usd == Decimal("28000")
    assert prediction.confidence == "high"

    unavailable = ModelServingForecastProvider(QueryingWorkspace(None), "forecast")
    fallback = unavailable.forecast(snapshot, Decimal("25000"), 30)
    assert fallback.projected_month_end_usd > 0
    assert fallback.confidence != "high"
