---
name: ai-gateway-coding-agent-bakeoff
description: >-
  Produce customer bake-off artifacts for Unity AI Gateway vs Claude Code
  (Slides, comparison Sheets, scorecard Docs): intake, win/lose call, power-user
  economics, and filled templates. Use when the user wants a customer
  presentation, comparison sheet, FinOps readout, Max vs PPT model, or asks what
  to collect before comparing Gateway vs Claude Code costs.
user-invocable: true
---

# AI Gateway Coding-Agent Bake-off Skill

**Primary output = customer artifacts** (Google Slides + comparison Sheet + optional Doc), not chat-only advice.

Supports intake, win/lose qualification, power-user economics, then **build the leave-behinds**.

## Non-negotiables

1. Define bake-off type before numbers.
2. Never accept “cheaper than Max for one power user” as the only success metric.
3. Never compare Claude Code `/usage` × list to Gateway $ without cache breakout.
4. Don’t say caching is ignored unless cache-read ≈ 0% on current traffic.
5. No internal ticket IDs in customer artifacts.
6. Every run includes bake-off call: GO / CONDITIONAL GO / NO-GO / PAUSE.
7. **When user wants a presentation or comparison → generate Slides/Sheet/Doc** via `google-slides` / `google-sheets` / `google-docs` (see `references/artifacts.md`). Never auto-share Drive files.

## What you produce

| Artifact | Template |
| --- | --- |
| Customer Google Slides | `references/slides-outline.md` → **google-slides** skill |
| Comparison Google Sheet | `references/sheet-spec.md` + `assets/comparison-sheet-seed.tsv` → **google-sheets** |
| Scorecard Google Doc | `references/bakeoff-scorecard.md` → **google-docs** |

Default customer package: **Slides + Sheet**. Add Doc if they want a leave-behind narrative.

## Bake-off types

| Type | Question |
| --- | --- |
| **A** | API list parity / metering |
| **B** | Control plane vs Foundry |
| **C** | Org seat vs PPT (+ power-user math) |
| **D** | Single Max user — context only |

## Workflow

### 1. Charter + intake
`references/intake-checklist.md` — stop if only Max screenshots and no charter.

### 2. Qualify
`references/win-lose-positioning.md` → call + position + FE time.

### 3. Economics (if power user / org $)
`references/power-user-economics.md` + `scripts/seat_vs_ppt.py`.

### 4. Diagnostics (if GO / CONDITIONAL and data exists)
`references/diagnostics-sql.md`.

### 5. **Build artifacts** (default when user asked for presentation / comparison / customer back)
1. Read `references/artifacts.md`
2. Fill `slides-outline.md` placeholders (use TBD where unknown)
3. Fill sheet seed / OrgModel / PowerUser tabs
4. Invoke **google-slides** (CLI/Databricks template for customer-facing)
5. Invoke **google-sheets** for comparison model
6. Optional: google-docs scorecard
7. Return links + AE speaker notes (3 bullets)
8. Ask before sharing

If Google auth blocked: write filled markdown + TSV to workspace/`/tmp` and say so.

### 6. Close with call block

```text
## Bake-off call
- Call: …
- Position now: …
- FE time: …
## Artifacts
- Slides: <url or path>
- Sheet: <url or path>
- Doc: <url or path or n/a>
```

## Positioning cheat sheet

| Situation | One line |
| --- | --- |
| 7× metering | Different meters; four-rate + cache; API list parity |
| Max cheaper | Expected for power users; not Gateway’s job |
| Org | Hybrid: seats for Johns, PPT for long tail |
| Foundry | Control plane bake-off; $ near parity |
| Cache ~0% | Fix path; pause $ slides |

## Progressive disclosure

| Need | Read |
| --- | --- |
| **Artifacts / Slides / Sheet** | `references/artifacts.md` |
| Slide content | `references/slides-outline.md` |
| Sheet layout | `references/sheet-spec.md` |
| Intake | `references/intake-checklist.md` |
| Win/lose | `references/win-lose-positioning.md` |
| Power-user math | `references/power-user-economics.md` |
| Scorecard | `references/bakeoff-scorecard.md` |
| SQL | `references/diagnostics-sql.md` |
| Talk tracks | `references/talk-tracks.md` |

## Field resources

- `go/aigovernance`
- [Coding agent sprawl blog](https://www.databricks.com/blog/governing-coding-agent-sprawl-unity-ai-gateway)
- [Pricing](https://www.databricks.com/product/pricing/proprietary-foundation-model-serving)
- `#ai-gateway`
