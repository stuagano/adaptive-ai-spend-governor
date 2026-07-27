from __future__ import annotations

from typing import Any

from gateway_policy.clients.budgets import (
    BudgetClient,
    budget_to_api_payload,
    budgets_equal,
    canonical_budget_from_api,
    canonical_budget_state,
    ensure_resource_type_tag,
    find_budget_by_policy_name,
    with_policy_name_tag,
)
from gateway_policy.clients.rate_limits import (
    RateLimitClient,
    canonical_rate_limit_from_api,
    canonical_rate_limit_state,
    merge_gateway_rate_limits,
    rate_limits_equal,
)
from gateway_policy.config import normalize_bundle
from gateway_policy.models import (
    GatewayPolicyBundle,
    NormalizedBudget,
    NormalizedRateLimit,
    PlanAction,
    PlanActionType,
    PlanResult,
)


class Planner:
    def __init__(
        self,
        bundle: GatewayPolicyBundle,
        budget_client: BudgetClient | None = None,
        rate_limit_clients: dict[str, RateLimitClient] | None = None,
    ) -> None:
        self._bundle = bundle
        self._budget_client = budget_client
        self._rate_limit_clients = rate_limit_clients or {}
        self._budgets, self._rate_limits = normalize_bundle(bundle)

    def plan(self, prune: bool = False) -> PlanResult:
        actions: list[PlanAction] = []
        actions.extend(self._plan_budgets(prune=prune))
        actions.extend(self._plan_rate_limits(prune=prune))
        return PlanResult(bundle_name=self._bundle.metadata.name, actions=actions, summary={})

    def _plan_budgets(self, prune: bool) -> list[PlanAction]:
        if self._budget_client is None:
            return [
                PlanAction(
                    action=PlanActionType.NO_OP,
                    resource_type="budget",
                    resource_name=budget.policy_name,
                    details={"message": "offline mode: budget plan skipped"},
                )
                for budget in self._budgets
            ]

        live_managed = self._budget_client.list_managed(self._bundle.metadata.name)

        actions: list[PlanAction] = []
        desired_names = {budget.policy_name for budget in self._budgets}

        for budget in self._budgets:
            desired = canonical_budget_state(budget)
            live_item = find_budget_by_policy_name(live_managed, budget.policy_name)
            if live_item is None:
                actions.append(
                    PlanAction(
                        action=PlanActionType.CREATE,
                        resource_type="budget",
                        resource_name=budget.policy_name,
                        after=desired,
                        details={"display_name": budget.display_name},
                    )
                )
                continue

            live = canonical_budget_from_api(live_item)
            if budgets_equal(desired, live):
                actions.append(
                    PlanAction(
                        action=PlanActionType.NO_OP,
                        resource_type="budget",
                        resource_name=budget.policy_name,
                        before=live,
                        after=desired,
                    )
                )
            else:
                actions.append(
                    PlanAction(
                        action=PlanActionType.UPDATE,
                        resource_type="budget",
                        resource_name=budget.policy_name,
                        before=live,
                        after=desired,
                        details={"budget_configuration_id": live.get("budget_configuration_id")},
                    )
                )

        if prune:
            for live_item in live_managed:
                live = canonical_budget_from_api(live_item)
                policy_name = BudgetClient._extract_tags(live_item).get("policy_name")
                if policy_name and policy_name not in desired_names:
                    actions.append(
                        PlanAction(
                            action=PlanActionType.DELETE,
                            resource_type="budget",
                            resource_name=policy_name,
                            before=live,
                            details={
                                "budget_configuration_id": live.get("budget_configuration_id")
                            },
                        )
                    )

        return actions

    def _plan_rate_limits(self, prune: bool) -> list[PlanAction]:
        actions: list[PlanAction] = []
        desired_keys = {(item.workspace, item.endpoint) for item in self._rate_limits}

        for policy in self._rate_limits:
            desired = canonical_rate_limit_state(policy)
            client = self._rate_limit_clients.get(policy.workspace)
            if client is None:
                actions.append(
                    PlanAction(
                        action=PlanActionType.NO_OP,
                        resource_type="rate_limit",
                        resource_name=policy.policy_name,
                        workspace=policy.workspace,
                        details={"message": "offline mode: rate limit plan skipped"},
                    )
                )
                continue

            try:
                gateway = client.get_endpoint_gateway(policy.endpoint)
            except Exception as exc:  # noqa: BLE001 - surface API failure in plan
                actions.append(
                    PlanAction(
                        action=PlanActionType.CREATE,
                        resource_type="rate_limit",
                        resource_name=policy.policy_name,
                        workspace=policy.workspace,
                        after=desired,
                        details={"warning": f"endpoint lookup failed, treating as create: {exc}"},
                    )
                )
                continue

            live = canonical_rate_limit_from_api(policy.workspace, policy.endpoint, gateway)
            if rate_limits_equal(desired, live):
                actions.append(
                    PlanAction(
                        action=PlanActionType.NO_OP,
                        resource_type="rate_limit",
                        resource_name=policy.policy_name,
                        workspace=policy.workspace,
                        before=live,
                        after=desired,
                    )
                )
            else:
                actions.append(
                    PlanAction(
                        action=PlanActionType.UPDATE,
                        resource_type="rate_limit",
                        resource_name=policy.policy_name,
                        workspace=policy.workspace,
                        before=live,
                        after=desired,
                    )
                )

        if prune:
            for workspace, client in self._rate_limit_clients.items():
                for endpoint_name in self._list_managed_endpoints(client, workspace):
                    if (workspace, endpoint_name) not in desired_keys:
                        gateway = client.get_endpoint_gateway(endpoint_name)
                        ownership = gateway.get("ownership_tags", {})
                        if ownership.get("gateway_policy_bundle") != self._bundle.metadata.name:
                            continue
                        live = canonical_rate_limit_from_api(workspace, endpoint_name, gateway)
                        actions.append(
                            PlanAction(
                                action=PlanActionType.DELETE,
                                resource_type="rate_limit",
                                resource_name=endpoint_name,
                                workspace=workspace,
                                before=live,
                            )
                        )

        return actions

    @staticmethod
    def _list_managed_endpoints(client: RateLimitClient, workspace: str) -> list[str]:
        _ = client, workspace
        return []


