# Power-user & org economics — when seats vs PPT make sense

Use for **Type C** bake-offs and to explain why a power user’s Gateway week looks “expensive” vs Max.

**Always verify seat list prices** with the customer’s Anthropic quote — defaults below are public list as of mid-2026 and change.

## Default list prices (verify)

| Plan | Typical list | Notes |
| --- | --- | --- |
| Claude Pro | ~$20 / user / mo | Light individuals |
| Claude Max 5x | ~$100 / user / mo | Heavy individual |
| Claude Max 20x | ~$200 / user / mo | Extreme power user |
| Team Standard | ~$20–25 / seat / mo | Often lower Claude Code capacity |
| Team Premium | ~$100–125 / seat / mo | Power-user team seat; often 5-seat min |
| Enterprise | Custom seat + often API overage | Ask customer |

Gateway / Anthropic API: **pay-per-token** at four rates (fresh / cache write 1.25× / cache read 0.1× / output). Databricks hosted list ≈ Anthropic API list at published DBU × $/DBU.

---

## Core idea

**A seat is a flat option on usage.**  
**PPT is linear in tokens.**  

For one person:

```text
seat wins on $  when  PPT_monthly  >  seat_price
PPT wins on $   when  PPT_monthly  <  seat_price
```

Governance / multi-tool / Foundry may still favor Gateway even when seat wins on $.

---

## Inputs to collect (Type C)

| Input | Example |
| --- | --- |
| Seat price under consideration | $100 Max 5x or $125 Team Premium |
| PPT monthly $ for that user (four-rate or billed) | From Gateway Cost Observability |
| Or: weekly PPT $ × 4.3 | John’s week ≈ $2,016 Gateway |
| Cache hit assumption if forecasting | 60–90% typical agentic |
| Cohort mix | % power / median / light |
| Headcount N | |
| Other tools on Gateway budget | Cursor, Codex, … |

---

## Single-user break-even

### From known PPT monthly cost

```text
break_even_seat = PPT_monthly
```

If customer seat is $100 and PPT is $150 → **seat cheaper**.  
If PPT is $40 → **PPT cheaper**.

### From weekly Gateway $

```text
PPT_monthly ≈ weekly_PPT_USD × 4.3
# or × (365/7)/12 ≈ × 4.345
```

**John worked example (illustrative):**

| Metric | Value |
| --- | --- |
| Gateway week (Unity $) | ~$2,016 |
| Implied monthly if sustained | ~$2,016 × 4.3 ≈ **$8,700** |
| Max 20x seat | ~$200 / mo |
| Max 5x / Team Premium | ~$100–125 / mo |
| Seat vs that PPT week | **Seat wins by ~40–80× on $ for that intensity** |

That is the power-user insight: **honest PPT for a Max-tier agentic week can dwarf any Claude seat.** The 7× table vs `$291` Claude UI estimate understates how bad PPT looks vs Max — and Max still wins that fight.

Their `$291` Claude list estimate for the week ≈ `$1,250` / mo if sustained — still ≫ $200 Max, so even their *undercounted* meter already implies seats win for John.

### From tokens (forecast)

Sonnet 5 intro Global list ($2 / $10 / $2.50 / $0.20 per 1M):

```text
PPT_USD ≈
  fresh_M     * 2.00
+ cache_w_M   * 2.50
+ cache_r_M   * 0.20
+ output_M    * 10.00
```

If only gross input `I` and output `O` known, assume cache-read share `h`:

```text
fresh = I * (1 - h)
cache_r = I * h
# ignore cache write for directional (or add ~few % of I at 1.25× once)
PPT ≈ fresh*2 + cache_r*0.20 + O*10   # Sonnet 5 intro $/1M tokens, I and O in millions
```

