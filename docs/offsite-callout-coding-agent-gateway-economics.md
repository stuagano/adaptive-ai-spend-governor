# Offsite Callout: Coding-agent economics vs Unity AI Gateway pitch

**Forum:** SF leadership offsite  
**Owner:** FE / AI Gateway field  
**Status:** Draft callout — needs PM / GTM ownership decision  
**Related customer signal:** Enterprise Claude Code → Unity AI Gateway POC; ~7× $ gap vs Claude Code `/usage` (metering mismatch + Max/seat vs PPT)

---

## The callout (one slide / 60 seconds)

> **We are winning the metering argument and losing the commercial frame.**  
> Customers comparing Claude Code Max/Team to Unity AI Gateway pay-per-token will often conclude “Databricks is more expensive.” That can be *true for a heavy seat* and still the *wrong bake-off*. Our decks sell governance; they do **not** arm the field for this objection. If coding-agent Gateway is a growth bet, this gap needs an explicit field + PM response — not another token FAQ.

---

## Why this belongs on the leadership agenda

| Signal | Detail |
| --- | --- |
| Recurring POC pattern | Claude Code UI “In” ≪ Gateway input (87×–1,300× in one 7-day power-user window); output similar; $ looks ~7× |
| Technical truth | List parity with Anthropic **API**; cache discounts show up in Gateway $; apples ≠ oranges on meters |
| Commercial truth | Max/Team seat can beat PPT for power users; Gateway is not sold as cheaper Claude |
| Field-materials gap | Battlecard / L200 / product deck = governance upside only; **no** Max-vs-PPT objection slide; **no** metering reconciliation guidance |
| Strategic risk | Coding-agent support is a headline Gateway motion; first serious FinOps review can kill the POC before governance value is heard |

---

## What leadership should internalize

1. **Do not let field “prove” Gateway is cheaper than Claude Code Max.** That fight is often unwinnable and off-strategy.
2. **Correct bake-off:** Gateway / Foundry / Anthropic **API** (list parity + platform) — *or* org-wide seat math vs PPT — not one power user’s `/usage` × list.
3. **Product + GTM owe the field an objection pack:** Max vs PPT, cache-aware metering, what “In” means in Claude Code vs `system.ai_gateway.usage`.
4. **This is a pattern, not a one-off ticket.** Same shape as Zepto-class cache reporting pain + Foundry consolidation deals.

---

## Asks for the offsite

| # | Ask | Owner |
| --- | --- | --- |
| 1 | Endorse the commercial frame: **governance + API list parity**, never “cheaper Max” | AI Governance PM + GTM |
| 2 | Ship a 1-pager / battlecard addendum: Max vs PPT + metering reconciliation | Product Marketing / FE enablement |
| 3 | Add Claude Code cost estimator + four-rate SQL to standard POC kit | FE / Solutions |
| 4 | Decide whether Databricks should ever offer / partner on seat-like economics for coding agents (or stay PPT-only and own that) | Leadership |

---

## Suggested talk track (leadership room)

**Open:** “Customers aren’t confused that we charge DBUs. They’re comparing a subscription seat to a metered bill and concluding we lose.”

**Bridge (with numbers):** “Public Max is roughly **$100–200/user-mo**. This power user is ~**$8.7k/mo** on Gateway PPT — seats win **~40–90×** on dollars. That’s expected. Wrong bake-off is Max vs PPT for John; right bake-off is API list parity + control plane, with hybrid org math.”

**Close:** “Our pitch already says governance, not cheaper Claude. The offsite ask is to make that objection **explicit** in field kits so POCs don’t die on a 7× spreadsheet.”

---

## Seat intel + guess-band (verify live before quoting)

Public U.S. list (Anthropic / Claude, mid-2026 — confirm on [claude.ai/upgrade](https://claude.ai/upgrade) and [Team plan FAQ](https://support.claude.com/en/articles/9266767-what-is-the-claude-team-plan)):

| SKU | ~$/user-mo |
| --- | ---: |
| Claude Pro | ~$20 |
| Claude Max 5× | ~$100 |
| Claude Max 20× | ~$200 |
| Team Standard | ~$25 ($20 annual) |
| Team Premium | ~$125 ($100 annual) |

**Power-user sample (Mirion POC): Gateway week ~$2,016 → ~$8,700/mo**

| Assume seat | PPT / seat | Verdict on $ |
| ---: | ---: | --- |
| $100 (Max 5×) | ~**87×** | seat wins |
| $200 (Max 20×) | ~**43×** | seat wins |
| $125 (Team Premium) | ~**70×** | seat wins |

Even at the high end of public Max, seat still wins by >40× for that profile. Org hybrid (power on seats, rest PPT) usually beats seat-all / PPT-all on dollars.

---

## Backup artifacts

- Customer-facing reconciliation: [Google Doc](https://docs.google.com/document/d/1qqjn9DZPDYubnS8gU0rnlMFt0W_Fean_IigxT2CDr7Y/edit) / `docs/unity-ai-gateway-claude-code-cost-reconciliation.md`
- Official pitch (governance only): `go/aigovernance`, [battlecard](https://docs.google.com/presentation/d/1ApQcYqaNracAw7OPqO04Q8qKJl-oxgFdxhYg9K6dMvs), [coding-agent sprawl blog](https://www.databricks.com/blog/governing-coding-agent-sprawl-unity-ai-gateway)
- Cost estimator (PPT): [Claude Code on Databricks — Cost Estimator](https://docs.google.com/spreadsheets/d/1Ae0rwl8K9pqvQ0v_VGDGxTNqUtXBZHST5cXIowIBx38)

---

## Optional slide title options

1. **Callout: Coding-agent Gateway POCs are dying on the wrong cost comparison**
2. **Gap: We sell governance; customers score Max vs PPT**
3. **Decision needed: Own the Max objection — or keep losing FinOps reviews**
