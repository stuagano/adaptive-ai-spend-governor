# Win / lose qualification + positioning

After intake (even partial), the skill **must** output a clear call:

| Call | Meaning |
| --- | --- |
| **GO** | Worth FE/AE time; winnable on a fair scoreboard |
| **CONDITIONAL GO** | Winnable only if charter/path/access conditions are met first |
| **NO-GO (reframe)** | Current frame is unwinnable; change success criteria or walk |
| **PAUSE** | Technical blocker (path/cache/access); don’t debate $ yet |

Always pair the call with **how to position** (exact talk track) and **what “win” looks like**.

---

## Decision tree (use in order)

### 1. What is their kill criterion?

| If they say win = … | Call | Position |
| --- | --- | --- |
| Cheaper than Claude Code Max for 1–few power users | **NO-GO (reframe)** | “Max can win that. We won’t pretend otherwise. Useful next step is org TCO or API/Foundry parity — not this.” |
| Prove Databricks isn’t overcharging vs Anthropic API | **GO** (Type A) if data access exists | Metering + four-rate; governance secondary |
| Pick enterprise control plane (Gateway vs Foundry) | **GO** (Type B) | Governance + list parity; $ near-flat expected |
| How do we buy Claude for N engineers? | **GO** (Type C) | Seat vs PPT cohort math + multi-tool budget |
| Fix 7× table / “caching broken” | **CONDITIONAL GO** | Fix comparison first; then Type A |

### 2. Buyer / sponsor signals

| Signal | Tips toward |
| --- | --- |
| Platform / CISO / FinOps / AI governance sponsor | **GO** |
| Only the power-user developer + AE | **NO-GO (reframe)** unless sponsor joins |
| Already in Foundry / CogMed consolidation | **GO** Type B |
| “We just want cheaper Claude” | **NO-GO (reframe)** |
| Multi-tool sprawl (Cursor + Claude + Codex) | **GO** Type B/C |
| Will not share cache SQL / admin access and won’t accept FE-run queries | **CONDITIONAL GO** → likely **PAUSE** on Type A |

### 3. Technical readiness

| Signal | Call |
| --- | --- |
| Cache read % high on current traffic | Type A economically clean → advance |
| Cache read % ~0% | **PAUSE** — fix `ucode` / `/ai-gateway/anthropic` before $ debate |
| Only Coding Agents tab (no Cost Observability / billing) | **CONDITIONAL GO** — wrong scoreboard |
| External BYO keys but using hosted DBU narrative | **CONDITIONAL GO** — switch to `external_model_spend` |
| Different users/weeks | **PAUSE** — re-pull |

### 4. Commercial shape (Type C quick sniff)

| Shape | Call |
| --- | --- |
| Many light/median users, few power users | **GO** — PPT often wins org TCO |
| Org is 10 power users on Max, no broad rollout | **NO-GO (reframe)** — seats win; don’t force Gateway on $ |
| Broad rollout + MCP/audit requirements | **GO** even if seats slightly cheaper |

---

## Scenario playbooks (positioning)

### Scenario W1 — Winnable: “Gateway is 7× / caching ignored” (FinOps + platform)

**Call:** CONDITIONAL GO → GO after Type A data  
**Win looks like:** Four-rate / billed $ ≈ Anthropic API list; cache % explained; trust restored  
**Position:**

> You’re comparing two meters. Let’s lock the same users/dates, pull cache breakout from `system.ai_gateway.usage`, and rebuild with four rates. Databricks list for Claude matches Anthropic API (incl. 0.1× cache read). If Unity $ is already well below full-rate on gross In, caching is in the bill. After that, we can talk governance — not before.

**Do:** Run intake + SQL.  
**Don’t:** Argue Max. Don’t concede overbilling at list without cache %.

---

### Scenario W2 — Winnable: Foundry / consolidation bake-off

**Call:** GO (Type B)  
**Win looks like:** Gateway chosen as control plane; $ parity acceptable  
**Position:**

> This isn’t Max vs Databricks. It’s which enterprise control plane governs coding agents — Gateway or Foundry. Expect near list parity on tokens either way. Score audit, MCP policy, one budget across tools, UC identity, and commit fit. We’ll still clean the metering so FinOps isn’t spooked.

---

### Scenario W3 — Winnable: Org-wide seat vs PPT

**Call:** GO (Type C) if headcount + cohorts available  
**Win looks like:** Clear recommendation seats / PPT / hybrid with numbers  
**Position:**

> For one heavy Max user, seats often win. For N engineers with a power/median/light mix — plus Cursor/Codex — metered + one Gateway budget is the real TCO question. Let’s build that model; John’s week is an input, not the answer.

---

### Scenario L1 — Bad use of time: Max death-match

**Call:** NO-GO (reframe)  
**Why:** Seat vs PPT for power users — Databricks usually loses on $. Fighting it burns POC.  
**Position (AE → customer):**

> If the only bar is “Gateway cheaper than Max for our heaviest Claude Code users,” we should stop. That’s often true for seats and isn’t what Gateway is for. If leadership cares about governed rollout, multi-tool spend, or Foundry-class control, we reframe the bake-off. If not, don’t spend another cycle on the 7× spreadsheet.

**Position (AE internal):**

> Qualify out or escalate to sponsor. Do not staff a 2-week FE metering deep-dive to “beat Max.”

---

### Scenario L2 — Bad use of time: No sponsor, only screenshots

**Call:** NO-GO (reframe) or PAUSE  
**Why:** Can’t change decision criteria; spreadsheet theater.  
**Position:**

> Happy to help once we have a written success criterion and FinOps/platform on the thread. Screenshots alone will keep producing 7× forever.

---

### Scenario P1 — Pause: Cache ~0% / wrong path

**Call:** PAUSE  
**Position:**

> Economics aren’t the issue yet — caching isn’t showing on the wire. Let’s get Claude Code on `ucode` / `/ai-gateway/anthropic`, re-measure cache %, then reopen the cost conversation. Scoring $ now will just confirm a broken path.

---

### Scenario P2 — Pause: Wrong dashboard

**Call:** PAUSE / CONDITIONAL GO  
**Position:**

> Coding Agents activity isn’t the bill. We need Cost Observability / `system.billing.usage` (or `external_model_spend` if BYO). Same for tokens: Usage tab or `ai_gateway.usage` with `token_details`.

---

## Output format (required every time this skill runs)

End the response with this block:

```text
## Bake-off call
- Call: GO | CONDITIONAL GO | NO-GO (reframe) | PAUSE
- Confidence: high | medium | low
- Why: <1–3 bullets>
- Winnable on: <what scoreboard>
- Unwinnable on: <what to refuse>
- Position now: <2–4 sentence talk track>
- Next ask of customer/AE: <bullets>
- FE time recommendation: invest | invest only if charter changes | walk
```

### Examples of good calls

**Invest:**
> Call: GO — Type A + B. Sponsor is FinOps + platform. They’ll accept API parity + governance. Reframe Max as context only.

**Walk:**
> Call: NO-GO (reframe). Kill criterion is beat Max for 5 power users; no platform sponsor. FE time recommendation: walk.

**Invest only if:**
> Call: CONDITIONAL GO. Winnable as Type C if they give headcount cohorts; otherwise Max death-match → walk.
