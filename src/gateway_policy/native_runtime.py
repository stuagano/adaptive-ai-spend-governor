from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from gateway_policy.clients.auth import build_workspace_client
from gateway_policy.clients.rate_limits import RateLimitClient
from gateway_policy.governor.engine import GovernorEngine
from gateway_policy.governor.predictor import (
    DeterministicForecastProvider,
    ForecastProvider,
    ModelServingForecastProvider,
)
from gateway_policy.governor.store import GovernorStateStore
from gateway_policy.governor.telemetry import (
    SqlTelemetryConfig,
    SqlTelemetryProvider,
    TelemetryProvider,
)
from gateway_policy.models import GatewayPolicyBundle
from gateway_policy.runtime import load_runtime_bundle, open_governor_state_store


@dataclass(frozen=True)
class NativeGovernorRuntime:
    bundle: GatewayPolicyBundle
    store: GovernorStateStore
    engine: GovernorEngine


def build_native_governor_runtime(
    policy_file: Path | None = None,
    state_path: Path | None = None,
) -> NativeGovernorRuntime:
    resolved_policy = policy_file or Path(
        os.environ.get("GATEWAY_POLICY_FILE", "gateway-policy.example.yaml")
    )
    resolved_state = state_path or Path(
        os.environ.get("GATEWAY_POLICY_STATE_PATH", "/tmp/gateway-policy.db")
    )
    bundle = load_runtime_bundle(resolved_policy)
    store = open_governor_state_store(resolved_state)
    workspaces = {
        workspace.name: build_workspace_client(
            None if os.environ.get("DATABRICKS_APP_NAME") else workspace.profile
        )
        for workspace in bundle.spec.workspaces
    }
    rate_limit_clients = {
        name: RateLimitClient(workspace) for name, workspace in workspaces.items()
    }
    rate_policy_lookup = {policy.name: policy for policy in bundle.spec.rate_limits}
    telemetry: dict[str, TelemetryProvider] = {}
    forecasts: dict[str, ForecastProvider] = {}

    for governor in bundle.spec.governors:
        workspace = workspaces[governor.workspace]
        rate_policy = rate_policy_lookup[governor.rate_limit_policy]
        telemetry[governor.name] = SqlTelemetryProvider(
            workspace,
            SqlTelemetryConfig(
                warehouse_id=governor.sql_warehouse_id,
                account_id=bundle.spec.account.account_id,
                endpoint_name=rate_policy.endpoint,
            ),
        )
        if governor.forecast_endpoint:
            forecasts[governor.name] = ModelServingForecastProvider(
                workspace,
                governor.forecast_endpoint,
            )
        else:
            forecasts[governor.name] = DeterministicForecastProvider()

    engine = GovernorEngine(
        bundle,
        store,
        telemetry,
        rate_limit_clients,
        forecast_provider=forecasts,
    )
    return NativeGovernorRuntime(bundle=bundle, store=store, engine=engine)
