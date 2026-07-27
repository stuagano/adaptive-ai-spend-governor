from __future__ import annotations

import os

from databricks.sdk import AccountClient, WorkspaceClient
from databricks.sdk.core import Config


class AuthError(Exception):
    """Raised when Databricks authentication cannot be resolved."""


def build_account_client(profile: str, account_id: str) -> AccountClient:
    config = Config(profile=profile, account_id=account_id)
    if not config.host:
        raise AuthError(
            "account host not configured. Set Databricks account profile with host and credentials."
        )
    return AccountClient(config=config)


def build_workspace_client(profile: str | None) -> WorkspaceClient:
    if profile:
        return WorkspaceClient(profile=profile)
    host = os.environ.get("DATABRICKS_HOST")
    if not host:
        raise AuthError("workspace profile or DATABRICKS_HOST is required for workspace API calls")
    return WorkspaceClient(host=host)
