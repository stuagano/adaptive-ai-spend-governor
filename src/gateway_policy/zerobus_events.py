from __future__ import annotations

import time
from typing import Any, Protocol

from zerobus.sdk.shared import (  # type: ignore[import-not-found]
    RecordType,
    StreamConfigurationOptions,
    TableProperties,
)
from zerobus.sdk.sync import ZerobusSdk  # type: ignore[import-not-found]


class UsageEventSink(Protocol):
    def emit(self, event: dict[str, Any]) -> None: ...

    def close(self) -> None: ...


class ZerobusUsageEventSink:
    """ACKed JSON event ingestion for optional near-real-time reconciliation."""

    def __init__(
        self,
        server_endpoint: str,
        workspace_url: str,
        table_name: str,
        client_id: str,
        client_secret: str,
        max_retries: int = 3,
    ) -> None:
        self._sdk = ZerobusSdk(server_endpoint, workspace_url)
        self._table = TableProperties(table_name)
        self._options = StreamConfigurationOptions(record_type=RecordType.JSON)
        self._client_id = client_id
        self._client_secret = client_secret
        self._max_retries = max_retries
        self._stream: Any | None = None

    def emit(self, event: dict[str, Any]) -> None:
        for attempt in range(self._max_retries):
            try:
                stream = self._get_stream()
                offset = stream.ingest_record_offset(event)
                stream.wait_for_offset(offset)
                return
            except Exception:
                self.close()
                if attempt == self._max_retries - 1:
                    raise
                time.sleep(2**attempt)

    def close(self) -> None:
        if self._stream is not None:
            self._stream.close()
            self._stream = None

    def _get_stream(self) -> Any:
        if self._stream is None:
            self._stream = self._sdk.create_stream(
                self._client_id,
                self._client_secret,
                self._table,
                self._options,
            )
        return self._stream
