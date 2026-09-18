from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any
from uuid import uuid4

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse

from gateway_policy.models import SessionBudgetPolicy
from gateway_policy.proxy.compatibility import ToolCallMetadata
from gateway_policy.proxy.metrics import metrics
from gateway_policy.proxy.session import SessionManager, SessionRecord
from gateway_policy.proxy.store import SessionStateStore
from gateway_policy.proxy.tokens import SessionTokenError, verify_session_token


def create_app(
    session_manager: SessionManager,
    store: SessionStateStore,
    upstream_headers: dict[str, str],
    default_upstream_base_url: str,
    session_policies: dict[str, SessionBudgetPolicy],
    session_token_secret: str,
    max_output_tokens_default: int = 1024,
    upstream_headers_provider: Callable[[], dict[str, str]] | None = None,
    require_session: bool = False,
    trusted_identity_header: str | None = None,
    upstream_base_urls: dict[str, str] | None = None,
    enforce_policy_endpoint: bool = False,
) -> FastAPI:
    app = FastAPI(title="Gateway Policy Proxy")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready")
    def ready() -> dict[str, str]:
        if store.is_proxy_blocked():
            return {"status": "blocked"}
        return {"status": "ready"}

    @app.get("/metrics")
    def prometheus_metrics() -> PlainTextResponse:
        return PlainTextResponse(metrics.to_prometheus(), media_type="text/plain")

    @app.post("/api/sessions")
    @app.post("/sessions")
    def create_session(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
        policy_name = str(payload["policy_name"])
        if trusted_identity_header:
            identity = _resolve_trusted_identity(request, trusted_identity_header)
        else:
            identity = str(payload["identity"])
        project = payload.get("project")
        session = session_manager.create_session(policy_name, identity, project)
        token = session_manager.issue_token(session.session_id)
        response = session_manager.remaining_budget(session.session_id)
        response["session_token"] = token
        return response

    def verify_session_access(
        session_id: str,
        authorization: str | None = Header(default=None),
        x_gateway_session_token: str | None = Header(
            default=None,
            alias="X-Gateway-Session-Token",
        ),
    ) -> None:
        _require_matching_session_token(
            authorization,
            x_gateway_session_token,
            session_id,
            session_token_secret,
            require_session,
        )

    @app.get("/api/sessions/{session_id}")
    @app.get("/sessions/{session_id}")
    def show_session(
        session_id: str,
        _: None = Depends(verify_session_access),
    ) -> dict[str, Any]:
        return session_manager.remaining_budget(session_id)

    @app.delete("/api/sessions/{session_id}")
    @app.delete("/sessions/{session_id}")
    def close_session(
        session_id: str,
        _: None = Depends(verify_session_access),
    ) -> dict[str, str]:
        session_manager.close_session(session_id)
        return {"status": "closed", "session_id": session_id}

    def register_openai_route(route_path: str, upstream_path: str) -> None:
        @app.post(route_path)
        async def proxy_openai(
            request: Request,
            authorization: str | None = Header(default=None),
            x_gateway_session_token: str | None = Header(
                default=None,
                alias="X-Gateway-Session-Token",
            ),
            x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
            x_request_id: str | None = Header(default=None, alias="X-Request-Id"),
            x_idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
        ) -> Any:
            return await _proxy_openai_request(
                request=request,
                path=upstream_path,
                authorization=authorization,
                session_token=x_gateway_session_token,
                session_id=x_session_id,
                request_id=x_request_id or str(uuid4()),
                idempotency_key=x_idempotency_key,
                upstream_headers=upstream_headers,
                default_upstream_base_url=default_upstream_base_url,
                session_manager=session_manager,
                store=store,
                session_policies=session_policies,
                session_token_secret=session_token_secret,
                max_output_tokens_default=max_output_tokens_default,
                upstream_headers_provider=upstream_headers_provider,
                require_session=require_session,
                upstream_base_urls=upstream_base_urls,
                enforce_policy_endpoint=enforce_policy_endpoint,
            )

    for openai_path in ("/v1/chat/completions", "/v1/responses", "/v1/embeddings"):
        register_openai_route(openai_path, openai_path)
        register_openai_route(f"/api{openai_path}", openai_path)

    return app


async def _proxy_openai_request(
    request: Request,
    path: str,
    authorization: str | None,
    session_token: str | None,
    session_id: str | None,
    request_id: str,
    idempotency_key: str | None,
    upstream_headers: dict[str, str],
    default_upstream_base_url: str,
    session_manager: SessionManager,
    store: SessionStateStore,
    session_policies: dict[str, SessionBudgetPolicy],
    session_token_secret: str,
    max_output_tokens_default: int,
    upstream_headers_provider: Callable[[], dict[str, str]] | None,
    require_session: bool,
    upstream_base_urls: dict[str, str] | None,
    enforce_policy_endpoint: bool,
) -> Any:
    metrics.requests_total += 1
    session_id = _resolve_session_id(
        authorization,
        session_token,
        session_id,
        session_token_secret,
        allow_unsigned_session_id=not require_session,
    )
    if require_session and session_id is None:
        metrics.rejections_total += 1
        raise HTTPException(status_code=401, detail="a valid session token is required")
    session = session_manager.get_session(session_id) if session_id else None
    policy = session_policies.get(session.policy_name) if session else None
    cache_key = f"{session_id or 'anonymous'}:{idempotency_key}" if idempotency_key else None
    if cache_key is not None:
        cached = store.get_idempotent_response(cache_key)
        if cached is not None:
            return JSONResponse(content=cached)
    block_identity = session.identity if session else None
    if store.is_proxy_blocked(block_identity):
        metrics.rejections_total += 1
        raise HTTPException(status_code=429, detail="governor blocked proxy traffic")

    body = await request.json()
    body = _sanitize_for_upstream(body)
    tool_metadata = ToolCallMetadata(store, session_id)
    tool_metadata.restore(body)
    model = str(body.get("model", "unknown"))
    if enforce_policy_endpoint and policy is not None:
        model = policy.endpoint
        body["model"] = model
    stream = bool(body.get("stream", False))
    max_tokens = int(body.get("max_tokens", max_output_tokens_default))

    upstream_base_url = (upstream_base_urls or {}).get(path, default_upstream_base_url).rstrip("/")
    if upstream_base_url.endswith("/invocations"):
        if path != "/v1/chat/completions":
            raise HTTPException(
                status_code=400, detail="this upstream supports Chat Completions only"
            )
        url = upstream_base_url
    else:
        url = upstream_base_url + path

    reservation_id: str | None = None
    if session_id:
        try:
            reservation_id, _ = session_manager.reserve(session_id, request_id, model, max_tokens)
            metrics.reservations_total += 1
        except RuntimeError as exc:
            metrics.rejections_total += 1
            raise HTTPException(
                status_code=402,
                detail={"error": "session_budget_exhausted", "message": str(exc)},
            ) from exc
        except Exception as exc:
            if policy is None or policy.fail_mode == "fail_closed":
                metrics.rejections_total += 1
                raise HTTPException(
                    status_code=503,
                    detail={"error": "session_budget_unavailable", "message": str(exc)},
                ) from exc
            reservation_id = None

    request_tags = _build_request_tags(body, session, policy, request_id)
    headers = {
        **upstream_headers,
        **(upstream_headers_provider() if upstream_headers_provider else {}),
    }
    if (
        upstream_headers_provider is None
        and authorization
        and not authorization.lower().startswith("bearer gpst_")
    ):
        headers["Authorization"] = authorization
    headers["Databricks-Ai-Gateway-Request-Tags"] = json.dumps(request_tags)

    if stream:
        return await _stream_response(
            url,
            headers,
            body,
            session_manager,
            session_id,
            reservation_id,
            model,
            tool_metadata,
        )
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(url, headers=headers, json=body)
        if response.status_code >= 400:
            if session_id and reservation_id:
                session_manager.finalize(reservation_id, model, 0, 0, session_id)
            try:
                payload = response.json()
            except ValueError:
                payload = {"error": response.text}
            return JSONResponse(status_code=response.status_code, content=payload)
        payload = response.json()
        tool_metadata.observe(payload)
        if session_id and reservation_id:
            usage = payload.get("usage", {})
            session_manager.finalize(
                reservation_id,
                model,
                int(usage.get("prompt_tokens", 0)),
                int(usage.get("completion_tokens", 0)),
                session_id,
            )
        if cache_key is not None:
            store.store_idempotent_response(cache_key, payload)
        return JSONResponse(content=payload)


def _resolve_trusted_identity(request: Request, trusted_identity_header: str) -> str:
    identity_headers = [name.strip() for name in trusted_identity_header.split(",") if name.strip()]
    for name in identity_headers:
        value = request.headers.get(name)
        if value:
            return value
    raise HTTPException(
        status_code=401,
        detail=f"missing trusted identity header: {', '.join(identity_headers)}",
    )


def _resolve_session_id(
    authorization: str | None,
    session_token: str | None,
    session_id: str | None,
    secret: str,
    allow_unsigned_session_id: bool = True,
) -> str | None:
    if session_id and allow_unsigned_session_id:
        return session_id
    if session_token:
        token = session_token.removeprefix("gpst_")
        try:
            return verify_session_token(token, secret)
        except SessionTokenError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
    if authorization and authorization.lower().startswith("bearer gpst_"):
        token = authorization.split(" ", maxsplit=1)[1].removeprefix("gpst_")
        try:
            return verify_session_token(token, secret)
        except SessionTokenError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
    return None


def _require_matching_session_token(
    authorization: str | None,
    session_token: str | None,
    session_id: str,
    secret: str,
    required: bool,
) -> None:
    if not required:
        return
    resolved = _resolve_session_id(
        authorization,
        session_token,
        None,
        secret,
        allow_unsigned_session_id=False,
    )
    if resolved != session_id:
        raise HTTPException(status_code=403, detail="session token does not match session")


def _build_request_tags(
    body: dict[str, Any],
    session: SessionRecord | None,
    policy: SessionBudgetPolicy | None,
    request_id: str,
) -> dict[str, str]:
    tags = {
        "session_id": session.session_id if session else "",
        "request_id": request_id,
        "cost_policy": session.policy_name if session else "",
        "project": session.project or "" if session else "",
    }
    metadata = body.get("metadata", {})
    if isinstance(metadata, dict) and policy is not None:
        for key in policy.allowed_request_tag_keys:
            if key in metadata:
                tags[key] = str(metadata[key])
    return tags


def _sanitize_for_upstream(body: dict[str, Any]) -> dict[str, Any]:
    """Strip OpenAI-specific fields that Gemini (via Databricks AI Gateway) rejects."""
    body = dict(body)
    # stream_options is OpenAI-only; Gemini rejects it
    body.pop("stream_options", None)
    # Recursively strip JSON Schema meta-fields from tool parameter schemas
    if "tools" in body:
        body["tools"] = [_sanitize_tool(t) for t in body["tools"]]
    return body


def _sanitize_tool(tool: Any) -> Any:
    if not isinstance(tool, dict):
        return tool
    tool = dict(tool)
    if "function" in tool and isinstance(tool["function"], dict):
        fn = dict(tool["function"])
        if "parameters" in fn:
            fn["parameters"] = _strip_json_schema_meta(fn["parameters"])
        tool["function"] = fn
    return tool


def _strip_json_schema_meta(schema: Any) -> Any:
    """Recursively remove $schema, $defs, and resolve $ref stubs from a JSON Schema object."""
    _BLOCKED = {"$schema", "$defs", "$ref", "$id", "$comment"}
    if not isinstance(schema, dict):
        return schema
    return {k: _strip_json_schema_meta(v) for k, v in schema.items() if k not in _BLOCKED}


async def _stream_response(
    url: str,
    headers: dict[str, str],
    body: dict[str, Any],
    session_manager: SessionManager,
    session_id: str | None,
    reservation_id: str | None,
    model: str,
    tool_metadata: ToolCallMetadata,
) -> StreamingResponse | JSONResponse:
    client = httpx.AsyncClient(timeout=120.0)
    try:
        upstream_request = client.build_request("POST", url, headers=headers, json=body)
        response = await client.send(upstream_request, stream=True)
    except Exception:
        await client.aclose()
        if session_id and reservation_id:
            session_manager.finalize(reservation_id, model, 0, 0, session_id)
        raise
    if response.status_code >= 400:
        try:
            await response.aread()
            try:
                payload = response.json()
            except ValueError:
                payload = {"error": response.text}
            return JSONResponse(status_code=response.status_code, content=payload)
        finally:
            await response.aclose()
            await client.aclose()
            if session_id and reservation_id:
                session_manager.finalize(reservation_id, model, 0, 0, session_id)

    async def event_generator() -> Any:
        usage: dict[str, int] = {"prompt_tokens": 0, "completion_tokens": 0}
        try:
            async for line in response.aiter_lines():
                if line.startswith("data:"):
                    try:
                        payload = json.loads(line.removeprefix("data:").strip())
                    except json.JSONDecodeError:
                        payload = {}
                    if isinstance(payload, dict):
                        tool_metadata.observe(payload)
                    candidate = payload.get("usage") if isinstance(payload, dict) else None
                    if isinstance(candidate, dict):
                        for field in usage:
                            if candidate.get(field) is not None:
                                usage[field] = int(candidate[field])
                yield line + "\n"
        except Exception:
            metrics.stream_disconnects_total += 1
            raise
        finally:
            await response.aclose()
            await client.aclose()
            if session_id and reservation_id:
                session_manager.finalize(
                    reservation_id,
                    model,
                    usage["prompt_tokens"],
                    usage["completion_tokens"],
                    session_id,
                )

    return StreamingResponse(event_generator(), media_type="text/event-stream")
