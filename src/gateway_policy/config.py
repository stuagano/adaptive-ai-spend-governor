from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from gateway_policy import MANAGED_BY_LABEL, OWNERSHIP_TAG_KEY
from gateway_policy.models import (
    GatewayPolicyBundle,
    NormalizedBudget,
    NormalizedRateLimit,
    PolicySpec,
)


class PolicyConfigError(Exception):
    """Raised when a policy file cannot be loaded or validated."""


def _expand_environment(contents: str) -> str:
    pattern = re.compile(r"\$\{([A-Z][A-Z0-9_]*)\}")

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        value = os.environ.get(name)
        if value is None:
            raise PolicyConfigError(f"required environment variable is not set: {name}")
        return value

    return pattern.sub(replace, contents)


def load_policy_file(path: Path) -> GatewayPolicyBundle:
    if not path.exists():
        raise PolicyConfigError(f"policy file not found: {path}")
    try:
        raw = yaml.safe_load(_expand_environment(path.read_text(encoding="utf-8")))
    except yaml.YAMLError as exc:
        raise PolicyConfigError(f"invalid YAML in {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise PolicyConfigError(f"policy root must be a mapping: {path}")
    try:
        return GatewayPolicyBundle.model_validate(raw)
    except ValidationError as exc:
        raise PolicyConfigError(f"policy validation failed for {path}:\n{exc}") from exc


def normalize_bundle(
    bundle: GatewayPolicyBundle,
) -> tuple[list[NormalizedBudget], list[NormalizedRateLimit]]:
    workspace_name_to_id = resolve_workspace_ids(bundle.spec)
    ownership = {
        MANAGED_BY_LABEL: bundle.metadata.managed_by,
        OWNERSHIP_TAG_KEY: bundle.metadata.name,
    }

    budgets: list[NormalizedBudget] = []
    for budget in bundle.spec.budgets:
        workspace_ids = [
            workspace_name_to_id[name] for name in budget.workspaces if name in workspace_name_to_id
        ]
        budgets.append(
            NormalizedBudget(
                policy_name=budget.name,
                display_name=budget.display_name,
                resource_type=budget.resource_type,
                workspace_ids=workspace_ids,
                tags=dict(budget.tags),
                shared_thresholds=budget.shared_thresholds,
                per_user_threshold=budget.per_user_threshold,
                per_user_overrides=budget.per_user_overrides,
                ownership_tags=ownership,
            )
        )

    rate_limits: list[NormalizedRateLimit] = []
    for rate_limit in bundle.spec.rate_limits:
        rate_limits.append(
            NormalizedRateLimit(
                policy_name=rate_limit.name,
                workspace=rate_limit.workspace,
                endpoint=rate_limit.endpoint,
                limits=rate_limit.limits,
                fallback_enabled=rate_limit.fallback_enabled,
                ownership_tags=ownership,
            )
        )

    return budgets, rate_limits


def resolve_workspace_ids(spec: PolicySpec) -> dict[str, int]:
    """Resolve workspace names to numeric IDs when encoded in host or name."""
    mapping: dict[str, int] = {}
    for workspace in spec.workspaces:
        workspace_id = extract_workspace_id(workspace.host, workspace.name)
        if workspace_id is not None:
            mapping[workspace.name] = workspace_id
    return mapping


def extract_workspace_id(host: str | None, name: str) -> int | None:
    if host:
        marker = "adb-"
        if marker in host:
            start = host.index(marker) + len(marker)
            digits = []
            for char in host[start:]:
                if char.isdigit():
                    digits.append(char)
                else:
                    break
            if digits:
                return int("".join(digits))
    if name.isdigit():
        return int(name)
    return None


def policy_to_dict(bundle: GatewayPolicyBundle) -> dict[str, Any]:
    return bundle.model_dump(by_alias=True, mode="json")
