from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True)
class SpendSnapshot:
    month_to_date_usd: Decimal
    recent_window_usd: Decimal
    billing_closed_through: datetime
    telemetry_fresh_through: datetime
    daily_burn_rates: list[Decimal]
    is_stale: bool


@dataclass(frozen=True)
class ForecastResult:
    current_spend_usd: Decimal
    projected_month_end_usd: Decimal
    daily_velocity_usd: Decimal
    hourly_velocity_usd: Decimal
    utilization_pct: Decimal
    selected_stage: str | None
    confidence: str
    is_stale: bool
