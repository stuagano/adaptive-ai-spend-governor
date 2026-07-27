from __future__ import annotations

from decimal import Decimal
from typing import Any, Protocol

from gateway_policy.governor import ForecastResult, SpendSnapshot
from gateway_policy.governor.forecast import forecast_month_end


class ForecastProvider(Protocol):
    def forecast(
        self,
        snapshot: SpendSnapshot,
        monthly_target_usd: Decimal,
        horizon_days: int,
    ) -> ForecastResult: ...


class DeterministicForecastProvider:
    def forecast(
        self,
        snapshot: SpendSnapshot,
        monthly_target_usd: Decimal,
        horizon_days: int,
    ) -> ForecastResult:
        _ = horizon_days
        return forecast_month_end(snapshot, monthly_target_usd)


class ModelServingForecastProvider:
    """Advisory forecasting endpoint with deterministic safe fallback."""

    def __init__(
        self,
        workspace_client: Any,
        endpoint_name: str,
        fallback: ForecastProvider | None = None,
    ) -> None:
        self._workspace = workspace_client
        self._endpoint_name = endpoint_name
        self._fallback = fallback or DeterministicForecastProvider()

    def forecast(
        self,
        snapshot: SpendSnapshot,
        monthly_target_usd: Decimal,
        horizon_days: int,
    ) -> ForecastResult:
        if snapshot.is_stale:
            return self._fallback.forecast(snapshot, monthly_target_usd, horizon_days)

        record = {
            "month_to_date_usd": float(snapshot.month_to_date_usd),
            "recent_window_usd": float(snapshot.recent_window_usd),
            "daily_burn_rates": [float(value) for value in snapshot.daily_burn_rates],
            "monthly_target_usd": float(monthly_target_usd),
            "horizon_days": horizon_days,
        }
        try:
            response = self._workspace.serving_endpoints.query(
                name=self._endpoint_name,
                dataframe_records=[record],
            )
            prediction = self._first_prediction(response)
            projected = Decimal(str(prediction["projected_month_end_usd"]))
            daily_velocity = Decimal(str(prediction["daily_velocity_usd"]))
            utilization = (
                projected / monthly_target_usd * Decimal("100")
                if monthly_target_usd > 0
                else Decimal("0")
            )
            return ForecastResult(
                current_spend_usd=snapshot.month_to_date_usd,
                projected_month_end_usd=projected,
                daily_velocity_usd=daily_velocity,
                hourly_velocity_usd=daily_velocity / Decimal("24"),
                utilization_pct=utilization,
                selected_stage=None,
                confidence=str(prediction.get("confidence", "model")),
                is_stale=False,
            )
        except Exception:  # noqa: BLE001 - model is advisory; deterministic path is mandatory
            return self._fallback.forecast(snapshot, monthly_target_usd, horizon_days)

    @staticmethod
    def _first_prediction(response: Any) -> dict[str, Any]:
        predictions = getattr(response, "predictions", None)
        if not predictions:
            raise ValueError("forecast endpoint returned no predictions")
        prediction = predictions[0]
        if not isinstance(prediction, dict):
            raise TypeError("forecast prediction must be an object")
        return prediction
