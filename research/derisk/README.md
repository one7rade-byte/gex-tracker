# De-risking patterns: backtest and forward test

**Question:** is there a pattern that warns early enough to reduce risk before a big drop, without costing too much in normal markets?

## Backtest (2007-04 → 2026-11, `derisk_study.py`)
Base rate: on days when SPY is within 5% of its 1-year high, a 10%+ drop follows within 120 sessions **25.0%** of the time (20%+: 4.7%). This window has 8 big drops: 2007, 2015, 2018 (×2), 2020, 2022, 2025, 2026.

| Warning (only while SPY is near its high) | On % of days | 10%+ drop within 120d | Big drops caught | Trim 50% on warning, buy back at −8% (CAGR / max DD vs hold 8.53% / −56.5%) |
|---|---|---|---|---|
| W1 **semis_lead**: SMH lags SPY by 10%+ over 60d | 1.6% (6 episodes) | **42.4%** | 2/8 | **8.84% / −53.5%** (bought back cheaper 4 of 7 times) |
| W2 narrow_rally: RSP lags SPY by 4%+ over 60d | 3.9% | 9.1% | 4/8 | (no better than holding) |
| W3 smallcap_lag: IWM lags SPY by 8%+ over 60d | 2.2% | 27.0% | 2/8 | (no better than holding) |
| W4 **credit_lead**: HYG/IEF −2%+ over 20d | 6.1% (39 episodes) | **47.4%** | 5/8 | 8.32% / −53.7% (bought back cheaper 15 of 37 times) |
| W5 vol_creep: VIX/VIX3M ≥ 0.95 within 3% of the high | 4.1% | 29.4% | 7/8 | 7.49% / −55.2% |
| W7 two_or_more of W1–W5 | 2.4% | 32.0% | 7/8 | 8.63% / −53.5% |
| Control: SPY below its 200-day average (hold 50%) | 23.0% | (already falling) | n/a | 7.62% / **−37.0%** |

**Verdict:** no warning is good enough to act on yet.
- Semis and credit roughly double the odds of a drop, but they're noisy or rare. Trimming on them barely changed returns or drawdowns.
- Warnings near highs switch off once SPY is 5% below its high, so they can only cut risk *before* the fall.
- The one rule that really cut drawdowns (below the 200-day) cost about 0.9 pts/yr and contradicts the buy-low plan.
- The proven edge is buying deep drops well (`../drawdown_2026/`), not timing exits.

## Forward test: rules FROZEN on 2026-11-25
`forward_test.py` runs every day in `gex_daily.yml` and logs W1–W5, W7 and the 200-day control to `forward_log.csv`. After 120 sessions it records whether a 10%+ / 20%+ drop followed, and `forward_summary.json` compares each warning with the base rate. **Do not change the thresholds:** results only count on data the rules never saw.

**Pass bar (proposed):** after 12+ months of resolved data, a warning passes if its 10%+ drop rate is at least 1.5× the base rate and it fired before the next real drop. Only then is it worth wiring into Quick Action as a "trim" signal.

The research agent also tracks one live-only hypothesis that can't be backtested (GEX data starts 2026): GEX getting less negative at a new RSI<30 low (backlog P0d).
