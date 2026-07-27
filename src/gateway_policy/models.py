from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from gateway_policy import MANAGED_BY_LABEL, OWNERSHIP_TAG_KEY


class ResourceType(StrEnum):
    UNITY_AI_GATEWAY = "unity_ai_gateway"
    GENIE = "genie"


class RateLimitScope(StrEnum):
    ENDPOINT = "endpoint"
    USER = "user"
    GROUP = "group"
    SERVICE_PRINCIPAL = "service_principal"


class PlanActionType(StrEnum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    NO_OP = "no_op"


class Metadata(BaseModel):
    name: str
    owner: str
    managed_by: str = MANAGED_BY_LABEL


class AccountTarget(BaseModel):
    account_id: str = Field(alias="accountId")
    profile: str = "DEFAULT"

    model_config = {"populate_by_name": True}


class WorkspaceTarget(BaseModel):
    name: str
    profile: str | None = None
    host: str | None = None


class ThresholdAction(BaseModel):
    amount_usd: Decimal = Field(alias="amountUsd", gt=0)
    emails: list[str] = Field(min_length=1)
    block_usage: bool = Field(default=False, alias="blockUsage")

    model_config = {"populate_by_name": True}

    @field_validator("emails")
    @classmethod
    def validate_emails(cls, emails: list[str]) -> list[str]:
        cleaned = [email.strip() for email in emails if email.strip()]
        if not cleaned:
            raise ValueError("at least one email is required")
        return cleaned


class PerUserOverride(BaseModel):
    principals: list[str] = Field(min_length=1)
    amount_usd: Decimal = Field(alias="amountUsd", gt=0)
    block_usage: bool = Field(default=False, alias="blockUsage")

    model_config = {"populate_by_name": True}


class BudgetPolicy(BaseModel):
    name: str
    display_name: str = Field(alias="displayName")
    resource_type: ResourceType = Field(alias="resourceType")
    workspaces: list[str] = Field(default_factory=list)
    tags: dict[str, str] = Field(default_factory=dict)
    shared_thresholds: list[ThresholdAction] = Field(default_factory=list, alias="sharedThresholds")
    per_user_threshold: ThresholdAction | None = Field(default=None, alias="perUserThreshold")
    per_user_overrides: list[PerUserOverride] = Field(
        default_factory=list, alias="perUserOverrides"
    )

    model_config = {"populate_by_name": True}

    @model_validator(mode="after")
    def validate_budget_semantics(self) -> BudgetPolicy:
        if len(self.shared_thresholds) > 4:
            raise ValueError(f"budget '{self.name}' supports at most 4 shared thresholds")

        if len(self.per_user_overrides) > 20:
            raise ValueError(f"budget '{self.name}' supports at most 20 per-user overrides")

        if self.resource_type == ResourceType.GENIE:
            if self.tags != {"databricks-product": "genie"}:
                raise ValueError(
                    f"genie budget '{self.name}' must use tags: databricks-product: genie only"
                )
        else:
            if any(threshold.block_usage for threshold in self.shared_thresholds):
                raise ValueError(
                    f"budget '{self.name}': blockUsage is only supported for genie budgets"
                )
            if self.per_user_threshold and self.per_user_threshold.block_usage:
                raise ValueError(
                    f"budget '{self.name}': per-user blockUsage is only supported for genie budgets"
                )
            if self.per_user_overrides:
                raise ValueError(
                    f"budget '{self.name}': perUserOverrides are only supported for genie budgets"
                )

        return self


class RateLimitPolicy(BaseModel):
    scope: RateLimitScope
    principal: str | None = None
    qpm: int | None = Field(default=None, gt=0)
    tpm: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_limit(self) -> RateLimitPolicy:
        if self.qpm is None and self.tpm is None:
            raise ValueError("rate limit requires qpm and/or tpm")
        if self.scope == RateLimitScope.ENDPOINT and self.principal is not None:
            raise ValueError("endpoint scope must not set principal")
        if self.scope != RateLimitScope.ENDPOINT and not self.principal:
            raise ValueError(f"{self.scope.value} scope requires principal")
        return self


class EndpointRateLimitPolicy(BaseModel):
    name: str
    workspace: str
    endpoint: str
    limits: list[RateLimitPolicy] = Field(min_length=1)
    fallback_enabled: bool | None = Field(default=None, alias="fallbackEnabled")

    model_config = {"populate_by_name": True}


class ModelPrice(BaseModel):
    model: str
    input_usd_per_million_tokens: Decimal = Field(alias="inputUsdPerMillionTokens", gt=0)
    output_usd_per_million_tokens: Decimal = Field(alias="outputUsdPerMillionTokens", gt=0)

    model_config = {"populate_by_name": True}


class GovernorStage(BaseModel):
    name: str
    forecast_utilization_pct: Decimal = Field(alias="forecastUtilizationPct", gt=0, le=100)
    qpm_multiplier: Decimal = Field(alias="qpmMultiplier", gt=0, le=1)
    tpm_multiplier: Decimal = Field(alias="tpmMultiplier", gt=0, le=1)
    block_proxy_traffic: bool = Field(default=False, alias="blockProxyTraffic")
    emergency_allowlist: list[str] = Field(default_factory=list, alias="emergencyAllowlist")
    fallback_enabled: bool | None = Field(default=None, alias="fallbackEnabled")

    model_config = {"populate_by_name": True}


class GovernorPolicy(BaseModel):
    name: str
    workspace: str
    rate_limit_policy: str = Field(alias="rateLimitPolicy")
    sql_warehouse_id: str = Field(alias="sqlWarehouseId")
    forecast_endpoint: str | None = Field(default=None, alias="forecastEndpoint")
    monthly_target_usd: Decimal = Field(alias="monthlyTargetUsd", gt=0)
    lookback_days: int = Field(default=7, alias="lookbackDays", ge=1, le=90)
    forecast_horizon_days: int = Field(default=30, alias="forecastHorizonDays", ge=1, le=90)
    polling_interval_seconds: int = Field(default=300, alias="pollingIntervalSeconds", ge=30)
    cooldown_seconds: int = Field(default=1800, alias="cooldownSeconds", ge=0)
    hysteresis_pct: Decimal = Field(default=Decimal("5"), alias="hysteresisPct", ge=0, le=20)
    stages: list[GovernorStage] = Field(min_length=1)
    model_prices: list[ModelPrice] = Field(default_factory=list, alias="modelPrices")

    model_config = {"populate_by_name": True}

    @model_validator(mode="after")
    def validate_stages(self) -> GovernorPolicy:
        if not self.model_prices:
            raise ValueError(f"governor '{self.name}' requires at least one model price")
        utilizations = [stage.forecast_utilization_pct for stage in self.stages]
        if utilizations != sorted(utilizations):
            raise ValueError(
                f"governor '{self.name}' stages must have increasing utilization thresholds"
            )
        multipliers = [(stage.qpm_multiplier, stage.tpm_multiplier) for stage in self.stages]
        for index in range(1, len(multipliers)):
            prev_qpm, prev_tpm = multipliers[index - 1]
            qpm, tpm = multipliers[index]
            if qpm > prev_qpm or tpm > prev_tpm:
                raise ValueError(
                    f"governor '{self.name}' stage multipliers must be non-increasing"
                )
        return self


class SessionBudgetPolicy(BaseModel):
    name: str
    workspace: str
    endpoint: str
    upstream_base_url: str = Field(alias="upstreamBaseUrl")
    max_usd: Decimal = Field(alias="maxUsd", gt=0)
    max_total_tokens: int = Field(alias="maxTotalTokens", gt=0)
    timeout_seconds: int = Field(default=3600, alias="timeoutSeconds", ge=60)
    allowed_identities: list[str] = Field(default_factory=list, alias="allowedIdentities")
    allowed_projects: list[str] = Field(default_factory=list, alias="allowedProjects")
    allowed_request_tag_keys: list[str] = Field(
        default_factory=lambda: ["project", "team"],
        alias="allowedRequestTagKeys",
    )
    fail_mode: Literal["fail_closed", "fail_open"] = Field(
        default="fail_closed", alias="failMode"
    )
    model_prices: list[ModelPrice] = Field(min_length=1, alias="modelPrices")

    model_config = {"populate_by_name": True}


class OmnigentCostBudget(BaseModel):
    max_cost_usd: Decimal = Field(alias="maxCostUsd", gt=0)
    ask_thresholds_usd: list[Decimal] = Field(
        default_factory=list,
        alias="askThresholdsUsd",
    )
    expensive_models: list[str] = Field(default_factory=list, alias="expensiveModels")

    model_config = {"populate_by_name": True}

    @model_validator(mode="after")
    def validate_thresholds(self) -> OmnigentCostBudget:
        if self.ask_thresholds_usd != sorted(self.ask_thresholds_usd):
            raise ValueError("Omnigent cost thresholds must be increasing")
        if len(set(self.ask_thresholds_usd)) != len(self.ask_thresholds_usd):
            raise ValueError("Omnigent cost thresholds must be unique")
        if any(threshold >= self.max_cost_usd for threshold in self.ask_thresholds_usd):
            raise ValueError("Omnigent ASK thresholds must be below maxCostUsd")
        return self


class OmnigentPolicyConfig(BaseModel):
    session_cost_budget: OmnigentCostBudget = Field(alias="sessionCostBudget")
    user_daily_cost_budget: OmnigentCostBudget | None = Field(
        default=None,
        alias="userDailyCostBudget",
    )

    model_config = {"populate_by_name": True}


class PolicySpec(BaseModel):
    account: AccountTarget
    workspaces: list[WorkspaceTarget] = Field(default_factory=list)
    budgets: list[BudgetPolicy] = Field(default_factory=list)
    rate_limits: list[EndpointRateLimitPolicy] = Field(default_factory=list, alias="rateLimits")
    governors: list[GovernorPolicy] = Field(default_factory=list)
    session_budgets: list[SessionBudgetPolicy] = Field(
        default_factory=list, alias="sessionBudgets"
    )
    omnigent: OmnigentPolicyConfig | None = None

    model_config = {"populate_by_name": True}

    @model_validator(mode="after")
    def validate_references(self) -> PolicySpec:
        workspace_names = {workspace.name for workspace in self.workspaces}
        rate_limit_names = {rate_limit.name for rate_limit in self.rate_limits}
        for budget in self.budgets:
            unknown = set(budget.workspaces) - workspace_names
            if unknown:
                raise ValueError(
                    f"budget '{budget.name}' references unknown workspaces: {sorted(unknown)}"
                )
        for rate_limit in self.rate_limits:
            if rate_limit.workspace not in workspace_names:
                raise ValueError(
                    f"rate limit '{rate_limit.name}' references unknown workspace "
                    f"'{rate_limit.workspace}'"
                )
        for governor in self.governors:
            if governor.workspace not in workspace_names:
                raise ValueError(
                    f"governor '{governor.name}' references unknown workspace "
                    f"'{governor.workspace}'"
                )
            if governor.rate_limit_policy not in rate_limit_names:
                raise ValueError(
                    f"governor '{governor.name}' references unknown rate limit policy "
                    f"'{governor.rate_limit_policy}'"
                )
        for session_budget in self.session_budgets:
            if session_budget.workspace not in workspace_names:
                raise ValueError(
                    f"session budget '{session_budget.name}' references unknown workspace "
                    f"'{session_budget.workspace}'"
                )
        return self


class GatewayPolicyBundle(BaseModel):
    api_version: Literal["gateway-policy.databricks.com/v1"] = Field(alias="apiVersion")
    kind: Literal["GatewayPolicyBundle"]
    metadata: Metadata
    spec: PolicySpec

    model_config = {"populate_by_name": True}


class PlanAction(BaseModel):
    action: PlanActionType
    resource_type: Literal["budget", "rate_limit"]
    resource_name: str
    workspace: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None


class PlanResult(BaseModel):
    bundle_name: str
    actions: list[PlanAction]
    summary: dict[str, int]

    @model_validator(mode="after")
    def compute_summary(self) -> PlanResult:
        summary = {action.value: 0 for action in PlanActionType}
        for item in self.actions:
            summary[item.action.value] += 1
        self.summary = summary
        return self


class NormalizedBudget(BaseModel):
    policy_name: str
    display_name: str
    resource_type: ResourceType
    workspace_ids: list[int]
    tags: dict[str, str]
    shared_thresholds: list[ThresholdAction]
    per_user_threshold: ThresholdAction | None
    per_user_overrides: list[PerUserOverride]
    ownership_tags: dict[str, str]

    def ownership_marker(self) -> dict[str, str]:
        return {
            MANAGED_BY_LABEL: self.ownership_tags.get(MANAGED_BY_LABEL, MANAGED_BY_LABEL),
            OWNERSHIP_TAG_KEY: self.ownership_tags[OWNERSHIP_TAG_KEY],
        }


class NormalizedRateLimit(BaseModel):
    policy_name: str
    workspace: str
    endpoint: str
    limits: list[RateLimitPolicy]
    fallback_enabled: bool | None = None
    ownership_tags: dict[str, str]
