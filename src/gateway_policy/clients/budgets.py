from __future__ import annotations

from typing import Any, cast

from databricks.sdk import AccountClient

from gateway_policy import MANAGED_BY_LABEL, OWNERSHIP_TAG_KEY
from gateway_policy.models import NormalizedBudget, ThresholdAction


class BudgetApiError(Exception):
    """Raised when budget API operations fail."""


class BudgetClient:
    def __init__(self, account: AccountClient, account_id: str) -> None:
        self._account = account
        self._account_id = account_id

    def list_managed(self, bundle_name: str) -> list[dict[str, Any]]:
        budgets: list[dict[str, Any]] = []
        page_token: str | None = None
        while True:
            response = self._account.api_client.do(
                "GET",
                f"/api/2.1/accounts/{self._account_id}/budgets",
                query={"page_token": page_token} if page_token else None,
            )
            for budget in response.get("budgets", []):
                if self._is_managed(budget, bundle_name):
                    budgets.append(budget)
            page_token = response.get("next_page_token")
            if not page_token:
                break
        return budgets

    def list_all(self) -> list[dict[str, Any]]:
        budgets: list[dict[str, Any]] = []
        page_token: str | None = None
        while True:
            response = self._account.api_client.do(
                "GET",
                f"/api/2.1/accounts/{self._account_id}/budgets",
                query={"page_token": page_token} if page_token else None,
            )
            budgets.extend(response.get("budgets", []))
            page_token = response.get("next_page_token")
            if not page_token:
                break
        return budgets

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self._account.api_client.do(
                "POST",
                f"/api/2.1/accounts/{self._account_id}/budgets",
                body={"budget": payload},
            ),
        )

    def update(self, budget_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self._account.api_client.do(
                "PATCH",
                f"/api/2.1/accounts/{self._account_id}/budgets/{budget_id}",
                body={"budget": payload},
            ),
        )

    def delete(self, budget_id: str) -> None:
        self._account.api_client.do(
            "DELETE",
            f"/api/2.1/accounts/{self._account_id}/budgets/{budget_id}",
        )

    @staticmethod
    def _is_managed(budget: dict[str, Any], bundle_name: str) -> bool:
        tags = BudgetClient._extract_tags(budget)
        return (
            tags.get(MANAGED_BY_LABEL) == "gateway-policy"
            and tags.get(OWNERSHIP_TAG_KEY) == bundle_name
        )

    @staticmethod
    def _extract_tags(budget: dict[str, Any]) -> dict[str, str]:
        tags: dict[str, str] = {}
        for tag in budget.get("filter", {}).get("tags", []):
            key = tag.get("key")
            values = tag.get("value", {}).get("values", [])
            if key and values:
                tags[key] = values[0]
        return tags


def budget_to_api_payload(budget: NormalizedBudget) -> dict[str, Any]:
    tags = dict(budget.tags)
    tags.update(budget.ownership_marker())

    alert_configurations = [
        _threshold_to_alert(threshold, per_user=False) for threshold in budget.shared_thresholds
    ]
    if budget.per_user_threshold is not None:
        alert_configurations.append(_threshold_to_alert(budget.per_user_threshold, per_user=True))

    payload: dict[str, Any] = {
        "display_name": budget.display_name,
        "filter": {
            "tags": [
                {
                    "key": key,
                    "value": {"operator": "IN", "values": [value]},
                }
                for key, value in sorted(tags.items())
            ],
        },
        "alert_configurations": alert_configurations,
    }

    if budget.workspace_ids:
        payload["filter"]["workspace_id"] = {
            "operator": "IN",
            "values": budget.workspace_ids,
        }

    if budget.per_user_overrides:
        payload["per_user_overrides"] = [
            {
                "principal": override.principals[0],
                "quantity_threshold": str(override.amount_usd),
                "block_usage": override.block_usage,
            }
            for override in budget.per_user_overrides
        ]

    return payload


def _threshold_to_alert(threshold: ThresholdAction, per_user: bool) -> dict[str, Any]:
    alert: dict[str, Any] = {
        "trigger_type": "CUMULATIVE_SPENDING_EXCEEDED",
        "quantity_threshold": str(threshold.amount_usd),
        "quantity_type": "LIST_PRICE_DOLLARS_USD",
        "time_period": "MONTH",
        "action_configurations": [
            {
                "action_type": "EMAIL_NOTIFICATION",
                "target": email,
            }
            for email in threshold.emails
        ],
    }
    if per_user:
        alert["scope"] = "PER_USER"
    if threshold.block_usage:
        alert["block_usage"] = True
    return alert


