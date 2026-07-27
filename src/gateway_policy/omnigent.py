from __future__ import annotations

from decimal import Decimal
from typing import Any

import yaml

from gateway_policy.models import OmnigentCostBudget, OmnigentPolicyConfig

SESSION_HANDLER = "omnigent.policies.builtins.cost.cost_budget"
DAILY_HANDLER = "omnigent.policies.builtins.cost.user_daily_cost_budget"


def render_managed_omnigent_config(config: OmnigentPolicyConfig) -> dict[str, Any]:
    """Render only handlers supported by managed Omnigent on Databricks."""
    policies: dict[str, Any] = {
        "session_budget": _render_cost_policy(
            SESSION_HANDLER,
            config.session_cost_budget,
        )
    }
    if config.user_daily_cost_budget is not None:
        policies["daily_budget"] = _render_cost_policy(
            DAILY_HANDLER,
            config.user_daily_cost_budget,
        )
    return {"policies": policies}


def render_managed_omnigent_yaml(config: OmnigentPolicyConfig) -> str:
    return yaml.safe_dump(
        render_managed_omnigent_config(config),
        sort_keys=False,
    )


def _render_cost_policy(handler: str, budget: OmnigentCostBudget) -> dict[str, Any]:
    arguments: dict[str, Any] = {
        "max_cost_usd": _number(budget.max_cost_usd),
        "ask_thresholds_usd": [_number(value) for value in budget.ask_thresholds_usd],
    }
    if budget.expensive_models:
        arguments["expensive_models"] = budget.expensive_models
    return {
        "type": "function",
        "handler": handler,
        "factory_params": arguments,
    }


def _number(value: Decimal) -> int | float:
    integral = value.to_integral_value()
    if value == integral:
        return int(integral)
    return float(value)
