from __future__ import annotations

from typing import Any, cast

from databricks.sdk import WorkspaceClient

from gateway_policy.models import NormalizedRateLimit, RateLimitPolicy, RateLimitScope


class RateLimitApiError(Exception):
    """Raised when serving endpoint AI Gateway API operations fail."""


class RateLimitClient:
    def __init__(self, workspace: WorkspaceClient) -> None:
        self._workspace = workspace

    def get_endpoint_gateway(self, endpoint_name: str) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self._workspace.api_client.do(
                "GET",
                f"/api/2.0/serving-endpoints/{endpoint_name}/ai-gateway",
            ),
        )

    def put_endpoint_gateway(
        self,
        endpoint_name: str,
        ai_gateway: dict[str, Any],
    ) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self._workspace.api_client.do(
                "PUT",
                f"/api/2.0/serving-endpoints/{endpoint_name}/ai-gateway",
                body=ai_gateway,
            ),
        )


def policy_limits_to_api(limits: list[RateLimitPolicy]) -> list[dict[str, Any]]:
    api_limits: list[dict[str, Any]] = []
    for limit in limits:
        key = _scope_to_key(limit.scope)
        entry: dict[str, Any] = {
            "key": key,
            "renewal_period": "minute",
        }
        if limit.qpm is not None:
            entry["calls"] = limit.qpm
        if limit.tpm is not None:
            entry["tokens"] = limit.tpm
        if limit.principal is not None:
            entry["principal"] = limit.principal
        api_limits.append(entry)
    return api_limits


def _scope_to_key(scope: RateLimitScope) -> str:
    match scope:
        case RateLimitScope.ENDPOINT:
            return "endpoint"
        case RateLimitScope.USER:
            return "user"
        case RateLimitScope.GROUP:
            return "user_group"
        case RateLimitScope.SERVICE_PRINCIPAL:
            return "service_principal"
        case _ as unreachable:
            raise RateLimitApiError(f"unsupported rate limit scope: {unreachable}")


def canonical_rate_limit_state(policy: NormalizedRateLimit) -> dict[str, Any]:
    return {
        "workspace": policy.workspace,
        "endpoint": policy.endpoint,
        "limits": [
            {
                "scope": limit.scope.value,
                "principal": limit.principal,
                "qpm": limit.qpm,
                "tpm": limit.tpm,
            }
            for limit in policy.limits
        ],
        "fallback_enabled": policy.fallback_enabled,
        "ownership": policy.ownership_tags,
    }


def canonical_rate_limit_from_api(
    workspace: str, endpoint: str, ai_gateway: dict[str, Any]
) -> dict[str, Any]:
    return {
        "workspace": workspace,
        "endpoint": endpoint,
        "limits": gateway_rate_limits_from_api(ai_gateway),
        "fallback_enabled": ai_gateway.get("fallback_config", {}).get("enabled"),
        "ownership": ai_gateway.get("ownership_tags", {}),
        "ai_gateway": ai_gateway,
    }


def gateway_rate_limits_from_api(ai_gateway: dict[str, Any]) -> list[dict[str, object]]:
    return [
        {
            "scope": _key_to_scope(str(entry.get("key", "endpoint"))).value,
            "principal": entry.get("principal"),
            "qpm": entry.get("calls"),
            "tpm": entry.get("tokens"),
        }
        for entry in ai_gateway.get("rate_limits", [])
    ]


def _key_to_scope(key: str) -> RateLimitScope:
    match key:
        case "endpoint":
            return RateLimitScope.ENDPOINT
        case "user":
            return RateLimitScope.USER
        case "user_group":
            return RateLimitScope.GROUP
        case "service_principal":
            return RateLimitScope.SERVICE_PRINCIPAL
        case _:
            return RateLimitScope.ENDPOINT


def merge_gateway_rate_limits(
    existing_gateway: dict[str, Any],
    desired_limits: list[RateLimitPolicy],
    ownership_tags: dict[str, str],
    fallback_enabled: bool | None = None,
) -> dict[str, Any]:
    merged = dict(existing_gateway)
    merged["rate_limits"] = policy_limits_to_api(desired_limits)
    if fallback_enabled is not None:
        merged["fallback_config"] = {"enabled": fallback_enabled}
    merged["ownership_tags"] = ownership_tags
    return merged


def rate_limits_equal(desired: dict[str, Any], live: dict[str, Any]) -> bool:
    return desired.get("limits") == live.get("limits") and desired.get(
        "fallback_enabled"
    ) == live.get("fallback_enabled")
