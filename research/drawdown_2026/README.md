# 2026 drawdown study: from first signs to full recovery

**Question:** what does a drop like this look like at every stage (first warnings, the fall, the bottom, the turn), and what does buying low along the way actually return? The study also asks whether this is the AI bubble popping or a correction.

**Window:** SPY's all-time-high close on **2026-10-06 (779.09)** until SPY closes at a new all-time high. QQQ peaked the same day. Semis (SMH) peaked earlier, on 2026-06-22, and had already fallen about 22% by Nov 3. That was the earliest warning in our own data. A scheduled task updates the study every trading day, and the final report is written when SPY recovers.

## Files
| File | Where | What |
|---|---|---|
| `ladder_history.py` / `ladder_history.json` | main | Every SPY (1995+) and QQQ (1999+) drawdown: how far drops went after each tier, and what buying at each tier returned |
| `track_drawdown.py` | main | Daily numbers: drawdowns, stage, credit, vol, yields, flows, and the ladder ledger |
| `drawdown_log.csv`, `ladder_ledger.csv`, `stage.json` | branch `claude/event-2026-11-05` | Daily output |
| `CAUSE_LOG.md` | branch `claude/event-2026-11-05` | The *why*: dated catalysts and the AI-bubble scoreboard, one entry per day |

## The buy-low ladder (also in `quick_action.py`)
| Tranche | SPY vs high | SPY price | Share of dip-buying cash |
|---|---|---|---|
| 1 | −8% | 716.76 | 15% |
| 2 | −12% | 685.60 | 15% |
| 3 | −16% | 654.44 | 20% |
| 4 | −20% | 623.27 | 20% |
| 5 | −25% | 584.32 | 15% |
| 6 | −30% | 545.36 | 15% |

Why this spacing (SPY 1995+, 19 drops that reached −8%): 67% went on to −10%, 39% to −15%, 28% to −20% and 17% to −30%. The median final bottom was −11.6%. Buying at −8% was positive after 12 months 12 of 17 times (median +15.6%), but it typically sat through about −9% more first. QQQ, which is now at −15%: 7 past drops reached −15%. 83% of them went to −20% and 33% to −30% (median bottom −25.9%), and those include 2000–02.

## Stages (decided from the data each day)
NEAR HIGH → FALLING (a new low in the last 5 sessions) → BASING (no new low for 5+ sessions) → RECOVERING (back within 5% of the high) → RECOVERED (new all-time high).

## AI-bubble scoreboard: what would separate "correction" from "bubble popping"
| Area | Correction looks like | Bubble popping looks like |
|---|---|---|
| Demand | AI revenue and guidance still rising | Guidance cuts, order cancellations, GPU prices falling |
| Capex | Hyperscalers hold or raise capex | Capex cuts or "digestion" language from 2+ hyperscalers |
| Financing | Spreads wider but deals still get done | Failed or pulled deals; HY/AI credit breaks (HYG/IEF 20d ≤ −3%) |
| Market breadth | Equal-weight and defensives hold up (rotation) | Equal-weight and credit fall with tech (de-risking) |
| Rates/Fed | Hikes priced and absorbed | Hiking into falling demand |
| Leaders' prices | Leaders fall less on good news | Leaders fall on good news (NVDA did this on 11-18) |
