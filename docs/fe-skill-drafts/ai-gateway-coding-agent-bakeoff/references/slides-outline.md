# Customer slides outline — fill then build with `google-slides`

Use Databricks corporate template via **google-slides** CLI path when available.

Replace `{{...}}` before building. Delete slides marked optional if N/A.

---

## Slide 1 — Title
**Title:** {{Customer}} — Unity AI Gateway × Claude Code bake-off  
**Subtitle:** {{Window}} · {{Audience: FinOps / Platform / Joint}}  
**Footer:** Databricks Field Engineering

## Slide 2 — Executive takeaway (always)
**Title:** Bottom line  
**Bullets:**
- Bake-off call: **{{GO | CONDITIONAL GO | NO-GO | PAUSE}}**
- Winnable on: {{…}}
- Not the scoreboard: {{e.g. beat Max for one power user}}
- Ask of you: {{1–2 asks}}

## Slide 3 — What we compared (charter)
**Title:** Fair comparison rules  
**Two columns:**
- Left: Same users · same dates · same models  
- Right: Four token rates (fresh / cache write / cache read / output)  
**Callout:** Claude Code `/usage` × list ≠ Gateway pay-per-token bill

## Slide 4 — What you sent us (optional if sparse)
**Title:** Inputs received  
Table: artifact | status | gap

## Slide 5 — Metering result (Type A)
**Title:** Token & cost reconciliation  
**Table:** Model | Claude Code In/Out | Gateway In/Out | Cache read % | Four-rate / billed $  
**Callout:** If Gateway $ ≪ full-rate on Gateway In → caching already in the bill  
**One liner:** List parity with Anthropic API at published rates (verify contract $/DBU)

## Slide 6 — Why input looked “7×” (optional)
**Title:** Same work, different meters  
**Diagram/bullets:**
- Output similar → same approximate workload  
- Gateway In includes full agentic context (often cache-inclusive)  
- Claude Code UI “In” is not that meter  
- Cost uses four rates, not In × full input price

## Slide 7 — Power-user economics (Type C / always useful)
**Title:** When seats beat pay-per-token  
**Example:** {{Power user}} week Gateway ${{W}} → ~${{M}}/mo vs Max/Team seat ~${{S}} → **seat wins ~{{R}}× on $**  
**Punchline:** Don’t ask Gateway to beat a Max power user on dollars.

## Slide 8 — Org model (Type C)
**Title:** Org buy model — seats vs PPT vs hybrid  
**Table:** Seat-all | PPT-all | Hybrid (power on seats, rest PPT)  
**Recommendation:** {{hybrid / seats / PPT}} on $ · Gateway still for {{governance / multi-tool}}

## Slide 9 — Control plane (Type B)
**Title:** Why route coding agents through Unity AI Gateway  
**Bullets:** One budget across Claude Code / Cursor / Codex · MCP + UC governance · Audit in lakehouse · Provider optionality · Near API list parity  
**Link:** Governing coding agent sprawl blog

## Slide 10 — Recommendation & next steps
**Title:** Recommended path  
**Bullets:**
1. {{Confirm charter}}  
2. {{Run cache SQL / fix path}}  
3. {{Decision meeting: A/B/C}}  
4. {{Pilot population}}  
**Owner / date**

## Slide 11 — Appendix: asks checklist (optional)
Paste condensed intake must-haves.

## Slide 12 — Appendix: SQL / links (optional)
Cache % query · pricing page · ucode / `/ai-gateway/anthropic`

---

## Speaker notes (AE)

1. Open with slide 2 call — don’t bury the lede.  
2. If they push Max death-match, stay on slide 7–8; don’t reopen slide 5 as “we’re cheaper.”  
3. Close with one decision: reframe charter, run diagnostics, or schedule Foundry-style control-plane score.

## Build checklist for the agent

- [ ] Fill all `{{placeholders}}` or mark `TBD`  
- [ ] Invoke `google-slides` (CLI template for customer-facing)  
- [ ] ~8–12 slides; cut appendix if time-boxed  
- [ ] Return presentation URL; do not share until asked  
