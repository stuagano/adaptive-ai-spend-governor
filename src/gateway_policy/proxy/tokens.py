from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime


class SessionTokenError(Exception):
    """Raised when a session token cannot be verified."""


def issue_session_token(session_id: str, expires_at: datetime, secret: str) -> str:
    payload = {
        "session_id": session_id,
        "exp": int(expires_at.timestamp()),
    }
    body = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8")
    signature = _sign(body, secret)
    return f"{body}.{signature}"


def verify_session_token(token: str, secret: str) -> str:
    try:
        body, signature = token.split(".", maxsplit=1)
    except ValueError as exc:
        raise SessionTokenError("malformed session token") from exc
    expected = _sign(body, secret)
    if not hmac.compare_digest(signature, expected):
        raise SessionTokenError("invalid session token signature")
    payload = json.loads(base64.urlsafe_b64decode(body.encode("utf-8")).decode("utf-8"))
    if int(payload["exp"]) < int(datetime.now(tz=UTC).timestamp()):
        raise SessionTokenError("session token expired")
    return str(payload["session_id"])


def _sign(body: str, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), body.encode("utf-8"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode("utf-8")
