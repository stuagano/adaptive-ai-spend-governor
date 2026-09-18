from __future__ import annotations

import hashlib
import json
from typing import Any

from fastapi import HTTPException

from gateway_policy.proxy.store import SessionStateStore


class ToolCallMetadata:
    def __init__(self, store: SessionStateStore, session_id: str | None) -> None:
        self.store = store
        self.session_id = session_id
        self.calls: dict[tuple[int, int], dict[str, Any]] = {}

    def restore(self, body: dict[str, Any]) -> None:
        if not self.session_id:
            return
        for message in body.get("messages", []):
            if message.get("role") != "assistant":
                continue
            for call in message.get("tool_calls") or []:
                saved = self.store.get_idempotent_response(self._key(call.get("id", "")))
                if saved is None:
                    continue
                if saved["fingerprint"] != self._fingerprint(call.get("function", {})):
                    raise HTTPException(status_code=400, detail="signed tool call was modified")
                extra_content = dict(call.get("extra_content") or {})
                google = dict(extra_content.get("google") or {})
                google["thought_signature"] = saved["thought_signature"]
                extra_content["google"] = google
                call["extra_content"] = extra_content

    def observe(self, payload: dict[str, Any]) -> None:
        if not self.session_id:
            return
        for choice in payload.get("choices", []):
            message = choice.get("delta") or choice.get("message") or {}
            for position, call in enumerate(message.get("tool_calls") or []):
                key = (choice.get("index", 0), call.get("index", position))
                accumulated = self.calls.setdefault(
                    key, {"id": "", "function": {"name": "", "arguments": ""}}
                )
                accumulated["id"] = call.get("id") or accumulated["id"]
                for field in ("name", "arguments"):
                    accumulated["function"][field] += (call.get("function") or {}).get(field) or ""
                signature = ((call.get("extra_content") or {}).get("google") or {}).get(
                    "thought_signature"
                )
                if signature:
                    accumulated["thought_signature"] = signature
                if accumulated.get("thought_signature") and accumulated["id"]:
                    self.store.store_idempotent_response(
                        self._key(accumulated["id"]),
                        {
                            "thought_signature": accumulated["thought_signature"],
                            "fingerprint": self._fingerprint(accumulated["function"]),
                        },
                    )

    def _key(self, call_id: str) -> str:
        return f"provider-tool-metadata:{self.session_id}:{call_id}"

    @staticmethod
    def _fingerprint(function: dict[str, Any]) -> str:
        arguments = function.get("arguments", "")
        try:
            arguments = json.loads(arguments)
        except (TypeError, ValueError):
            pass
        canonical = json.dumps(
            {"name": function.get("name"), "arguments": arguments}, sort_keys=True
        )
        return hashlib.sha256(canonical.encode()).hexdigest()