class Applier:
    def __init__(
        self,
        bundle: GatewayPolicyBundle,
        budget_client: BudgetClient,
        rate_limit_clients: dict[str, RateLimitClient],
    ) -> None:
        self._bundle = bundle
        self._budget_client = budget_client
        self._rate_limit_clients = rate_limit_clients
        self._budgets, self._rate_limits = normalize_bundle(bundle)

    def apply(self, plan: PlanResult) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        budget_lookup = {budget.policy_name: budget for budget in self._budgets}
        rate_lookup = {item.policy_name: item for item in self._rate_limits}

        for action in plan.actions:
            if action.action == PlanActionType.NO_OP:
                results.append(
                    {
                        "action": action.action.value,
                        "resource": action.resource_name,
                        "status": "skipped",
                    }
                )
                continue

            if action.resource_type == "budget":
                results.append(self._apply_budget_action(action, budget_lookup))
            else:
                results.append(self._apply_rate_limit_action(action, rate_lookup))

        return results

    def _apply_budget_action(
        self, action: PlanAction, budget_lookup: dict[str, NormalizedBudget]
    ) -> dict[str, Any]:
        if action.action == PlanActionType.DELETE:
            budget_id = action.details.get("budget_configuration_id")
            if not budget_id:
                return {
                    "action": action.action.value,
                    "resource": action.resource_name,
                    "status": "failed",
                    "error": "missing budget_configuration_id",
                }
            self._budget_client.delete(str(budget_id))
            return {
                "action": action.action.value,
                "resource": action.resource_name,
                "status": "deleted",
            }

        budget = budget_lookup[action.resource_name]
        payload = budget_to_api_payload(budget)
        with_policy_name_tag(payload, budget.policy_name)
        ensure_resource_type_tag(payload, budget.resource_type.value)

        if action.action == PlanActionType.CREATE:
            created = self._budget_client.create(payload)
            return {
                "action": action.action.value,
                "resource": action.resource_name,
                "status": "created",
                "budget_configuration_id": created.get("budget_configuration_id"),
            }

        budget_id = action.details.get("budget_configuration_id")
        if not budget_id:
            return {
                "action": action.action.value,
                "resource": action.resource_name,
                "status": "failed",
                "error": "missing budget_configuration_id for update",
            }
        updated = self._budget_client.update(str(budget_id), payload)
        return {
            "action": action.action.value,
            "resource": action.resource_name,
            "status": "updated",
            "budget_configuration_id": updated.get("budget_configuration_id"),
        }

    def _apply_rate_limit_action(
        self, action: PlanAction, rate_lookup: dict[str, NormalizedRateLimit]
    ) -> dict[str, Any]:
        policy = rate_lookup.get(action.resource_name)
        if policy is None and action.before:
            workspace = str(action.before.get("workspace"))
            endpoint = str(action.before.get("endpoint"))
        elif policy is not None:
            workspace = policy.workspace
            endpoint = policy.endpoint
        else:
            return {
                "action": action.action.value,
                "resource": action.resource_name,
                "status": "failed",
                "error": "unable to resolve endpoint for rate limit action",
            }

        client = self._rate_limit_clients[workspace]

        if action.action == PlanActionType.DELETE:
            gateway = client.get_endpoint_gateway(endpoint)
            gateway.pop("rate_limits", None)
            gateway.pop("ownership_tags", None)
            client.put_endpoint_gateway(endpoint, gateway)
            return {
                "action": action.action.value,
                "resource": action.resource_name,
                "status": "deleted",
            }

        if policy is None:
            return {
                "action": action.action.value,
                "resource": action.resource_name,
                "status": "failed",
                "error": "missing desired rate limit policy",
            }

        existing = client.get_endpoint_gateway(endpoint)
        merged = merge_gateway_rate_limits(
            existing,
            policy.limits,
            policy.ownership_tags,
            fallback_enabled=policy.fallback_enabled,
        )
        client.put_endpoint_gateway(endpoint, merged)
        status = "created" if action.action == PlanActionType.CREATE else "updated"
        return {"action": action.action.value, "resource": action.resource_name, "status": status}
