# Customer intake checklist — coding-agent Gateway bake-off

Use this with the AE **before** anyone builds a cost table. Check boxes in the working notes; missing must-haves = bake-off not started.

**Doc-checked (Jul 30, 2026):** `system.ai_gateway.usage` schema + dashboard tabs, cost observability (`system.billing.usage` / `external_model_spend`), Claude Code via `ucode` → `/ai-gateway/anthropic`, Claude DBU rate card (cache write/read columns).

## 0. Charter (must-have)

- [ ] Bake-off type primary: **A** API list parity / **B** vs Foundry / **C** org seat vs PPT / **D** single Max user (context only)
- [ ] Written success criteria (one sentence)
- [ ] Out of scope stated (e.g. “not trying to beat Max for one power user”)
- [ ] Decision maker + FinOps contact named

**Success criteria examples (good):**

- “Gateway four-rate $ within ~10% of Anthropic API list for the same traffic.”
- “We can see cache hit %, per-user spend, and a single budget across Claude Code + Cursor.”
- “TCO for 200 engineers: seats vs PPT by cohort.”

**Success criteria examples (bad):**

- “Gateway cheaper than John’s Claude Code Max week.”
- “Unity dashboard In tokens match Claude Code In.”

## 1. Window and population (must-have)

- [ ] Start date / end date / timezone
- [ ] Same window for Claude Code UI **and** Gateway/billing
- [ ] Named users (email ↔ Databricks identity; billing side often `identity_metadata.run_by`)
- [ ] Confirm those users actually routed coding-agent traffic through Gateway in-window

## 2. Commercial context (must-have)

- [ ] Claude Code plan: Max / Team / Pro / API key / mixed
- [ ] Seat price (list or contract) if Max/Team
- [ ] Whether Claude Code `/usage` is subscription UI vs API billing
- [ ] Databricks contract: list vs discounted $/DBU (ask account team if unknown; do not assume $0.07 without check)
- [ ] **Capacity path:** Databricks-hosted PPT **or** external model provider service (BYO Anthropic/Bedrock/etc.) — different cost tables
- [ ] Competing path: Anthropic API direct / Azure AI Foundry / other gateway

## 3. Usage artifacts — Claude Code side (must-have)

- [ ] Models tab or `/usage` screenshots for **named users + window**
- [ ] Per-model **In** and **Out** (and cache fields if shown)
- [ ] Clarification: does their “In” exclude cache reads? (confirm with them — don’t assume)
- [ ] Any export CSV if available (better than screenshots)

## 4. Usage artifacts — Gateway side (must-have)

- [ ] Unity AI Gateway **Usage** + **Cost Observability** dashboard views (or exports) for **same users + window**
  - Prefer Cost Observability / billing for **$**
  - Prefer Usage tab / `system.ai_gateway.usage` for **tokens + cache hit ratios**
  - Coding Agents tab (sessions, commits, LOC) is **not** the token/$ scoreboard
- [ ] Per-model In / Out / $ if shown
- [ ] Source confirmed: `system.ai_gateway.usage` for tokens (not classic `endpoint_usage` alone)
- [ ] Access note: `system.ai_gateway.usage` often needs account + metastore admin (or FE runs SQL). Unity AI Gateway preview must be enabled.
- [ ] Endpoint type: Global vs in-geo
- [ ] Model names as billed (Sonnet 5, Opus 4.6, …)

## 5. Metering bake-off extras (Type A — required for “is Databricks overcharging?”)

- [ ] Query or FE access: `token_details.cache_read_input_tokens` / `cache_creation_input_tokens`
- [ ] Cache-read % of input by model
- [ ] Sample rows checking whether `input_tokens` looks inclusive of cache (docs do not state this; measure empirically)
- [ ] Claude Code routing path: `ucode` / `https://<workspace>/ai-gateway/anthropic` vs other
- [ ] Four-rate rebuild $ **or** billed DBUs from `system.billing.usage` (hosted) / `system.ai_gateway.external_model_spend` (external provider)

## 6. Rollout TCO extras (Type C)

- [ ] Headcount in scope
- [ ] Cohort split: % power / median / light (or proxy: p90 / median tokens)
- [ ] Other coding agents to include in “one budget” (Cursor, Codex, Gemini CLI)
- [ ] Expected adoption ramp (month 1 / 3 / 6)

## 7. Governance value (Type B — score even if $ is flat)

- [ ] MCP / data systems agents must reach
- [ ] Audit / retention requirements
- [ ] Need for per-user or per-team budgets
- [ ] Need for one budget across multiple coding tools
- [ ] Identity / SSO requirements

## 8. Red flags — pause the bake-off

| Red flag | Action |
| --- | --- |
| Only one Max power user, no Type A/C data | Reframe charter; collect intake |
| Different weeks compared | Re-pull same window |
| Unity In × full input rate as “proof” | Run four-rate + cache % |
| No `token_details` access | Get FE/admin help before concluding |
| Cache % ≈ 0 on current traffic | Fix path; don’t score economics yet |
| Scoring $ from Coding Agents tab only | Switch to Cost Observability / billing |
| External BYO keys but using hosted DBU math | Use `external_model_spend` instead |
| Success = “beat Max” | Reset success criteria with sponsor |

## Quick ask script (Slack to customer)

> To run a fair bake-off we need, for the **same people and same dates**:
> 1) Claude Code plan (Max/Team/API) and Models/`/usage` In/Out by model  
> 2) Gateway Usage + Cost Observability (or exports) for those users — not just Coding Agents activity  
> 3) Whether we can query `system.ai_gateway.usage` cache fields (or have FE run it; may need admin)  
> 4) How Claude Code is pointed at Databricks (`ucode` / `/ai-gateway/anthropic` vs other) and whether models are Databricks-hosted or external provider  
> 5) What “good” looks like — API cost parity, Foundry comparison, or org-wide seat vs metered TCO  
>
> We should **not** use one power user’s Max week × list as the only scoreboard.
