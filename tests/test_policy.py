from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
from pathlib import Path

import pytest

from gateway_policy.clients.budgets import (
    budget_to_api_payload,
    budgets_equal,
    with_policy_name_tag,
)
from gateway_policy.config import PolicyConfigError, load_policy_file, normalize_bundle
from gateway_policy.models import (
    NormalizedBudget,
    PlanActionType,
    ResourceType,
    ThresholdAction,
)
from gateway_policy.planner import Planner

FIXTURES = Path(__file__).parent / "fixtures"


def test_load_valid_policy() -> None:
    bundle = load_policy_file(FIXTURES / "valid-policy.yaml")
    assert bundle.metadata.name == "test-bundle"
    assert len(bundle.spec.budgets) == 1


def test_reject_non_genie_block_usage() -> None:
    with pytest.raises(PolicyConfigError):
        load_policy_file(FIXTURES / "invalid-block-policy.yaml")


def test_budget_payload_translation() -> None:
    budget = NormalizedBudget(
        policy_name="gateway-soft-cap",
        display_name="Gateway soft cap",
        resource_type=ResourceType.UNITY_AI_GATEWAY,
        workspace_ids=[1234567890123456],
        tags={"team": "ml"},
        shared_thresholds=[
            ThresholdAction(amountUsd=Decimal("1000"), emails=["finops@example.com"])
        ],
        per_user_threshold=None,
        per_user_overrides=[],
        ownership_tags={"managed_by": "gateway-policy", "gateway_policy_bundle": "test-bundle"},
    )
    payload = with_policy_name_tag(budget_to_api_payload(budget), budget.policy_name)
    assert payload["display_name"] == "Gateway soft cap"
    assert payload["filter"]["workspace_id"]["values"] == [1234567890123456]
    assert len(payload["alert_configurations"]) == 1
    assert payload["alert_configurations"][0]["quantity_threshold"] == "1000"


def test_offline_plan_is_noop_for_budgets() -> None:
    bundle = load_policy_file(FIXTURES / "valid-policy.yaml")
    planner = Planner(bundle)
    plan = planner.plan()
    assert all(action.action == PlanActionType.NO_OP for action in plan.actions)


def test_budget_drift_detection() -> None:
    desired = {
        "display_name": "Gateway soft cap",
        "resource_type": "unity_ai_gateway",
        "workspace_ids": [1],
        "tags": {"team": "ml"},
        "shared_thresholds": [
            {"amount_usd": "1000", "emails": ["finops@example.com"], "block_usage": False}
        ],
        "per_user_threshold": None,
        "per_user_overrides": [],
        "ownership": {"managed_by": "gateway-policy", "gateway_policy_bundle": "test"},
    }
    live = deepcopy(desired)
    live["shared_thresholds"][0]["amount_usd"] = "900"
    assert not budgets_equal(desired, live)


def test_normalize_bundle_workspace_id() -> None:
    bundle = load_policy_file(FIXTURES / "valid-policy.yaml")
    budgets, rate_limits = normalize_bundle(bundle)
    assert budgets[0].workspace_ids == [1234567890123456]
    assert rate_limits[0].endpoint == "main.serving.chat"
