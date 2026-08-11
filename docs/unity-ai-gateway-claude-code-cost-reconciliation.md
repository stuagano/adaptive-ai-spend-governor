# Unity AI Gateway vs Claude Code: Cost & Token Reconciliation

**Audience:** Customer data platform / FinOps stakeholders evaluating Claude Code via Unity AI Gateway  
**Purpose:** Clarify why Databricks dashboards and Claude Code `/usage` can diverge sharply on input tokens and estimated dollars — and how to reconcile them correctly  
**Status:** Guidance based on the 7-day usage comparison you shared (Claude Code Models tab vs Unity AI Gateway dashboard)

---

## Summary

Unity AI Gateway is **not** ~7× more expensive than Anthropic **API** list price. The comparison you built mixes two different input meters and two different commercial models (Claude Code product usage vs pay-per-token Gateway).

| Observation | What it means |
| --- | --- |
| Output tokens are similar between Claude Code and Unity | Roughly the same work ran on both sides |
| Unity **input** tokens are ~87×–1,300× higher than Claude Code “In” | Different definitions of “input,” not a 7× list-price markup |
| Unity reported cost (~$2,016) is far below full-rate pricing on those input tokens | Prompt caching discounts appear to be reflected in Unity cost |
| Claude Code list estimate (~$291) uses Claude Code “In/Out” only | That is not a like-for-like pay-per-token bill for the same traffic |

**Bottom line on metering:** Claude on Databricks list = Anthropic public list (including cache read at 0.1× and cache write at 1.25×). Reconcile with the four-rate token model and `system.ai_gateway.usage` / `system.billing.usage`.

**Bottom line on why switch:** Unity AI Gateway is not sold as “cheaper Claude Code Max.” For heavy individual users on a flat Claude Code subscription, pay-per-token will often look higher — that is expected. The enterprise case is **control, consolidation, and governance** of coding-agent and LLM traffic (and parity with other enterprise gateways such as Azure AI Foundry), not beating Anthropic’s subscription ARPU for power users.

---

## Why route Claude Code through Unity AI Gateway?

If the only success criterion is “lowest dollar for one power user’s Claude Code habit,” a Claude Code Max/Team seat can win. That is a **subscription vs pay-per-token** comparison, not a Databricks vs Anthropic rate-card comparison.

