from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from gateway_policy.clients.rate_limits import (
    RateLimitClient,
    gateway_rate_limits_from_api,
    merge_gateway_rate_limits,
)
from gateway_policy.governor import ForecastResult, SpendSnapshot
from gateway_policy.governor.audit import record_decision
from gateway_policy.governor.forecast import (
    apply_stage_to_policy,
    select_stage,
)
from gateway_policy.governor.predictor import (
    DeterministicForecastProvider,
    ForecastProvider,
)
from gateway_policy.governor.state import GovernorRuntimeState
from gateway_policy.governor.store import GovernorStateStore
from gateway_policy.governor.telemetry import TelemetryProvider, model_prices_to_map
from gateway_policy.models import (
    EndpointRateLimitPolicy,
    GatewayPolicyBundle,
    GovernorPolicy,
    RateLimitPolicy,
)


@dataclass
class GovernorEvaluation:
    governor_name: str
    forecast: dict[str, Any]
    selected_stage: str | None
    applied: bool
    dry_run: bool
    healthy: bool
    details: dict[str, Any]


class GovernorEngine:
    def __init__(
        self,
        bundle: GatewayPolicyBundle,
        store: GovernorStateStore,
        telemetry: TelemetryProvider | dict[str, TelemetryProvider],
        rate_limit_clients: dict[str, RateLimitClient],
        forecast_provider: ForecastProvider | dict[str, ForecastProvider] | None = None,
    ) -> None:
        self._bundle = bundle
        self._store = store
        self._telemetry = telemetry
        self._rate_limit_clients = rate_limit_clients
        self._forecast_provider = forecast_provider or DeterministicForecastProvider()
        self._rate_limit_lookup = {policy.name: policy for policy in bundle.spec.rate_limits}

    def status(self, governor_name: str) -> dict[str, Any]:
        governor = self._get_governor(governor_name)
        runtime = self._store.get_governor_state(governor_name)
        snapshot, forecast = self._build_forecast(governor)
        stage = select_stage(
            forecast,
            governor.stages,
            runtime.active_stage if runtime else None,
            governor.hysteresis_pct,
        )
        return {
            "governor": governor_name,
            "healthy": not snapshot.is_stale,
            "active_stage": runtime.active_stage if runtime else None,
            "selected_stage": stage.name if stage else None,
            "forecast": {
                "current_spend_usd": str(forecast.current_spend_usd),
                "projected_month_end_usd": str(forecast.projected_month_end_usd),
                "utilization_pct": str(forecast.utilization_pct),
                "confidence": forecast.confidence,
                "is_stale": forecast.is_stale,
            },
            "block_proxy_traffic": bool(runtime.block_proxy_traffic) if runtime else False,
        }

    def evaluate(self, governor_name: str, apply: bool = False) -> GovernorEvaluation:
        governor = self._get_governor(governor_name)
        runtime = self._store.get_governor_state(governor_name)
        rate_policy = self._rate_limit_lookup[governor.rate_limit_policy]
        baseline_limits = self._baseline_limits(rate_policy, runtime)
        snapshot, forecast = self._build_forecast(governor)
        selected = select_stage(
            forecast,
            governor.stages,
            runtime.active_stage if runtime else None,
            governor.hysteresis_pct,
        )

        if snapshot.is_stale:
            record_decision(
                self._store,
                "governor_skipped_stale_telemetry",
                governor_name,
                {"reason": "telemetry stale"},
            )
            return GovernorEvaluation(
                governor_name=governor_name,
                forecast=self._forecast_payload(forecast),
                selected_stage=None,
                applied=False,
                dry_run=not apply,
                healthy=False,
                details={"reason": "stale telemetry"},
            )

        active_stage = runtime.active_stage if runtime else None
        selected_name = selected.name if selected else None
        is_relaxation = self._is_relaxation(active_stage, selected_name, governor)
        if is_relaxation and runtime and runtime.last_applied_at:
            cooldown_until = runtime.last_applied_at + timedelta(seconds=governor.cooldown_seconds)
            if datetime.now(tz=UTC) < cooldown_until:
                return GovernorEvaluation(
                    governor_name=governor_name,
                    forecast=self._forecast_payload(forecast),
                    selected_stage=selected_name,
                    applied=False,
                    dry_run=not apply,
                    healthy=True,
                    details={"reason": "recovery cooldown active"},
                )

        if active_stage == selected_name and runtime and runtime.last_applied_at:
            return GovernorEvaluation(
                governor_name=governor_name,
                forecast=self._forecast_payload(forecast),
                selected_stage=selected_name,
                applied=False,
                dry_run=not apply,
                healthy=True,
                details={"reason": "stage unchanged"},
            )

        baseline_gateway = self._baseline_gateway(runtime)
        if apply and (runtime is None or not runtime.baseline_limits_json):
            baseline_gateway = self._capture_baseline_gateway(rate_policy)
            captured_limits = self._limits_from_gateway(baseline_gateway)
            if captured_limits:
                baseline_limits = captured_limits

        adjusted_limits = apply_stage_to_policy(governor, selected, baseline_limits)
        applied = False
        if apply:
            if selected is not None:
                fallback_enabled = (
                    selected.fallback_enabled
                    if selected.fallback_enabled is not None
                    else rate_policy.fallback_enabled
                )
                self._apply_rate_limits(
                    rate_policy,
                    adjusted_limits,
                    governor,
                    fallback_enabled=fallback_enabled,
                )
            elif runtime and runtime.active_stage:
                baseline_fallback = baseline_gateway.get("fallback_config", {}).get(
                    "enabled",
                    False,
                )
                self._apply_rate_limits(
                    rate_policy,
                    baseline_limits,
                    governor,
                    fallback_enabled=bool(baseline_fallback),
                )
            applied = True
            new_state = GovernorRuntimeState(
                governor_name=governor_name,
                active_stage=selected_name,
                last_applied_at=datetime.now(tz=UTC),
                baseline_limits_json=json.dumps(baseline_limits),
                block_proxy_traffic=bool(selected.block_proxy_traffic) if selected else False,
                emergency_allowlist_json=json.dumps(
                    selected.emergency_allowlist if selected else []
                ),
                baseline_gateway_json=json.dumps(baseline_gateway),
            )
            self._store.upsert_governor_state(new_state)
            record_decision(
                self._store,
                "governor_stage_applied" if selected else "governor_recovered",
                governor_name,
                {
                    "selected_stage": selected_name,
                    "utilization_pct": str(forecast.utilization_pct),
                    "limits": adjusted_limits if selected else baseline_limits,
                },
            )

        return GovernorEvaluation(
            governor_name=governor_name,
            forecast=self._forecast_payload(forecast),
            selected_stage=selected_name,
            applied=applied,
            dry_run=not apply,
            healthy=True,
            details={"limits": adjusted_limits if selected else baseline_limits},
        )

    def run_once(self, apply: bool = True) -> list[GovernorEvaluation]:
        return [
            self.evaluate(governor.name, apply=apply) for governor in self._bundle.spec.governors
        ]

    def run_daemon(self, apply: bool = True) -> None:
        while True:
            self.run_once(apply=apply)
            interval = min(
                (governor.polling_interval_seconds for governor in self._bundle.spec.governors),
                default=300,
            )
            time.sleep(interval)

    def _capture_baseline_gateway(
        self,
        rate_policy: EndpointRateLimitPolicy,
    ) -> dict[str, Any]:
        client = self._rate_limit_clients[rate_policy.workspace]
        return client.get_endpoint_gateway(rate_policy.endpoint)

    @staticmethod
    def _limits_from_gateway(existing: dict[str, Any]) -> list[dict[str, object]]:
        return gateway_rate_limits_from_api(existing)

    def _apply_rate_limits(
        self,
        rate_policy: EndpointRateLimitPolicy,
        limits: list[dict[str, object]],
        governor: GovernorPolicy,
        fallback_enabled: bool | None,
    ) -> None:
        client = self._rate_limit_clients[rate_policy.workspace]
        existing = client.get_endpoint_gateway(rate_policy.endpoint)
        desired_limits = [RateLimitPolicy.model_validate(limit) for limit in limits]
        ownership = {
            "managed_by": "gateway-policy",
            "gateway_policy_bundle": self._bundle.metadata.name,
            "governor": governor.name,
        }
        merged = merge_gateway_rate_limits(
            existing,
            desired_limits,
            ownership,
            fallback_enabled=fallback_enabled,
        )
        client.put_endpoint_gateway(rate_policy.endpoint, merged)

    def _baseline_limits(
        self,
        rate_policy: EndpointRateLimitPolicy,
        runtime: GovernorRuntimeState | None,
    ) -> list[dict[str, object]]:
        if runtime and runtime.baseline_limits_json:
            loaded = json.loads(runtime.baseline_limits_json)
            if isinstance(loaded, list):
                return cast(list[dict[str, object]], loaded)
        return [
            {
                "scope": limit.scope.value,
                "principal": limit.principal,
                "qpm": limit.qpm,
                "tpm": limit.tpm,
            }
            for limit in rate_policy.limits
        ]

    @staticmethod
    def _baseline_gateway(runtime: GovernorRuntimeState | None) -> dict[str, Any]:
        if runtime and runtime.baseline_gateway_json:
            loaded = json.loads(runtime.baseline_gateway_json)
            if isinstance(loaded, dict):
                return cast(dict[str, Any], loaded)
        return {}

    def _build_forecast(
        self,
        governor: GovernorPolicy,
    ) -> tuple[SpendSnapshot, ForecastResult]:
        snapshot = self._telemetry_for(governor.name).fetch_spend_snapshot(
            governor.lookback_days,
            model_prices_to_map(governor.model_prices),
        )
        forecast = self._forecast_for(governor.name).forecast(
            snapshot,
            governor.monthly_target_usd,
            governor.forecast_horizon_days,
        )
        return snapshot, forecast

    def _get_governor(self, governor_name: str) -> GovernorPolicy:
        for governor in self._bundle.spec.governors:
            if governor.name == governor_name:
                return governor
        raise KeyError(f"unknown governor: {governor_name}")

    def _telemetry_for(self, governor_name: str) -> TelemetryProvider:
        if isinstance(self._telemetry, dict):
            return self._telemetry[governor_name]
        return self._telemetry

    def _forecast_for(self, governor_name: str) -> ForecastProvider:
        if isinstance(self._forecast_provider, dict):
            return self._forecast_provider[governor_name]
        return self._forecast_provider

    @staticmethod
    def _is_relaxation(
        active_stage: str | None,
        selected_stage: str | None,
        governor: GovernorPolicy,
    ) -> bool:
        if active_stage is None:
            return False
        if selected_stage is None:
            return True
        stage_order = {stage.name: index for index, stage in enumerate(governor.stages)}
        return stage_order.get(selected_stage, 0) < stage_order.get(active_stage, 0)

    @staticmethod
    def _forecast_payload(forecast: ForecastResult) -> dict[str, str]:
        return {
            "current_spend_usd": str(forecast.current_spend_usd),
            "projected_month_end_usd": str(forecast.projected_month_end_usd),
            "daily_velocity_usd": str(forecast.daily_velocity_usd),
            "hourly_velocity_usd": str(forecast.hourly_velocity_usd),
            "utilization_pct": str(forecast.utilization_pct),
            "confidence": forecast.confidence,
            "is_stale": str(forecast.is_stale),
        }
