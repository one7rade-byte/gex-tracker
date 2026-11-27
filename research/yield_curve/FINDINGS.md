# 2y/10y yield curve regimes vs SPY (1995-10 → 2026-11)

Data: U.S. Treasury daily par yield curve (1990+, `yield_curve.py`, updated daily). It matches FRED DGS2 exactly on all 9,230 overlapping days. `DGS2_fred_1976.csv` (from Simon) extends the 2y back to 1976 for recession-era work. Regime = the 20-session change in the 2y and 10y yields; FLAT when the 10y−2y spread moved less than 10bp. Study: `curve_study.py`.

| Regime (share of days) | SPY median 120d | Up after 120d | 10%+ drop within 120d | Since 2010: median 120d / 10%+ drop |
|---|---|---|---|---|
| All days | +5.8% | 72.8% | 24.6% | +6.7% / 20.7% |
| Bull steepener (7.8%): the market expects Fed cuts | **+0.7%** | 51.2% | **43.6%** | **+11.0% / 12.8%** |
| Bull flattener (14.2%): growth fears, flight to safety | +6.8% | 81.0% | 22.2% | +7.4% / 19.8% |
| Bear steepener (12.9%): inflation / fiscal / term premium | +8.6% | 77.4% | 21.3% | +9.3% / 16.2% |
| Bear flattener (8.8%): the Fed is tightening | +3.1% | 66.6% | 28.1% | **+3.3% / 32.1%** |
| Flat (56.2%) | +5.9% | 73.6% | 22.7% | +6.0% / 21.3% |

## What it means
- **The bull steepener depends on why the Fed is cutting.** Before 2010 it meant "something broke" (2001, 2007–08): −4.9% median, and a 10%+ drop followed 56% of the time. Since 2010 the cuts have been "insurance" cuts and it was the best regime. To tell the two apart, check credit and the deep-drop switch in Quick Action.
- **The bear flattener (active tightening) has been the weakest regime since 2010.** That matches the "late-cycle warning" in the chart.
- **The bear steepener did not hurt stocks on average**, contrary to the chart's "pressures equities".
- **Inversion itself isn't a short-term sell signal** (+6.8% median 120d). The **un-inversion** after a long inversion has a worse record: 2000-12, 2007-03 and 2024-08 were each followed by a drop of 10.7% to 27% within a year. That's only 3 cases.

## On the dashboard
The Quick Action card (and Telegram) shows the current regime, yields, spread, 20-day changes and the regime's record since 2010. It's informational only: no buy or trim rule uses it yet. The research agent forward-tracks the regime (backlog P0f).
