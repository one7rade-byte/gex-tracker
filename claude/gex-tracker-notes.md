# GEX Tracker notes
NOTE 2026-11-01: original notes file was not found in the repo (branch or main); this stub was created by the weekly research run.
NOTE 2026-11-07: the original long-form notes live in the claude.ai Project "GEX " as doc `claude/gex-tracker-notes.md` (history through 2026-10-22). This repo file tracks research-routine state only.

## Known open items
(updated 2026-11-07)
- P1 (vol-free STRONG_BUY gate) REJECTED 2026-11-07: vol-only-blocked setups hit 50% at 20d with 62.5% seeing a >=3% drawdown (9 episodes since 2010); keep composite>=1. Waiting for the gate to pass costs ~1.2% and avoids no drawdown.
- Real live gap: the Oct 16-Nov 3 STRONG_BUY cluster fired with composite 4.5-4.7 and is -2.2% to -3.7%; backlog P8 (re-fire / whale-flow veto / RSI<40).
- Next priority items: P0 (SMH/RSP rotation shakeout), P0b (quick_action persistence), P2 (MAE in track_signal_performance.py).
- STRONG_BUY setup is untestable pre-2010 in deep history (SKEW>138 only 2 days pre-2010); deep tests are effectively 2010+.
- Research routine CAN push to claude/research (the older "no push capability" note in the Project doc is outdated).
- ROC layer (composite_5d_chg, hyg_5d_pct): not present in code; re-test 2026-11-01 shows ~1.5-3x lift but poor lead time on COVID/2025 — see WEEKLY_RESEARCH_LOG.md.
- macro_history.csv last row 2026-08-17 (stale ~12 weeks); investigate collection. deep_history_backtest_log.csv ends 2026-08-21 — re-run deep_history_backtest.yml to extend it through the Nov-2026 event.
- Sandbox can't reach Yahoo/FRED/CFTC; ideas 1,3,4,5,7 need allowlist.
- Bottom/risk-on-turn detection untested.