| Monthly tokens (Sonnet-heavy, h=75%) | Rough PPT $/mo | vs $100 seat | vs $200 seat |
| --- | ---: | --- | --- |
| Light: 2M in / 0.5M out | ~$2.5 | PPT wins | PPT wins |
| Median: 20M in / 5M out | ~$25 | PPT wins | PPT wins |
| Heavy: 100M in / 20M out | ~$110 | ~tie Max 5x | PPT wins |
| Power (John-ish): ~800M+ in / 12M out / week | thousands | Seat wins | Seat wins |

*(Directional — swap rates for Opus/Haiku mix.)*

---

## Org model (the interesting part)

Don’t average one John across the company.

```text
N = headcount
p_power, p_median, p_light   # fractions summing to 1
cost_seat = N * seat_price   # or mix: n_prem * prem + n_std * std

cost_PPT =
  N * p_power  * PPT_power
+ N * p_median * PPT_median
+ N * p_light  * PPT_light
```

### Hybrid (often the honest recommendation)

| Cohort | Buy |
| --- | --- |
| Power users (top ~5–15%) | Max / Team Premium seats **or** accept high PPT + hard Gateway budgets |
| Median / light | Gateway PPT (or Team Standard if they stay in Anthropic seats) |
| Org needing one audit/budget/MCP plane | Gateway in front even if some seats remain |

**Gateway still wins the control-plane bake-off** when they need one budget across Claude + Cursor + Codex, UC audit, MCP policy — even if power users stay on seats for $ and Gateway covers the long tail + governance.

### Example org (illustrative)

N = 200; power users burn ~$8,700/mo PPT (John-like); median $40; light $8; Max/Premium seat $100–200.

| Mix | Seat-all | PPT-all | Hybrid (power on seats, rest PPT) |
| --- | ---: | ---: | ---: |
| 10% power / 30% med / 60% light, $200 seat | $40k | ~$177k | **~$7.4k** |
| 5% power / 25% med / 70% light, $100 seat | $20k | ~$90k | **~$4.1k** |

**Takeaway:** One John makes **PPT-all disastrous** and **seat-all wasteful** for light users. **Hybrid** — seats for the tip of the spear, PPT for everyone else — usually wins on $. Gateway still attaches for governance / multi-tool / Foundry even on the PPT cohort (and can front seats if product supports it).

---

## How the skill should use this

When Type C or power-user economics come up:

1. Compute `PPT_monthly` from Gateway week/month or token forecast.  
2. Compare to stated seat price → **seat_wins_usd** true/false for that user.  
3. If only power users in scope → say clearly: **on $, seats win; Gateway bake-off must be governance/Foundry/org mix.**  
4. If N and cohorts given → run org table; recommend seat-all / PPT-all / hybrid.  
5. Fold into bake-off call:
   - Pure Max death-match + power-only → **NO-GO (reframe)**  
   - Org mix + platform sponsor → **GO** Type C even if John-seat wins  

### Output snippet to include

```text
## Economics snapshot
- Power-user PPT (period): $…
- Annualized / monthly PPT: $…
- Seat under consideration: $… / mo
- For this power user on $: seat wins | PPT wins | tie
- Org (if N known): seat-all $… | PPT-all $… | hybrid $…
- Implication for bake-off call: …
```

---

## Script

Run `scripts/seat_vs_ppt.py` for quick numbers (see `--help`).

```bash
python3 ~/.cursor/skills/ai-gateway-coding-agent-bakeoff/scripts/seat_vs_ppt.py \
  --weekly-ppt 2016 --seat 200 --n 200 \
  --pct-power 10 --ppt-power 800 --ppt-median 40 --ppt-light 8
```

---

## Positioning lines (power-user)

> For a Max-tier power user, flat seats often crush pay-per-token on dollars — John’s Gateway week at ~$2k already implies ~$8k+/mo PPT vs ~$100–200 Max. That’s expected. The interesting question isn’t “can Gateway beat John’s Max seat?” (usually no). It’s whether the **org** is mostly Johns, or mostly light/median users plus a few Johns — and whether you need one governed plane across tools. Many teams hybrid: seats for the tip of the spear, Gateway PPT + budgets for everyone else and for Cursor/Codex.