Official Databricks positioning is **tool freedom for developers, unified governance for admins** — not “cheaper than Claude Code Max.” See [Governing coding agent sprawl with Unity AI Gateway](https://www.databricks.com/blog/governing-coding-agent-sprawl-unity-ai-gateway).

Unity AI Gateway is the right comparison when you are deciding how the **enterprise** will buy, govern, and observe LLM / coding-agent usage:

| Decision driver | Claude Code direct (esp. Max/Team) | Unity AI Gateway |
| --- | --- | --- |
| Unit economics for one heavy user | Flat seat can be cheaper than metered tokens | Pay-per-token (same list economics as Anthropic API) |
| Enterprise-wide rollout | Per-seat tax for every user; weak central FinOps | Usage-based; light users cheap, heavy users visible |
| Chargeback / showback | Limited product-level usage | System tables, tags, budgets, dashboards by user/team |
| Budgets across tools | Per-vendor admin consoles | **One budget across Claude Code, Cursor, Codex, Gemini CLI, etc.** |
| MCP / data access | Tool-native; easy to over-privilege agents | UC permissions + service policies on MCP/tools |
| Audit / compliance | Fragmented product logs | Audit-ready traces in Unity Catalog / Lakehouse |
| Multi-model / day-one models | Claude-centric | Claude + OpenAI + Gemini + open models on one path |
| Procurement | Separate Anthropic (or Foundry) relationship | Can sit under existing Databricks commercial relationship |
| Alternative you are also evaluating | — | Same class of decision as **Azure AI Foundry / CogMed-style consolidation** — pick an enterprise control plane, then compare **API list parity + platform value**, not Max seat vs Gateway invoice |

### How to frame cost in the POC

1. **Do not** use “Claude Code `/usage` × list ≈ $291” as the business case baseline for Gateway.
2. **Do** compare:
   - Unity AI Gateway pay-per-token (four-rate, cache-aware) **vs Anthropic API** or **vs Azure AI Foundry** pay-per-token for the same models — expect **near list parity**, then decide on platform.
   - Optional: seat math for Claude Code Max/Team across the full engineer population vs metered Gateway (many orgs find seats win for a few power users and lose for broad rollout).
3. **Buy Gateway for:** identity-bound routing, MCP governance, observability, budgets across coding tools, and one governed path for enterprise AI coding — with honest token economics, not a hidden discount on Claude.

Customer proof points from the coding-agent sprawl launch (First American, Milliman MedInsight) emphasize **visibility, budgets, anomalies, and governed scale across hundreds of developers** — not lower seat price vs Anthropic Max.

---

## Answers to your two questions

### 1. Why is reported usage (DBUs / tokens) so high? Is input token caching considered?

**Yes — input token caching is supported and priced on Databricks for Claude.**

- Cache **reads** bill at **one tenth** of the input rate (same multiplier as Anthropic).
- Cache **writes** bill at **1.25×** the input rate (same as Anthropic’s 5-minute cache write).
- Token breakouts for cache read / cache write are available in `system.ai_gateway.usage` under `token_details` (`cache_read_input_tokens`, `cache_creation_input_tokens`).

Reported input volume looks high because **Claude Code agentic sessions resend large conversation / tool context on every turn**. Databricks meters each request’s input. A large share of that volume is typically served from cache and billed at the reduced rate — it should not be costed as if every input token were fresh.

Your Unity cost column is consistent with that behavior. For example, Sonnet 5 at full introductory input rate on **818.7M** input tokens would be on the order of **~$1,750+** (before output). Unity shows **~$646**, which only reconciles if a large majority of those tokens are billed as cache reads (~75% implied for Sonnet in the window you shared). Opus and Haiku reverse-engineer similarly (~80% / ~58%). That is the opposite of “caching ignored.”

**Does it vary by model?** Yes. Absolute DBU rates differ by model (Sonnet / Opus / Haiku), and cache hit rates differ by how each model is used in the session. The *multipliers* (0.1× read / 1.25× write) are consistent across Claude models.

### 2. What is the DBU-to-dollar conversion, and is it discounted vs Anthropic?

For pay-per-token Anthropic models on Databricks:

- Conversion is **$0.07 per DBU** at published list.
- Published DBU rates × $0.07 equal Anthropic’s **public list** prices for input, output, cache write, and cache read.
- There is **no Databricks markup at list** relative to Anthropic list for these Claude SKUs.
- Any discount below list comes from **your Databricks contract**, not from a special Claude-only rate card. Account team can confirm contracted rates.

**Illustrative list parity (Claude Sonnet 5 introductory rates, through Aug 31, 2026):**

| Token type | Anthropic list | Databricks (DBU/1M × $0.07) |
| --- | --- | --- |
| Input | $2 / 1M | 28.571 × $0.07 = $2 |
| Output | $10 / 1M | 142.857 × $0.07 = $10 |
| Cache write | $2.50 / 1M (1.25×) | 35.714 × $0.07 = $2.50 |
| Cache read | $0.20 / 1M (0.1×) | 2.857 × $0.07 = $0.20 |

Authoritative invoice math: join `system.billing.usage` to `system.billing.list_prices` on `sku_name` and multiply usage quantity by effective list price. Contract discounts are applied on the invoice, not always visible as “list” in system tables.

---

## What your comparison table is showing

Values below are from the 7-day comparison you shared.

| Model | Claude Code In / Out | Unity dashboard In / Out | Input ratio | Unity cost | Claude Code list estimate |
| --- | --- | --- | ---: | ---: | ---: |
| Sonnet 5 | 9.4M / 13.0M | **818.7M** / 12.1M | **~87×** | $646.33 | ~$148.80 |
| Opus 4.6 | 679.7k / 5.5M | **887.9M** / 4.27M | **~1,306×** | $1,361.04 | ~$140.90 |
| Haiku 4.5 | 172.4k / 219.7k | **15.7M** / 153.7k | **~91×** | $8.22 | ~$1.27 |
| **Total** | — | — | — | **$2,015.59** | **~$290.97** |

### Correct reading

1. **Output alignment** → same approximate workload.
2. **Input divergence** → Claude Code “In” and Unity “In” are not the same quantity.
   - Claude Code `/usage` (especially on Max/Team) is a product usage view; it is not a drop-in substitute for pay-per-token API metering of every Gateway request.
   - Unity AI Gateway dashboards / `system.ai_gateway.usage` reflect request-level metering. On common paths, reported `input_tokens` can be **cache-inclusive** (fresh + cache read + cache write components), while Anthropic-style “input” often means **fresh / non-cached** only.
3. **~$291 vs ~$2,016** → apples to oranges.
   - ~$291 = list price on Claude Code In/Out only (and does not add cache-read charges for the large cached portion of agentic traffic).
   - ~$2,016 = Unity’s reported cost for a much larger input meter, already looking cache-discounted rather than full-rate.

### Incorrect reading

- “Unity AI Gateway list price is ~7× Anthropic.”
- “Databricks does not consider input token caching.”

---

## How to cost Claude correctly on Databricks

Use **four rates**, never a single input rate on gross input:

```text
cost ≈
  fresh_input      × input_rate
+ cache_write      × (1.25 × input_rate)
+ cache_read       × (0.10 × input_rate)
+ output           × output_rate
```

Where:

```text
fresh_input ≈ max(input_tokens − cache_read − cache_write, 0)
```

Confirm empirically on your workspace whether `input_tokens` is inclusive of cache components (recommended before any FinOps model is locked).

---

## Recommended reconciliation queries

Run these in a workspace with access to system tables. Adjust the requester / time window to match the user and 7-day period in your analysis.

### A. Is caching engaging?

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

**How to interpret**

| Result | Meaning |
| --- | --- |
| Cache read share in the ~60–90%+ range | Caching is working; cost models must use four rates |
| Cache read share near 0% on current traffic | Integration path needs review (prefer Claude Code → native Anthropic Gateway path) |

### B. Confirm whether `input_tokens` includes cache

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

If `input_tokens` is consistently ≥ `cache_read + cache_write`, treat `input_tokens` as **inclusive** and do not add cache tokens on top.

### C. Rebuild dollars with four rates (Sonnet 5 intro example)

Swap DBU rates for the model actually used. Rates below are Claude Sonnet 5 Global introductory DBUs.

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

### D. Reconcile to billed DBUs

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

Token × rate card estimates should be checked against this billing table (and your invoice), not against Claude Code `/usage` dollars alone.

---

## Integration guidance for Claude Code

For best cache behavior and Anthropic-native semantics, route Claude Code through Unity AI Gateway’s **Anthropic-compatible** path (for example `/ai-gateway/anthropic` / `ucode` setup), rather than an OpenAI-compatible chat-completions path.

Databricks documents coding-agent integration and Claude Code configuration here:

- [Integrate coding agents with Unity AI Gateway](https://docs.databricks.com/aws/en/ai-gateway/coding-agent-integration-model-provider-services)
- [Model usage for Unity AI Gateway](https://docs.databricks.com/aws/en/ai-gateway/usage-tracking)
- [Monitor Unity AI Gateway cost](https://docs.databricks.com/aws/en/ai-gateway/cost-observability)
- [Proprietary Foundation Model Serving pricing](https://www.databricks.com/product/pricing/proprietary-foundation-model-serving)

---

## Recommended next steps

1. Separate two decisions in the POC write-up: **(a)** metering/caching accuracy, **(b)** commercial model (subscription seats vs enterprise pay-per-token + governance).
2. Run query **A** for the same user/window as your Claude Code screenshots and confirm cache-read %.
3. Run query **B** once to lock inclusive vs exclusive `input_tokens` semantics for your wire path.
4. Rebuild cost with query **C** (correct model rates) and compare to query **D** / invoice — and to **Anthropic API or Foundry** economics, not to Claude Code UI list estimates.
5. Confirm Claude Code is on the Anthropic-native Gateway path.
6. If evaluating enterprise rollout, add a simple seat model: N engineers × Claude Code Max/Team vs expected Gateway pay-per-token by cohort (power / median / light). That is the business comparison; John’s power-user week alone is not.

---

## Appendix: Why a single “input × rate” model fails for agentic coding

Long Claude Code sessions send large prompts repeatedly. Most of that content is eligible for prompt caching after the first turn. Costing every input token at the fresh input rate overstates spend by a factor that grows with cache hit rate:

| Cache reads as share of input | Overstatement if all input priced at full input rate |
| ---: | ---: |
| 50% | ~1.8× |
| 75% | ~2.9× |
| 90% | ~5.3× |
| 95% | ~6.9× |
| 97% | ~7.8× |

That pattern — **large input divergence, similar output, multi-× dollar gap vs a Claude Code UI estimate** — is exactly what a cache-unaware or cross-meter comparison produces. It is not evidence that Unity AI Gateway list pricing is a fixed multiple of Anthropic list.

---

*Document prepared to support your Unity AI Gateway POC evaluation. For contracted discounts or invoice-level reconciliation, involve your Databricks account team with the outputs of queries C and D.*
