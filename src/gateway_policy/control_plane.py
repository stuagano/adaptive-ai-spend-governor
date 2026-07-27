from __future__ import annotations

import os
from dataclasses import asdict
from typing import Any, cast

import uvicorn
from databricks.sdk import WorkspaceClient
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse

from gateway_policy.governor.engine import GovernorEngine
from gateway_policy.governor.store import GovernorStateStore
from gateway_policy.models import GatewayPolicyBundle
from gateway_policy.native_runtime import build_native_governor_runtime
from gateway_policy.omnigent import render_managed_omnigent_config
from gateway_policy.proxy.app import create_app as create_proxy_app
from gateway_policy.proxy.session import SessionManager
from gateway_policy.proxy.store import SessionStateStore
from gateway_policy.runtime import session_policy_map


def create_control_plane(
    bundle: GatewayPolicyBundle,
    store: GovernorStateStore,
    engine: GovernorEngine,
    allow_apply: bool = False,
) -> FastAPI:
    app = FastAPI(title="Adaptive AI Spend Governor", version="1.0")

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return """
        <!doctype html>
        <html>
          <head><title>Adaptive AI Spend Governor</title></head>
          <body style="font-family:system-ui;max-width:900px;margin:40px auto">
            <h1>Adaptive AI Spend Governor</h1>
            <p>Databricks-native control plane for managed Omnigent policies,
               Unity AI Gateway budgets, and adaptive QPM/TPM.</p>
            <ul>
              <li><a href="/docs">Interactive API</a></li>
              <li><a href="/api/governors">Governor status</a></li>
              <li><a href="/api/audit">Recent decisions</a></li>
              <li><a href="/api/omnigent">Managed Omnigent config</a></li>
            </ul>
          </body>
        </html>
        """

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "bundle": bundle.metadata.name,
            "state_backend": type(store).__name__,
            "apply_enabled": allow_apply,
        }

    @app.get("/api/governors")
    def governors() -> list[dict[str, Any]]:
        return [engine.status(governor.name) for governor in bundle.spec.governors]

    @app.post("/api/governors/{governor_name}/evaluate")
    def evaluate_governor(
        governor_name: str,
        apply: bool = Query(default=False),
    ) -> dict[str, Any]:
        if apply and not allow_apply:
            raise HTTPException(
                status_code=403,
                detail="mutation is disabled; set GATEWAY_POLICY_ENABLE_APPLY=true",
            )
        try:
            return asdict(engine.evaluate(governor_name, apply=apply))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/audit")
    def audit(limit: int = Query(default=100, ge=1, le=1000)) -> list[dict[str, Any]]:
        return store.list_audit(limit)

    @app.get("/api/omnigent")
    def omnigent() -> dict[str, Any]:
        if bundle.spec.omnigent is None:
            raise HTTPException(status_code=404, detail="Omnigent policy is not configured")
        return render_managed_omnigent_config(bundle.spec.omnigent)

    return app


def build_control_plane_from_env() -> FastAPI:
    runtime = build_native_governor_runtime()
    control_plane = create_control_plane(
        runtime.bundle,
        runtime.store,
        runtime.engine,
        allow_apply=os.environ.get("GATEWAY_POLICY_ENABLE_APPLY", "false").lower() == "true",
    )
    policy_name = os.environ["GATEWAY_POLICY_SESSION_POLICY"]
    policies = session_policy_map(runtime.bundle)
    policy = policies[policy_name]
    store = cast(SessionStateStore, runtime.store)
    manager = SessionManager(
        store,
        policies,
        os.environ["GATEWAY_POLICY_SESSION_SECRET"],
    )
    workspace = WorkspaceClient()
    host = os.environ["DATABRICKS_HOST"].rstrip("/")
    proxy = create_proxy_app(
        session_manager=manager,
        store=store,
        upstream_headers={},
        default_upstream_base_url=policy.upstream_base_url,
        session_policies={policy.name: policy},
        session_token_secret=os.environ["GATEWAY_POLICY_SESSION_SECRET"],
        upstream_headers_provider=workspace.config.authenticate,
        require_session=True,
        trusted_identity_header="X-Forwarded-Email,X-Forwarded-User",
        upstream_base_urls={
            "/v1/chat/completions": f"{host}/ai-gateway/mlflow",
            "/v1/embeddings": f"{host}/ai-gateway/mlflow",
            "/v1/responses": f"{host}/ai-gateway/openai",
        },
        enforce_policy_endpoint=True,
    )
    control_plane.mount("/", proxy)
    return control_plane


app = build_control_plane_from_env()


def main() -> None:
    uvicorn.run(
        "gateway_policy.control_plane:app",
        host="0.0.0.0",
        port=int(os.environ.get("DATABRICKS_APP_PORT", "8000")),
    )


if __name__ == "__main__":
    main()
