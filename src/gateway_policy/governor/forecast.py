from __future__ import annotations

from calendar import monthrange
from datetime import UTC, datetime
from decimal import Decimal

from gateway_policy.governor import ForecastResult, SpendSnapshot
from gateway_policy.models import GovernorPolicy, GovernorStage


def ewma_daily_burn(daily_burn_rates: list[Decimal], alpha: Decimal = Decimal("0.35")) -> Decimal:
    if not daily_burn_rates:
        return Decimal("0")
    value = daily_burn_rates[0]
    for burn in daily_burn_rates[1:]:
        value = alpha * burn + (Decimal("1") - alpha) * value
    return value


def forecast_month_end(snapshot: SpendSnapshot, monthly_target_usd: Decimal) -> ForecastResult:
    now = datetime.now(tz=UTC)
    days_in_month = monthrange(now.year, now.month)[1]
    day_of_month = now.day
    remaining_days = max(days_in_month - day_of_month, 0)

    daily_velocity = ewma_daily_burn(snapshot.daily_burn_rates)
    hourly_velocity = daily_velocity / Decimal("24")
    projected = snapshot.month_to_date_usd + (daily_velocity * Decimal(remaining_days))
    utilization = (
        (projected / monthly_target_usd) * Decimal("100")
        if monthly_target_usd > 0
        else Decimal("0")
    )
    if snapshot.is_stale:
        confidence = "low"
    elif len(snapshot.daily_burn_rates) >= 5:
        confidence = "high"
    else:
        confidence = "medium"
    return ForecastResult(
        current_spend_usd=snapshot.month_to_date_usd,
        projected_month_end_usd=projected,
        daily_velocity_usd=daily_velocity,
        hourly_velocity_usd=hourly_velocity,
        utilization_pct=utilization,
        selected_stage=None,
        confidence=confidence,
        is_stale=snapshot.is_stale,
    )


def select_stage(
    forecast: ForecastResult,
    stages: list[GovernorStage],
    active_stage: str | None,
    hysteresis_pct: Decimal,
) -> GovernorStage | None:
    if forecast.is_stale:
        return None

    ordered = sorted(stages, key=lambda stage: stage.forecast_utilization_pct)
    selected: GovernorStage | None = None
    for stage in ordered:
        threshold = stage.forecast_utilization_pct
        if active_stage == stage.name:
            threshold = max(Decimal("0"), threshold - hysteresis_pct)
        if forecast.utilization_pct >= threshold:
            selected = stage
    return selected


def apply_stage_to_policy(
    governor: GovernorPolicy,
    stage: GovernorStage | None,
    baseline_limits: list[dict[str, object]],
) -> list[dict[str, object]]:
    if stage is None:
        return baseline_limits
    adjusted: list[dict[str, object]] = []
    for limit in baseline_limits:
        updated = dict(limit)
        if "qpm" in updated and updated["qpm"] is not None:
            updated["qpm"] = int(
                Decimal(str(updated["qpm"])) * stage.qpm_multiplier
            )
        if "tpm" in updated and updated["tpm"] is not None:
            updated["tpm"] = int(
                Decimal(str(updated["tpm"])) * stage.tpm_multiplier
            )
        adjusted.append(updated)
    return adjusted
