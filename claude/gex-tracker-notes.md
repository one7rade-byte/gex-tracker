# GEX Tracker notes
NOTE 2026-11-01: original notes file was not found in the repo (branch or main); this stub was created by the weekly research run.
NOTE 2026-11-07: the original long-form notes live in the claude.ai Project "GEX " as doc `claude/gex-tracker-notes.md` (history through 2026-10-22). This repo file tracks research-routine state only.

## Known open items
(updated 2026-11-11)
- P0 (SMH/RSP rotation shakeout) INCONCLUSIVE 2026-11-11: dip-within-10d 42% vs 19% base, but 20d upside is threshold-fragile (6 episodes, 0 fires 2010-17); confirmation entries didn't help; credit-selling subgroup (HYG/IEF 10d <= -1) 2 bad of 4. Not wired in.
- P1 (vol-free STRONG_BUY gate) REJECTED 2026-11-07: keep composite>=1.
- Real live gap: Oct 16-Nov 3 STRONG_BUY cluster (composite 4.5-4.7) fired with rotation R ON + HYG/IEF 10d -1.5 to -2.0; 10d outcomes -0.88/-3.86/-1.26. STRONG_BUY fired again 11-10 with R ON (credit calmer). Next: P8 (re-fire / rotation+credit veto / RSI<40).
- Remaining priority items: P0b (quick_action persistence), P2 (MAE in track_signal_performance.py), P3, P5, P6, P7, P8.
- Event 2026-11-05: confirmation entries (753.01) cost 2.5% vs trigger close (734.40), no drawdown avoided so far (trigger close was the low).
- STRONG_BUY setup is untestable pre-2010 in deep history (SKEW>138 only 2 days pre-2010); deep tests are effectively 2010+.
- Research routine CAN push to claude/research.
- ROC layer (composite_5d_chg, hyg_5d_pct): not in code; ~1.5-3x lift, poor lead time (2026-11-01).
- macro_history.csv last row 2026-08-17 (stale); deep_history_backtest_log.csv ends 2026-08-21 — re-run deep_history_backtest.yml to cover the Nov-2026 event.
- Sandbox can't reach Yahoo/FRED/CFTC; ideas 1,3,4,5,7 need allowlist (flow_history.csv now covers VIX3M, so idea 5 is testable locally).
- Bottom/risk-on-turn detection untested.
