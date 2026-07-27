from __future__ import annotations

import os
from pathlib import Path

from gateway_policy.clients import ClientBundle, build_client_bundle
from gateway_policy.config import load_policy_file
from gateway_policy.governor.state import StateStore
from gateway_policy.governor.store import GovernorStateStore, LakebaseStateStore
from gateway_policy.models import GatewayPolicyBundle, SessionBudgetPolicy


def load_runtime_bundle(policy_file: Path) -> GatewayPolicyBundle:
    return load_policy_file(policy_file)


def build_runtime_clients(
    bundle: GatewayPolicyBundle,
    profile: str | None = None,
) -> ClientBundle:
    account_profile = profile or bundle.spec.account.profile
    workspace_profiles = {workspace.name: workspace.profile for workspace in bundle.spec.workspaces}
    return build_client_bundle(
        account_profile=account_profile,
        account_id=bundle.spec.account.account_id,
        workspace_profiles=workspace_profiles,
    )


def open_state_store(state_path: Path) -> StateStore:
    return StateStore(state_path)


def open_governor_state_store(state_path: Path) -> GovernorStateStore:
    if os.environ.get("LAKEBASE_ENDPOINT"):
        return LakebaseStateStore.from_databricks_app_env()
    return StateStore(state_path)


def session_policy_map(bundle: GatewayPolicyBundle) -> dict[str, SessionBudgetPolicy]:
    return {policy.name: policy for policy in bundle.spec.session_budgets}
