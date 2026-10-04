# Weekly research log

## 2026-10-04 — Idea 8: ROC early-warning layer (composite_5d_chg, hyg_5d_pct), offline re-test

**VERDICT: inconclusive / partial — NOT a PASS. Not wired into regime_analyzer.py.**

Setup problems, stated plainly:
- `claude/gex-tracker-notes.md` does not exist in the repo (any branch), and neither do the
  2026-08-25 ROC validation script/thresholds. I could not reproduce that validation; thresholds
  below are my own sweep, not the original ones. A notes file was created this run.
- cftc.gov, fred.stlouisfed.org and Yahoo are denied by the sandbox proxy, so ideas 1-7 could not run.
  No results were faked. Ran idea 8 offline on `deep_history_backtest_log.csv` (script:
  `roc_layer_backtest.py`, output `roc_layer_backtest_summary.json`).

Method: composite_5d_chg = 5-row diff of composite_score; hyg_5d_pct = 5-day % change of HYG.
HYG era only (n=4,853 days with a full 20d forward window, 2007-04 onward). Hit = SPY closes
>=5% (or >=10%) below today's close at some point in the next 20 trading days.
Base rate: 18.0% hit the -5% mark, 4.6% hit -10%; mean fwd 20d return +0.79%.

Pooled results (fire rate / P(-5% dd) / P(-10% dd) / mean fwd20 ret):
- hyg_5d_pct <= -1.5: 8.47% / 33.6% / 12.2% / +1.36%
- hyg_5d_pct <= -2.5: 3.32% / 45.3% / 26.1% / +1.63%
- composite_5d_chg <= -3: 5.03% / 28.7% / 11.9% / +1.63%
- composite_5d_chg <= -5: 0.80% / 33.3% / 20.5% / +1.36%
- either(hyg<=-1.5, comp<=-3): 11.09% / 30.5% / 11.0% / +1.35%
- both: 2.41% / 37.6% / 17.1% / +1.98%

Era cross-check (base P(-5%) in era: 27.8% / 10.1% / 17.8%):
- 2007-2012 and 2020-2026: the signals roughly double the -5% rate (e.g. hyg<=-2.5: 49.5%, 48.7%).
- 2013-2019: effectively no edge: hyg<=-1.5 gives 14.7% vs 10.1% base, and zero -10% events
  (0 of 95 fires). Pooled numbers are driven by 2008-09 and 2020.

Episodes:
- COVID 2020 (peak 2020-02-19, -34.1% to 2020-03-23): hyg<=-1.5 first fired 2020-02-25 (+6 cal days after peak),
  composite<=-3 on 2020-01-27 (23 days before the peak; a false start for ~4 weeks). No pre-peak lead from HYG.
- 2025 selloff (peak 2025-02-19, -19.0% to 2025-04-08): composite<=-3 fired 2025-02-21 (+2 days);
  hyg<=-1.5 only on 2025-04-04 (+44 days, 2 trading days before the trough). Credit ROC lagged badly.
- Risk-on turn: hyg_5d_pct>=+2 fired 3 days after the 2020 trough and 7 days after the 2025 trough;
  composite_5d_chg>=+4 fired 7 and 21 days after. Honest read: these confirm the turn, they do not call it.
  In 10%+ drawdowns, composite_5d_chg>=+4 gave +3.42% mean fwd 20d vs +1.08% base, but n=29 days, heavily clustered.

Caveats: fires on ~11% of days with ~70% of fires NOT followed by a -5% drawdown; mean forward
return after a fire is above base (the signal flags volatility/dislocation, not direction, and it
includes sharp rebounds). Thresholds were swept on the same data they are evaluated on (no
out-of-sample holdout beyond the era split). composite_score uses fixed thresholds with copper
absent pre-2011.

Takeaway: useful as a "volatility/dislocation elevated" flag when both rules fire (37.6% / 17.1% vs 18.0% / 4.6% base),
not as a standalone de-risk or bottom call. Existing 2026-08-25 validation can't be checked from the repo.

New ideas added to backlog: #9 (VIX-ROC fast-shock detector: HYG lagged the 2025 selloff by 44 days),
#10 (episode-level risk-on turn test: day counts are clustered).
