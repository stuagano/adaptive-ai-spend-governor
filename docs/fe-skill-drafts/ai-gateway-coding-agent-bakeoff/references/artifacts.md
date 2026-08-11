# Customer artifacts — what this skill produces

The point of this skill is **customer-ready deliverables**, not just chat advice.

When the user asks for a bake-off, presentation, comparison, or customer readout, **default to generating artifacts** via FE Google tools:

| Artifact | When | How to create |
| --- | --- | --- |
| **Google Slides** (customer back) | Primary customer meeting / EBC-style readout | Invoke **`google-slides`** skill (CLI/Databricks template preferred). Fill from `references/slides-outline.md`. |
| **Google Sheet** (comparison model) | FinOps / numbers debate | Invoke **`google-sheets`** skill. Seed from `assets/comparison-sheet-seed.tsv` + formulas in `references/sheet-spec.md`. |
| **Google Doc** (scorecard) | Leave-behind / email follow-up | Invoke **`google-docs`** / `docs_document_create_from_markdown`. Use filled `bakeoff-scorecard.md`. |
| Local markdown / TSV | Offline or auth blocked | Write filled files under `/tmp` or workspace; user uploads |

**Never auto-share** Drive files. Create private → return links → ask before sharing.

## Required flow when user wants “slides / sheet / presentation”

1. Run intake + bake-off call (GO / CONDITIONAL / NO-GO / PAUSE) — short.
2. If **NO-GO (reframe)** or **PAUSE**, still offer a **short deck** that reframes or pauses — don’t build a fake “we win on $ vs Max” deck.
3. Ask which artifacts: **Slides** / **Sheet** / **Doc** / all (default: Slides + Sheet for customer backs).
4. Fill templates with customer numbers (or clearly marked placeholders).
5. Create Google files via google-slides / google-sheets / google-docs skills.
6. Return links + 3-bullet speaker notes for the AE.

## Artifact package by bake-off call

| Call | Slides | Sheet | Doc |
| --- | --- | --- | --- |
| **GO** Type A | Full metering + next steps | Token/$ reconciliation | Scorecard |
| **GO** Type B | Control plane vs Foundry | Optional $ parity tab | Scorecard + governance criteria |
| **GO** Type C | Org economics + hybrid | Seat vs PPT model | Scorecard |
| **CONDITIONAL GO** | “What we need” + working hypothesis | Intake checklist tab | Short asks list |
| **NO-GO (reframe)** | 4–5 slides: wrong scoreboard / propose new charter | Optional power-user economics only | 1-pager reframe |
| **PAUSE** | Path/cache fix first | None or diagnostic only | Asks list |

## Naming

```text
[Customer] Unity AI Gateway × Claude Code — Bake-off readout
[Customer] Unity AI Gateway × Claude Code — Comparison model
[Customer] Unity AI Gateway × Claude Code — Scorecard
```
