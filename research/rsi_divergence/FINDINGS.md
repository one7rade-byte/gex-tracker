# RSI bear divergence → oversold: does the chart's pattern work?

Prompted by a StockCharts SPX chart (2026-11-24). It shows three cycles of "RSI bear divergence at the highs, then an oversold reading", plus a break of the trendline from the April 2025 low. Tested on SPY 1995+ and QQQ 1999+ (`rsi_study.py`, results in `rsi_study.json`).

## 1. As a crash warning: no edge
- **Definition:** a close at a 60-day high within 2% of the 1-year high, RSI(14) below 70, and an earlier high in the prior 15–120 sessions at a lower price with RSI 70+ and at least 5 points higher. First signal per 40 sessions.
- **How often it fires:** 68 times on SPY (about 2 a year).
- **What followed vs any other high:**

  | After… | Fell −5% within 60 days | Fell −10% within 120 days | Fell −20% within 120 days |
  |---|---|---|---|
  | A divergence | 29.9% | 15.2% | 3.0% |
  | Any other high | 29.4% | 16.2% | 4.4% |

  No better than an ordinary high.
- **Catch rate:** it showed up before 12 of 13 drops of 10%+ (92%), including Oct 6, 2026. But a divergence sits in the prior 120 sessions of **82% of all highs**, so catching tops is mostly a matter of how common it is. QQQ is the same: 12 of 14 tops caught vs 85% by chance.
- **Why the chart looks convincing:** it shows the three divergences that worked and none of the many that didn't.

## 2. As a bottom zone: useful, but expect a retest
"First oversold" = RSI(14) below 30 after 60+ sessions without one.

| SPY | n | Close undercut within 60 days | Median extra drop | Median 12-month return | Up after 12 months |
|---|---|---|---|---|---|
| All | 33 | 85% | −2.9% | +15.0% | 71% |
| VIX above 30 that day | 8 | 62% | −4.5% | **+22.5%** | 86% |
| VIX at or below 30 | 25 | 92% | −2.9% | +14.4% | 67% |

| QQQ | n | Close undercut within 60 days | Median extra drop | Median 12-month return | Up after 12 months |
|---|---|---|---|---|---|
| All | 29 | 83% | −6.0% | +14.6% | 67% |
| No divergence first | 10 | 80% | −11.7% | −8.2% | 40% (includes 2000–02) |

**Takeaway:** the first oversold reading is a good place to *start* loading, and rarely the exact low. The price usually comes back below it (the chart's "back test") before the real turn. That fits the staged ladder rather than going all in.

## Now (2026-11-24)
- **SPY:** first oversold on 2026-11-20, close 689.81, with VIX 35.9.
  - History: undercut within 60 days 62% of the time, with a median retest zone around **659**. That's close to ladder tranche 3 (654.44).
  - Buying that first oversold close returned a median +22.5% over 12 months.
  - RSI is now back to 40.5.
- **QQQ:** first oversold on 2026-11-05 and again on 11-20 (RSI 26.6). It's now 16% below its high.
- **Our live GEX (2026 only, too few cases to trust):** at the Nov 20 flush, price made a new low but GEX got *less* negative (−20.0 → −13.2) while VIX spiked to 35.9. That's dealers covering into the low. The Mar 30, 2026 low (RSI 22.8, GEX −3.5) looked similar. It can't be tested on history because GEX data starts in 2026, so the research agent tracks it on every future low.
- **The trendline break** in the chart depends on hand-picked anchor points, so it can't be tested objectively. Its "back test" idea matches the 85% retest rate above.