def canonical_budget_state(budget: NormalizedBudget) -> dict[str, Any]:
    return {
        "display_name": budget.display_name,
        "resource_type": budget.resource_type.value,
        "workspace_ids": sorted(budget.workspace_ids),
        "tags": dict(sorted(budget.tags.items())),
        "shared_thresholds": [
            {
                "amount_usd": str(threshold.amount_usd),
                "emails": threshold.emails,
                "block_usage": threshold.block_usage,
            }
            for threshold in budget.shared_thresholds
        ],
        "per_user_threshold": (
            {
                "amount_usd": str(budget.per_user_threshold.amount_usd),
                "emails": budget.per_user_threshold.emails,
                "block_usage": budget.per_user_threshold.block_usage,
            }
            if budget.per_user_threshold
            else None
        ),
        "per_user_overrides": [
            {
                "principals": override.principals,
                "amount_usd": str(override.amount_usd),
                "block_usage": override.block_usage,
            }
            for override in budget.per_user_overrides
        ],
        "ownership": budget.ownership_marker(),
    }


def canonical_budget_from_api(budget: dict[str, Any]) -> dict[str, Any]:
    shared_thresholds: list[dict[str, Any]] = []
    per_user_threshold: dict[str, Any] | None = None
    for alert in budget.get("alert_configurations", []):
        threshold = {
            "amount_usd": alert.get("quantity_threshold"),
            "emails": [
                action.get("target")
                for action in alert.get("action_configurations", [])
                if action.get("action_type") == "EMAIL_NOTIFICATION"
            ],
            "block_usage": bool(alert.get("block_usage", False)),
        }
        if alert.get("scope") == "PER_USER":
            per_user_threshold = threshold
        else:
            shared_thresholds.append(threshold)

    workspace_ids = budget.get("filter", {}).get("workspace_id", {}).get("values", [])
    tags = BudgetClient._extract_tags(budget)
    ownership = {
        MANAGED_BY_LABEL: tags.get(MANAGED_BY_LABEL),
        OWNERSHIP_TAG_KEY: tags.get(OWNERSHIP_TAG_KEY),
    }
    for key in (MANAGED_BY_LABEL, OWNERSHIP_TAG_KEY):
        tags.pop(key, None)

    return {
        "display_name": budget.get("display_name"),
        "resource_type": tags.get("resource_type", "unity_ai_gateway"),
        "workspace_ids": sorted(workspace_ids),
        "tags": dict(sorted(tags.items())),
        "shared_thresholds": shared_thresholds,
        "per_user_threshold": per_user_threshold,
        "per_user_overrides": budget.get("per_user_overrides", []),
        "ownership": ownership,
        "budget_configuration_id": budget.get("budget_configuration_id"),
    }


def budgets_equal(desired: dict[str, Any], live: dict[str, Any]) -> bool:
    comparable_keys = [
        "display_name",
        "resource_type",
        "workspace_ids",
        "tags",
        "shared_thresholds",
        "per_user_threshold",
        "per_user_overrides",
    ]
    return all(desired.get(key) == live.get(key) for key in comparable_keys)


def find_budget_by_policy_name(
    budgets: list[dict[str, Any]], policy_name: str
) -> dict[str, Any] | None:
    for budget in budgets:
        tags = BudgetClient._extract_tags(budget)
        if tags.get("policy_name") == policy_name:
            return budget
    return None


def with_policy_name_tag(payload: dict[str, Any], policy_name: str) -> dict[str, Any]:
    tags = payload.setdefault("filter", {}).setdefault("tags", [])
    tags.append(
        {
            "key": "policy_name",
            "value": {"operator": "IN", "values": [policy_name]},
        }
    )
    return payload


def ensure_resource_type_tag(payload: dict[str, Any], resource_type: str) -> dict[str, Any]:
    tags = payload.setdefault("filter", {}).setdefault("tags", [])
    tags.append(
        {
            "key": "resource_type",
            "value": {"operator": "IN", "values": [resource_type]},
        }
    )
    return payload
