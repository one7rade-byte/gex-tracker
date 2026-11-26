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

## The buy plan (in `quick_action.py`; evidence in `buy_plan_study.py`)
**Normal correction: one buy at −8% from the high** (716.76 this time). Of 17 SPY drops since 1995 that reached −8%, this filled every time, returned a median +15.6% over 12 months (12/17 positive), and typically saw about −9% more first. Waiting for −10% or the first oversold day either missed drops or did no better.

**Deep / black-swan drop: 3 buys**, switched on by a **second leg**: SPY closes 5%+ below its first-oversold (RSI<30) close. That happened in **5/5 drops of 20%+** (2000, 2007, 2018, 2020, 2022), in 3/3 drops of −14% to −20% (1998, 2015, 2025), and in **0/9 mild corrections**. It fires at a median −15.7% from the high.
| Buy | Level | This time |
|---|---|---|
| 1 | −8% from the high | 716.76 (hit 2026-11-19) |
| 2 | the second leg: 5% under the first-oversold close | 655.32 (first oversold 2026-11-20 at 689.81) |
| 3 | −25%, or 5 straight closes above the 50-day average, whichever comes first | 584.32 |

The 5-day reclaim fixed 2018 (a 1-day reclaim fired on Dec 3, before the Dec 24 low). In real bear markets (2000, 2008) every early buy still went on to lose another 40%+. Three buys limit the damage; they don't avoid it.

`ladder_ledger.csv` still measures −8/−12/−15/−20/−25/−30% for research.

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
