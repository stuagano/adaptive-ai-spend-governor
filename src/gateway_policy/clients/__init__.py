from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from databricks.sdk import AccountClient, WorkspaceClient

from gateway_policy.clients.auth import build_account_client, build_workspace_client
from gateway_policy.clients.budgets import BudgetClient
from gateway_policy.clients.rate_limits import RateLimitClient


@dataclass
class ClientBundle:
    account: AccountClient
    account_id: str
    workspaces: dict[str, WorkspaceClient]
    budgets: BudgetClient
    rate_limits: dict[str, RateLimitClient]


class ClientFactory(Protocol):
    def build(
        self,
        account_profile: str,
        account_id: str,
        workspace_profiles: dict[str, str | None],
    ) -> ClientBundle: ...


class LiveClientFactory:
    def build(
        self,
        account_profile: str,
        account_id: str,
        workspace_profiles: dict[str, str | None],
    ) -> ClientBundle:
        account = build_account_client(account_profile, account_id)
        workspaces: dict[str, WorkspaceClient] = {}
        rate_limits: dict[str, RateLimitClient] = {}
        for name, profile in workspace_profiles.items():
            workspace = build_workspace_client(profile)
            workspaces[name] = workspace
            rate_limits[name] = RateLimitClient(workspace)
        return ClientBundle(
            account=account,
            account_id=account_id,
            workspaces=workspaces,
            budgets=BudgetClient(account, account_id),
            rate_limits=rate_limits,
        )


def build_client_bundle(
    account_profile: str,
    account_id: str,
    workspace_profiles: dict[str, str | None],
    factory: ClientFactory | None = None,
) -> ClientBundle:
    builder = factory or LiveClientFactory()
    return builder.build(account_profile, account_id, workspace_profiles)
