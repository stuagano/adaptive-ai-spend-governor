# Customer POC — Unity AI Gateway × Claude Code — Bake-off readout

**Window:** 7-day sample (John’s Claude Code Models tab vs Unity AI Gateway)  
**Audience:** FinOps / Platform  
**Call:** **CONDITIONAL GO**  
**Comparison model:** [Google Sheet](https://docs.google.com/spreadsheets/d/1m7ayHw-Cb0he2dBk106QNSH3molE5-fBEg6DUHvUzSU/edit)  
**Google Doc (this content):** [Bake-off readout](https://docs.google.com/document/d/15V9Y6qWBriZWrKZZ1-H7PMXRblwCJO2l-_FpDgT_qXw/edit)  
**Slides shell (empty — needs `google-slides-mcp` auth to populate):** [Presentation](https://docs.google.com/presentation/d/1JW48R0vhiPPE_iEzF6ZqOg5ZpPrurKUjiE-uSRqYHBE/edit)

---

## Slide 1 — Title

**Customer POC — Unity AI Gateway × Claude Code bake-off**  
7-day sample · FinOps / Platform  
Databricks Field Engineering

---

## Slide 2 — Bottom line

- **Bake-off call: CONDITIONAL GO**
- **Winnable on:** Type A API/list metering parity + Type B control-plane / Foundry-class decision
- **Not the scoreboard:** Beat Claude Code Max/Team for one power user (John) on dollars
- **Ask of you:** (1) Reframe charter away from Max death-match (2) Run cache SQL to close metering proof (3) Decide hybrid org buy model

---

## Slide 3 — Fair comparison rules

**Same work:** Same users · same dates · same models  

**Four token rates (not one):** fresh input · cache write (1.25×) · cache read (0.1×) · output  

**Callout:** Claude Code `/usage` × list ≠ Gateway pay-per-token bill

---

## Slide 4 — Inputs received

| Artifact | Status | Gap |
| --- | --- | --- |
| John’s 7-day CC vs Unity table | Received | Exact date bounds / TZ |
| Claude Code plan (Max / Team / API) | Open | Confirm seat SKU + $ |
| Cache breakout SQL | Missing | Fill FourRateCost tab |
| Contracted $/DBU | Open | Account team |
| Org cohort sizes | Placeholder | N=100 illustrative |

---

## Slide 5 — Token & cost reconciliation (Type A)

| Model | Claude Code In / Out | Gateway In / Out | Unity $ | CC list est. |
| --- | ---: | ---: | ---: | ---: |
| Sonnet 5 | 9.4M / 13.0M | **818.7M** / 12.1M | $646 | ~$149 |
| Opus 4.6 | 0.68M / 5.5M | **887.9M** / 4.27M | $1,361 | ~$141 |
| Haiku 4.5 | 0.17M / 0.22M | **15.7M** / 0.15M | $8 | ~$1 |
| **Total** | — | — | **~$2,016** | **~$291** |

**Callout:** Unity $ ≪ full-rate on Gateway In → **caching already in the bill** (~75% implied cache reads for Sonnet).  

**One liner:** List parity with Anthropic API at published rates (verify contract $/DBU = $0.07 list).

---

## Slide 6 — Same work, different meters

- Output similar → same approximate workload
- Gateway In includes full agentic context (often cache-inclusive)
- Claude Code UI “In” is **not** that meter
- Cost uses **four rates**, not In × full input price
- ~7× is **not** “Gateway list vs Anthropic API”

---

## Slide 7 — When seats beat pay-per-token

**John (sample week):** Gateway **~$2,016**/week → **~$8,700**/mo  
vs Max/Team seat **~$100–200**/mo → **seat wins ~40–87× on $** for that user  

**Punchline:** Don’t ask Gateway to beat a Max power user on dollars.

---

## Slide 8 — Org buy model

| Model | Illustrative (N=100, verify inputs) |
| --- | --- |
| Seat-all | Highest fixed tax |
| PPT-all | Cheap for light users; power users blow up |
| **Hybrid** (power on seats, rest PPT) | Usually cheapest on $ |

**Recommendation:** Hybrid on dollars · Gateway still for **governance / multi-tool control plane**

---

## Slide 9 — Why route coding agents through Unity AI Gateway

- One budget across Claude Code / Cursor / Codex / …
- MCP + Unity Catalog governance
- Audit in the lakehouse
- Provider optionality
- Near API list parity (not Max seat parity)

Blog: [Governing coding agent sprawl with Unity AI Gateway](https://www.databricks.com/blog/governing-coding-agent-sprawl-unity-ai-gateway)

---

## Slide 10 — Recommended path

1. **Confirm charter** — Type A metering + Type B control plane; drop “beat Max for John”
2. **Run cache SQL** — fill `token_details` in comparison sheet
3. **Decision meeting** — A/B/C score; hybrid population
4. **Pilot** — light/median on Gateway PPT; power users on seats (or hybrid policy)

**Owner / date:** TBD with AE

---

## AE speaker notes (3 bullets)

1. Open with slide 2 call — CONDITIONAL GO; don’t bury the lede.
2. If they push Max death-match, stay on slides 7–8; don’t reopen slide 5 as “we’re cheaper.”
3. Close with one decision: reframe charter, run diagnostics, or schedule Foundry-style control-plane score.

---

## Appendix — next data pull

```sql
-- Sketch: cache share from system.ai_gateway.usage (adapt catalog/filter to workspace)
SELECT
  model_name,
  SUM(input_tokens) AS gw_in,
  SUM(output_tokens) AS gw_out,
  SUM(token_details.cache_read_input_tokens) AS cache_read,
  SUM(token_details.cache_creation_input_tokens) AS cache_write
FROM system.ai_gateway.usage
WHERE /* same users + window as Claude Code export */
GROUP BY 1;
```

Pricing: Databricks Claude DBU rates × **$0.07/DBU** ≈ Anthropic public list (cache read 0.1×, cache write 1.25×).
