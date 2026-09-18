from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from gateway_policy.config import load_policy_file
from gateway_policy.governor.state import StateStore
from gateway_policy.proxy.app import create_app
from gateway_policy.proxy.compatibility import ToolCallMetadata
from gateway_policy.proxy.session import SessionManager
from gateway_policy.runtime import session_policy_map

FIXTURES = Path(__file__).parent / "fixtures"


class ChunkedStream(httpx.AsyncByteStream):
    def __init__(self, content: bytes) -> None:
        self.content = content
        self.closed = False

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for offset in range(0, len(self.content), 3):
            yield self.content[offset : offset + 3]

    async def aclose(self) -> None:
        self.closed = True


def proxy_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    handler: Callable[[httpx.Request], httpx.Response],
    upstream: str = "https://workspace.test/ai-gateway/mlflow",
) -> tuple[TestClient, SessionManager, str, str]:
    async_client = httpx.AsyncClient
    monkeypatch.setattr(
        "gateway_policy.proxy.app.httpx.AsyncClient",
        lambda **kwargs: async_client(transport=httpx.MockTransport(handler), **kwargs),
    )
    bundle = load_policy_file(FIXTURES / "governor-policy.yaml")
    store = StateStore(tmp_path / "state.db")
    manager = SessionManager(store, session_policy_map(bundle), "test-secret")
    session = manager.create_session("agent-session", "alice@example.com")
    app = create_app(
        session_manager=manager,
        store=store,
        upstream_headers={},
        default_upstream_base_url=upstream,
        session_policies=session_policy_map(bundle),
        session_token_secret="test-secret",
        upstream_headers_provider=lambda: {"Authorization": "Bearer upstream-oauth"},
        require_session=True,
    )
    return TestClient(app), manager, session.session_id, manager.issue_token(session.session_id)


@pytest.mark.parametrize(
    ("upstream", "expected"),
    [
        (
            "https://workspace.test/ai-gateway/mlflow",
            "https://workspace.test/ai-gateway/mlflow/v1/chat/completions",
        ),
        (
            "https://workspace.test/serving-endpoints/model/invocations",
            "https://workspace.test/serving-endpoints/model/invocations",
        ),
    ],
)
def test_routes_and_keeps_upstream_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, upstream: str, expected: str
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == expected
        assert request.headers["Authorization"] == "Bearer upstream-oauth"
        return httpx.Response(200, json={"usage": {"prompt_tokens": 10, "completion_tokens": 5}})

    client, manager, session_id, token = proxy_client(tmp_path, monkeypatch, handler, upstream)
    response = client.post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {token}"},
        json={"model": "test-model", "max_tokens": 16},
    )
    assert response.status_code == 200
    assert manager.get_session(session_id).spent_tokens == 15


def test_stream_handles_split_events_unicode_and_null_usage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    content = (
        'data: {"choices":[{"delta":{"content":"café"}}],"usage":null}\n\n'
        'data: {"usage":{"prompt_tokens":10,"completion_tokens":5}}\n\n'
        'data: {"usage":{"prompt_tokens":null,"completion_tokens":null}}\n\n'
        "data: [DONE]\n\n"
    )
    stream = ChunkedStream(content.encode())

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=stream, headers={"content-type": "text/event-stream"})

    client, manager, session_id, token = proxy_client(tmp_path, monkeypatch, handler)
    response = client.post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {token}"},
        json={"model": "test-model", "max_tokens": 16, "stream": True},
    )
    assert response.status_code == 200
    assert response.text == content
    assert stream.closed
    assert manager.get_session(session_id).spent_tokens == 15
    assert manager.get_session(session_id).reserved_tokens == 0


@pytest.mark.parametrize("status", [401, 429, 503])
def test_stream_preserves_upstream_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, status: int
) -> None:
    payload: dict[str, Any] = {"error": {"message": "upstream unavailable"}}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=payload)

    client, manager, session_id, token = proxy_client(tmp_path, monkeypatch, handler)
    response = client.post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {token}"},
        json={"model": "test-model", "stream": True},
    )
    assert response.status_code == status
    assert response.json() == payload
    assert manager.get_session(session_id).reserved_tokens == 0


def test_invocations_rejects_incompatible_protocol_before_reserving(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("unsupported request must not reach upstream")

    client, manager, session_id, token = proxy_client(
        tmp_path, monkeypatch, handler, "https://workspace.test/serving-endpoints/model/invocations"
    )
    response = client.post(
        "/v1/responses",
        headers={"Authorization": f"Bearer {token}"},
        json={"model": "test-model"},
    )
    assert response.status_code == 400
    assert manager.get_session(session_id).reserved_tokens == 0


def test_tool_metadata_is_session_scoped_and_bound_to_arguments(tmp_path: Path) -> None:
    store = StateStore(tmp_path / "state.db")
    metadata = ToolCallMetadata(store, "session-one")
    metadata.observe(
        {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {
                                "id": "call-one",
                                "index": 0,
                                "function": {"name": "ping", "arguments": '{"value":'},
                                "extra_content": {
                                    "google": {"thought_signature": "test-signature"}
                                },
                            }
                        ]
                    }
                }
            ]
        }
    )
    metadata.observe(
        {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {
                                "index": 0,
                                "function": {"arguments": '"OK"}'},
                            }
                        ]
                    }
                }
            ]
        }
    )
    call = {"id": "call-one", "function": {"name": "ping", "arguments": '{ "value": "OK" }'}}
    body = {"messages": [{"role": "assistant", "tool_calls": [call]}]}
    ToolCallMetadata(store, "session-two").restore(body)
    assert "extra_content" not in call
    ToolCallMetadata(store, "session-one").restore(body)
    assert call["extra_content"]["google"]["thought_signature"] == "test-signature"
    call["function"]["arguments"] = '{"value":"changed"}'
    with pytest.raises(HTTPException, match="signed tool call was modified"):
        metadata.restore(body)


def test_streamed_signature_survives_client_dropping_provider_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    call = {"id": "call-one", "type": "function", "function": {"name": "ping", "arguments": "{}"}}
    upstream_call = {
        **call,
        "index": 0,
        "extra_content": {"google": {"thought_signature": "test-signature"}},
    }
    event = json.dumps({"choices": [{"index": 0, "delta": {"tool_calls": [upstream_call]}}]})

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if body.get("stream"):
            return httpx.Response(
                200, stream=ChunkedStream(f"data: {event}\n\ndata: [DONE]\n\n".encode())
            )
        restored = body["messages"][0]["tool_calls"][0]
        assert restored["extra_content"]["google"]["thought_signature"] == "test-signature"
        return httpx.Response(
            200, json={"choices": [], "usage": {"prompt_tokens": 5, "completion_tokens": 1}}
        )

    client, manager, session_id, token = proxy_client(tmp_path, monkeypatch, handler)
    headers = {"Authorization": f"Bearer {token}"}
    first = client.post(
        "/v1/chat/completions", headers=headers, json={"model": "test-model", "stream": True}
    )
    assert first.status_code == 200
    second = client.post(
        "/v1/chat/completions",
        headers=headers,
        json={
            "model": "test-model",
            "messages": [{"role": "assistant", "tool_calls": [call]}],
        },
    )
    assert second.status_code == 200
