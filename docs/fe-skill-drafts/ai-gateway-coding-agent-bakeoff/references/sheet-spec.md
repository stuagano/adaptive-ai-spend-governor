# Comparison Google Sheet — spec

Create with **`google-sheets`** skill. Seed values from `assets/comparison-sheet-seed.tsv` (tab-separated).

## Tabs

### 1. Cover
| Cell | Content |
| --- | --- |
| A1 | Customer |
| B1 | {{customer}} |
| A2 | Window |
| B2 | {{start}} → {{end}} (TZ) |
| A3 | Bake-off types |
| B3 | A / B / C / D |
| A4 | Call |
| B4 | GO / CONDITIONAL / NO-GO / PAUSE |
| A5 | Seat $/user-mo (verify) |
| B5 | 100 |
| A6 | $/DBU list (verify) |
| B6 | 0.07 |

### 2. TokenCompare
Columns: Model | CC_In | CC_Out | GW_In | GW_Out | In_Ratio | Out_Ratio | Notes

`In_Ratio = GW_In/CC_In` (if CC_In>0)

### 3. FourRateCost
Per model (example Sonnet 5 intro — swap rates):

| Col | Meaning |
| --- | --- |
| Model | |
| Fresh_In | GW_In − Cache_Read − Cache_Write (floor 0) |
| Cache_Read | from token_details |
| Cache_Write | from token_details |
| Output | GW_Out |
| Rate_Fresh | e.g. 2 |
| Rate_CW | e.g. 2.5 |
| Rate_CR | e.g. 0.2 |
| Rate_Out | e.g. 10 |
| USD | Fresh/1e6*RF + CW/1e6*RCW + CR/1e6*RCR + Out/1e6*RO |
| FullRate_If_No_Cache | GW_In/1e6*RF + Out/1e6*RO |
| Cache_Implied | FullRate − USD (directional) |

Also row: **Their_CC_List_Estimate** (CC_In/1e6*RF + CC_Out/1e6*RO) for contrast — label clearly as *not* API-like-for-like.

### 4. PowerUser
| | |
| --- | --- |
| Gateway week USD | |
| Monthly ≈ week×4.3 | formula |
| Seat USD | |
| PPT/seat ratio | formula |
| Verdict | seat wins / PPT wins |

### 5. OrgModel
Inputs: N, pct_power, pct_median, ppt_power, ppt_median, ppt_light, seat  
Outputs: seat_all, ppt_all, hybrid (power on seats, rest PPT), cheapest  

### 6. IntakeGaps
Checklist status from intake-checklist.md

### 7. Rates (reference)
Paste model DBU rates × $/DBU; note Sonnet 5 intro end date.

## Sheet title
`[Customer] Unity AI Gateway × Claude Code — Comparison model`
