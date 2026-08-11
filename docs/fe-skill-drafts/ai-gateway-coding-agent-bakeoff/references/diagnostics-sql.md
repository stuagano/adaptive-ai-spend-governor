# Diagnostics SQL — Unity AI Gateway coding-agent cost

Run in a workspace with system table access. Adjust requester / time window to the user under review.

## 1. Is caching engaging?

```sql
SELECT
  destination_model,
  COUNT(*)                                       AS requests,
  SUM(input_tokens)                              AS input_tokens_reported,
  SUM(token_details.cache_read_input_tokens)     AS cache_read_tokens,
  SUM(token_details.cache_creation_input_tokens) AS cache_write_tokens,
  SUM(output_tokens)                             AS output_tokens,
  ROUND(
    100.0 * SUM(token_details.cache_read_input_tokens)
      / NULLIF(SUM(input_tokens), 0),
    1
  ) AS cache_read_pct_of_input
FROM system.ai_gateway.usage
WHERE event_time >= current_timestamp() - INTERVAL 7 DAYS
  -- AND requester = '<user_email>'
GROUP BY destination_model
ORDER BY input_tokens_reported DESC;
```

| Result | Meaning |
| --- | --- |
| ~60–95%+ | Caching working; use four-rate cost model |
| Near 0% on current traffic | Review Claude Code path (prefer `/ai-gateway/anthropic` / ucode); escalate in `#ai-gateway` if still zero |

## 2. Is `input_tokens` inclusive of cache?

```sql
SELECT
  request_id,
  input_tokens,
  token_details.cache_read_input_tokens     AS cache_read,
  token_details.cache_creation_input_tokens AS cache_write,
  input_tokens
    - COALESCE(token_details.cache_read_input_tokens, 0)
    - COALESCE(token_details.cache_creation_input_tokens, 0) AS implied_fresh_input,
  output_tokens
FROM system.ai_gateway.usage
WHERE event_time >= current_timestamp() - INTERVAL 1 DAY
  AND COALESCE(token_details.cache_read_input_tokens, 0) > 0
ORDER BY input_tokens DESC
LIMIT 20;
```

If `input_tokens` ≥ `cache_read + cache_write` on rows, treat input as **inclusive** — do not add cache on top.

OpenAI-format paths are often cache-**inclusive**; native Anthropic passthrough is often cache-**exclusive**. Confirm empirically for the customer’s wire path.

## 3. Four-rate rebuild (Sonnet 5 intro Global example)

Swap DBU rates for the actual model. Verify on the [pricing page](https://www.databricks.com/product/pricing/proprietary-foundation-model-serving) before sending to customers.

```sql
WITH u AS (
  SELECT
    destination_model,
    SUM(
      GREATEST(
        input_tokens
          - COALESCE(token_details.cache_read_input_tokens, 0)
          - COALESCE(token_details.cache_creation_input_tokens, 0),
        0
      )
    ) AS fresh_input,
    SUM(COALESCE(token_details.cache_read_input_tokens, 0))     AS cache_read,
    SUM(COALESCE(token_details.cache_creation_input_tokens, 0)) AS cache_write,
    SUM(output_tokens)                                          AS output
  FROM system.ai_gateway.usage
  WHERE event_time >= current_timestamp() - INTERVAL 7 DAYS
  GROUP BY destination_model
)
SELECT
  destination_model,
  ROUND(
      fresh_input / 1e6 * 28.571
    + cache_write / 1e6 * 35.714
    + cache_read  / 1e6 *  2.857
    + output      / 1e6 * 142.857,
    2
  ) AS dbus_at_list,
  ROUND(
    (
        fresh_input / 1e6 * 28.571
      + cache_write / 1e6 * 35.714
      + cache_read  / 1e6 *  2.857
      + output      / 1e6 * 142.857
    ) * 0.07,
    2
  ) AS usd_at_list
FROM u
ORDER BY usd_at_list DESC;
```

Cost model:

```text
cost ≈ fresh×input + cache_write×1.25×input + cache_read×0.1×input + output×output
```

## 4. Reconcile to billed DBUs

```sql
SELECT
  DATE(usage_start_time) AS usage_date,
  usage_metadata.ai_gateway.destination_model AS model,
  SUM(usage_quantity) AS billed_dbus
FROM system.billing.usage
WHERE billing_origin_product = 'MODEL_SERVING'
  AND usage_start_time >= current_timestamp() - INTERVAL 7 DAYS
  AND usage_metadata.ai_gateway.endpoint_name IS NOT NULL
GROUP BY 1, 2
ORDER BY 1, billed_dbus DESC;
```

Token × list-rate estimates should be checked against this table / invoice, not against Claude Code `/usage` dollars alone.

## Tables cheat sheet

| Table | Cache breakout? | Use for |
| --- | --- | --- |
| `system.ai_gateway.usage` | Yes (`token_details`) | Coding-agent / Unity AI Gateway POC |
| `system.serving.endpoint_usage` | No | Classic endpoints only — cannot explain cache $ |
| `system.billing.usage` | DBU aggregates | Invoice reconciliation |

## Sanity check without SQL

If Unity $ ≪ (Unity input tokens × full input $/1M + output × output $/1M), the dashboard cost is already applying something cheaper than full input — typically cache reads. Say that out loud before debating list markup.
