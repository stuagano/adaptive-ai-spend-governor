# Talk tracks — AI Gateway coding-agent cost

## Customer / AE — before you have numbers

> Before we debate price, let’s lock a fair bake-off. We need, for the **same people and same dates**: Claude Code plan (Max/Team/API), Models/`/usage` In/Out, Gateway usage + $, and ideally `system.ai_gateway.usage` cache fields. Also: what does “win” mean — API cost parity, Foundry comparison, or org-wide seat vs metered TCO? We should not use one power user’s Max week × list as the only scoreboard.

## Customer / AE — metering objection (“Gateway is 7×”)

> Looking at the table — the gap is almost entirely the **input meter**, not Gateway list being ~7× Anthropic API.
>
> Output is comparable. Unity **input** is often tens to thousands of times Claude Code’s “In.” Claude Code `/usage` (especially Max/Team) is not the same as pay-per-token Gateway metering of full agentic request input (often cache-inclusive).
>
> Unity’s reported $ is also usually **not** full-rate on those input tokens. If full-rate on Unity In would be much higher than Unity Cost, a large share is already billed as cache reads at 0.1× — same multipliers as Anthropic.
>
> List parity: Claude on Databricks is $0.07/DBU × published DBUs = Anthropic public list (incl. cache). Like-for-like is Unity token mix × four rates vs Anthropic API — not vs Claude Code UI $.
>
> Next check: `cache_read_input_tokens / input_tokens` in `system.ai_gateway.usage`. High % → rebuild with four rates. Near 0% on current traffic → we dig into the integration path.

## Customer / AE — Max is cheaper (commercial objection)

> Fair — if this is one power user optimizing seat economics, Claude Code Max/Team can win. Databricks is not trying to beat that conversation on standalone seat price.
>
> We win when you need many developers and many AI tools: governed MCP access, one budget across Claude Code / Cursor / Codex / Gemini CLI, audit in Unity Catalog, chargeback, provider portability, and a Foundry-class control plane — at **Anthropic API list parity**, not Max ARPU.
>
> Fair bake-off: Gateway vs Anthropic API or Azure AI Foundry, plus platform value. Optional: org-wide seat math vs metered usage. Unfair: Gateway invoice vs one user’s `/usage` × list.

## 30-second pitch (governance)

> Anthropic sells Claude access; Databricks sells governed enterprise adoption of coding agents. Keep developer tool choice; give admins one control plane for security, spend, and observability.

## Leadership / offsite (internal)

**Open:** Customers aren’t confused that we charge DBUs. They’re comparing a subscription seat to a metered bill and concluding we lose.

**Bridge:** Technically fine at Anthropic API list — including cache. Commercially, Max can win for heavy individuals. That’s expected.

**Close:** Pitch already says governance, not cheaper Claude. Ask: make that objection explicit in field kits so POCs don’t die on a 7× spreadsheet.

## What not to say

| Don’t | Say instead |
| --- | --- |
| “Gateway is cheaper than Max” | “Max can win for heavy seats; Gateway wins on governance + API parity” |
| “Databricks ignores caching” | “Run cache %; Unity $ often already shows cache discounts” |
| “Your Claude Code $ is wrong” | “Different meters — here’s how to reconcile” |
| “See ticket ES-…” | Describe the diagnostic and escalate internally |
| “The battlecard says Max is more expensive” | It doesn’t — use this skill’s commercial frame |
| “Let’s keep analyzing until Max loses” | “NO-GO on that scoreboard — reframe or walk” |

## Qualify first (see win-lose-positioning.md)

Before a long reply, state: **GO / CONDITIONAL GO / NO-GO (reframe) / PAUSE**, what it’s winnable on, and the position for that scenario.

## Channels

- Product / path issues: `#ai-gateway`
- Coding agents at Databricks: `#ai-devtools` / `#ai-devtools-support`
- Field hub: `go/aigovernance`
