# GEX Tracker notes

(Recreated 2026-10-04: the original notes file was not present in the repo. Prior context —
ROC validation of 2026-08-25, by_era/recency_windows correction of 2026-08-21 — survives only
in deep_history_backtest_summary.json; the ROC script itself is missing.)

## Known open items
- ROC layer (composite_5d_chg, hyg_5d_pct): 2026-10-04 offline re-test is inconclusive (see
  WEEKLY_RESEARCH_LOG.md). Not wired into regime_analyzer.py. Original 2026-08-25 validation
  artifacts need to be located/restored.
- Research sandbox cannot reach cftc.gov, fred.stlouisfed.org, query1.finance.yahoo.com —
  allowlist them to unblock backlog items 1-7.
- Backlog: IDEA_BACKLOG.md. Log: WEEKLY_RESEARCH_LOG.md.
