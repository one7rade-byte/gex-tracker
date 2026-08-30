# GEX Tracker — Research Notes

Living context file for the weekly research cycle. Read this first, then
`IDEA_BACKLOG.md` (next idea to test) and `WEEKLY_RESEARCH_LOG.md` (what's
already been tried and the verdict).

## Bootstrap note (2026-08-30)

This file, `IDEA_BACKLOG.md`, and `WEEKLY_RESEARCH_LOG.md` did not exist in
the repo before this run — checked `git log --all --full-history` for all
three paths across both branches, nothing. Whatever prior "ROC layer
validated 2026-08-25" context this routine's own instructions referenced
was not present anywhere in this repository's history. Rather than assume
it, this run re-derived and independently validated the same underlying
idea (composite_score / HYG rate-of-change as an early-warning signal) from
scratch, honestly, against real local data — see the 2026-08-30 entry in
`WEEKLY_RESEARCH_LOG.md`. Treat these three files as starting fresh from
this date; there is no earlier log to reconcile against.

## Current signal framework (as of 2026-08-30, from reading the actual code)

- **`gex_tracker.py`** — daily SPY GEX pull (spot, net GEX, zero gamma,
  call/put walls, RSI, VIX term structure, SKEW) → `gex_log.csv`.
- **`regime_analyzer.py`** — reads `macro_history.csv` + latest `gex_log.csv`
  row, computes a `composite_score` (-8 to +8) from five sub-scores (credit
  via HYG, volatility via VIX, flow via DXY/Gold/TLT, growth via
  Copper/EEM, skew), a `flow_regime` label, and a combined `regime_signal`
  (STRONG_BUY/BUY_WATCH/STRONG_HOLD/HOLD/CAUTION/DEFENSIVE/CRISIS) →
  `regime_log.csv`. Also runs `detect_black_swan()`, an advisory-only
  multi-signal watch (fires when 3+ of 7 warning conditions trip
  simultaneously) — text warnings, not a trading action.
- **`deep_history_backtest.py`** — one-time/occasional re-run script that
  fetches real Yahoo daily history (SPY back to the 1990s where free data
  allows) and replays `regime_analyzer.py`'s actual scoring functions
  (imported directly, not reimplemented) against it, with `gex=None` since
  no free historical dealer-positioning data exists. Output:
  `deep_history_backtest_log.csv` (7,762 trading days, 1995-10-17 to
  2026-08-21, columns: date/spy_close/vix/hyg/dxy/gold/copper/eem/skew/
  composite_score/flow_regime/regime_signal/return_5d/return_10d/return_20d)
  and `deep_history_backtest_summary.json` (by-composite-bucket,
  by-flow-regime, by-era, recency-window, and named-crash-window stats).
  Already documents a real, disciplined finding: pooling 30 years hides a
  regime change (the "stress" bucket looks bearish pooled but is bullish
  in every era since 2010) — always cross-check `by_era`/`recency_windows`.
- **`roc_early_warning_backtest.py`** (new, 2026-08-30) — derives
  `composite_5d_chg` and `hyg_5d_pct` from `deep_history_backtest_log.csv`
  (no new fetch) and tests them as earlier-firing companions to the
  level-based signals above. See the research log for results — validated
  PASS, now wired into `regime_analyzer.py` as live-accumulating columns
  (`hyg_5d_pct`, `composite_5d_chg` in `regime_log.csv`) and as a 7th
  black-swan warning condition, pending PR review.
- **`sector_rotation.py`, `mag7_signals.py`, `market_scanner.py`,
  `signal_tiers.py`, `track_signal_performance.py`** — daily trackers /
  tier framework / live performance logging for the rest of the signal
  suite. Not modified this run.

## Environment constraint (check every run)

This sandbox's outbound network policy denies everything except a small
allowlist (checked via `curl $HTTPS_PROXY/__agentproxy/status` — see
`/root/.ccr/README.md`). Confirmed 2026-08-30: `query1.finance.yahoo.com`,
`fred.stlouisfed.org`, and `www.cftc.gov` all come back `403` at the proxy
(policy denial, not a transient failure — three separate hosts, three
separate 403s in `recentRelayFailures`). This blocks any idea needing a
live fetch of COT/CFTC data, FRED series, fresh Yahoo tickers not already
in the repo, or breadth data. Re-check this at the start of every run —
if it ever opens up, items 1-7 in `IDEA_BACKLOG.md` become testable as
originally scoped.

## Known open items

- Ideas 1-7 in `IDEA_BACKLOG.md` (COT positioning, breadth, net liquidity,
  yield curve shape, VIX term structure history, yen carry, gold drivers)
  are all blocked on the network restriction above — none of the required
  series exist in any local CSV yet. Revisit once network access changes,
  or reformulate to use only data already checked into the repo.
- `composite_5d_chg` / `hyg_5d_pct` are now live-accumulating in
  `regime_log.csv` (added 2026-08-30) but only have ~105 days of real
  history so far (regime_analyzer.py started 2026-08-21) — too short to
  re-validate independently; the validation is entirely from the 2007-2026
  `deep_history_backtest_log.csv` replay. Worth spot-checking again once
  regime_log.csv itself has a few hundred more days.
- Natural next step once more data accumulates: test whether requiring
  composite_5d_chg AND hyg_5d_pct to both trigger (confirmation) cuts the
  false-positive rate meaningfully below either alone (~25-35% hit rate
  standalone, see log) — flagged in `IDEA_BACKLOG.md`.
- Gold-specific research (idea 7: real yields, GDX/GLD ratio) still needs
  a TIPS-breakeven series and GDX price history, neither present locally —
  blocked same as above until network access changes.
