from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Protocol

from gateway_policy.governor import SpendSnapshot


class TelemetryProvider(Protocol):
    def fetch_spend_snapshot(
        self,
        lookback_days: int,
        model_prices: dict[str, tuple[Decimal, Decimal]],
    ) -> SpendSnapshot:
        ...


@dataclass
class SqlTelemetryConfig:
    warehouse_id: str
    account_id: str
    endpoint_name: str | None = None


class FakeTelemetryProvider:
    def __init__(self, snapshot: SpendSnapshot) -> None:
        self._snapshot = snapshot

    def fetch_spend_snapshot(
        self,
        lookback_days: int,
        model_prices: dict[str, tuple[Decimal, Decimal]],
    ) -> SpendSnapshot:
        _ = lookback_days, model_prices
        return self._snapshot


class SqlTelemetryProvider:
    """Aggregates billing and usage telemetry via Databricks SQL Statements API."""

    def __init__(self, workspace_client: Any, config: SqlTelemetryConfig) -> None:
        self._workspace = workspace_client
        self._config = config

    def fetch_spend_snapshot(
        self,
        lookback_days: int,
        model_prices: dict[str, tuple[Decimal, Decimal]],
    ) -> SpendSnapshot:
        endpoint_filter = self._endpoint_filter("u")
        external_endpoint_filter = self._endpoint_filter("e")
        billing_usd = self._query_scalar(
            f"""
            SELECT COALESCE(SUM(u.usage_quantity * p.pricing.default), 0)
            FROM system.billing.usage AS u
            INNER JOIN system.billing.list_prices AS p
              ON u.cloud = p.cloud
             AND u.sku_name = p.sku_name
             AND u.usage_start_time >= p.price_start_time
             AND (u.usage_end_time <= p.price_end_time OR p.price_end_time IS NULL)
            WHERE u.billing_origin_product = 'MODEL_SERVING'
              AND u.usage_unit = 'DBU'
              AND u.usage_date >= date_trunc('month', current_date())
              {endpoint_filter}
            """
        )
        external_usd = self._query_scalar(
            f"""
            SELECT COALESCE(SUM(e.usage_quantity), 0)
            FROM system.ai_gateway.external_model_spend AS e
            WHERE e.usage_start_time >= date_trunc('month', current_timestamp())
              {external_endpoint_filter}
            """
        )
        daily_rows = self._query_rows(
            f"""
            WITH daily AS (
              SELECT u.usage_date,
                     SUM(u.usage_quantity * p.pricing.default) AS usd
              FROM system.billing.usage AS u
              INNER JOIN system.billing.list_prices AS p
                ON u.cloud = p.cloud
               AND u.sku_name = p.sku_name
               AND u.usage_start_time >= p.price_start_time
               AND (u.usage_end_time <= p.price_end_time OR p.price_end_time IS NULL)
              WHERE u.billing_origin_product = 'MODEL_SERVING'
                AND u.usage_unit = 'DBU'
                AND u.usage_date >= current_date() - INTERVAL {lookback_days} DAY
                {endpoint_filter}
              GROUP BY u.usage_date
              UNION ALL
              SELECT e.usage_date, SUM(e.usage_quantity) AS usd
              FROM system.ai_gateway.external_model_spend AS e
              WHERE e.usage_date >= current_date() - INTERVAL {lookback_days} DAY
                {external_endpoint_filter}
              GROUP BY e.usage_date
            )
            SELECT usage_date, SUM(usd) AS usd
            FROM daily
            GROUP BY usage_date
            ORDER BY usage_date
            """
        )
        recent_tokens = self._query_rows(
            f"""
            SELECT destination_model,
                   SUM(input_tokens) AS input_tokens,
                   SUM(output_tokens) AS output_tokens,
                   MAX(event_time) AS fresh_through
            FROM system.ai_gateway.usage
            WHERE event_time >= current_timestamp() - INTERVAL {lookback_days} DAY
              {self._usage_endpoint_filter()}
            GROUP BY destination_model
            """
        )

        month_to_date = Decimal(str(billing_usd)) + Decimal(str(external_usd))
        recent_estimate = self._estimate_recent_tokens(recent_tokens, model_prices)
        daily_burn = [Decimal(str(row.get("usd", 0))) for row in daily_rows]
        now = datetime.now(tz=UTC)
        stale = not daily_rows and not recent_tokens
        return SpendSnapshot(
            month_to_date_usd=month_to_date + recent_estimate,
            recent_window_usd=recent_estimate,
            billing_closed_through=now,
            telemetry_fresh_through=now,
            daily_burn_rates=daily_burn,
            is_stale=stale,
        )

    def _estimate_recent_tokens(
        self,
        rows: list[dict[str, Any]],
        model_prices: dict[str, tuple[Decimal, Decimal]],
    ) -> Decimal:
        total = Decimal("0")
        for row in rows:
            model = str(row.get("destination_model", ""))
            if model not in model_prices:
                continue
            input_price, output_price = model_prices[model]
            input_tokens = Decimal(str(row.get("input_tokens", 0)))
            output_tokens = Decimal(str(row.get("output_tokens", 0)))
            total += (input_tokens / Decimal("1000000")) * input_price
            total += (output_tokens / Decimal("1000000")) * output_price
        return total

    def _query_scalar(self, statement: str) -> float:
        rows = self._query_rows(statement)
        if not rows:
            return 0.0
        first = rows[0]
        return float(next(iter(first.values()), 0))

    def _query_rows(self, statement: str) -> list[dict[str, Any]]:
        response = self._workspace.statement_execution.execute_statement(
            warehouse_id=self._config.warehouse_id,
            statement=statement,
            wait_timeout="50s",
        )
        if response.result is None or response.result.data_array is None:
            return []
        columns = [column.name for column in response.manifest.schema.columns]
        rows: list[dict[str, Any]] = []
        for values in response.result.data_array:
            rows.append(dict(zip(columns, values, strict=False)))
        return rows

    def _endpoint_filter(self, alias: str | None = None) -> str:
        if self._config.endpoint_name is None:
            return ""
        prefix = f"{alias}." if alias else ""
        escaped = self._config.endpoint_name.replace("'", "''")
        return f"AND {prefix}usage_metadata.endpoint_name = '{escaped}'"

    def _usage_endpoint_filter(self) -> str:
        if self._config.endpoint_name is None:
            return ""
        escaped = self._config.endpoint_name.replace("'", "''")
        return f"AND endpoint_name = '{escaped}'"


def model_prices_to_map(
    prices: list[Any],
) -> dict[str, tuple[Decimal, Decimal]]:
    mapping: dict[str, tuple[Decimal, Decimal]] = {}
    for price in prices:
        mapping[price.model] = (
            price.input_usd_per_million_tokens,
            price.output_usd_per_million_tokens,
        )
    return mapping


def snapshot_to_json(snapshot: SpendSnapshot) -> str:
    payload = {
        "month_to_date_usd": str(snapshot.month_to_date_usd),
        "recent_window_usd": str(snapshot.recent_window_usd),
        "billing_closed_through": snapshot.billing_closed_through.isoformat(),
        "telemetry_fresh_through": snapshot.telemetry_fresh_through.isoformat(),
        "daily_burn_rates": [str(value) for value in snapshot.daily_burn_rates],
        "is_stale": snapshot.is_stale,
    }
    return json.dumps(payload)
