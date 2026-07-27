from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ProxyMetrics:
    requests_total: int = 0
    rejections_total: int = 0
    reservations_total: int = 0
    stream_disconnects_total: int = 0
    active_stage: str | None = None
    telemetry_stale: bool = False

    def to_prometheus(self) -> str:
        lines = [
            "# HELP gateway_proxy_requests_total Total proxied requests",
            "# TYPE gateway_proxy_requests_total counter",
            f"gateway_proxy_requests_total {self.requests_total}",
            "# HELP gateway_proxy_rejections_total Total rejected requests",
            "# TYPE gateway_proxy_rejections_total counter",
            f"gateway_proxy_rejections_total {self.rejections_total}",
            "# HELP gateway_proxy_reservations_total Total budget reservations",
            "# TYPE gateway_proxy_reservations_total counter",
            f"gateway_proxy_reservations_total {self.reservations_total}",
            "# HELP gateway_proxy_stream_disconnects_total Stream disconnects before usage",
            "# TYPE gateway_proxy_stream_disconnects_total counter",
            f"gateway_proxy_stream_disconnects_total {self.stream_disconnects_total}",
            "# HELP gateway_proxy_telemetry_stale Whether telemetry is stale",
            "# TYPE gateway_proxy_telemetry_stale gauge",
            f"gateway_proxy_telemetry_stale {1 if self.telemetry_stale else 0}",
        ]
        if self.active_stage:
            lines.extend(
                [
                    "# HELP gateway_proxy_active_stage_info Active governor stage",
                    "# TYPE gateway_proxy_active_stage_info gauge",
                    f'gateway_proxy_active_stage_info{{stage="{self.active_stage}"}} 1',
                ]
            )
        return "\n".join(lines) + "\n"


metrics = ProxyMetrics()
