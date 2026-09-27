# GEX Tracker — research notes

Living context file for the weekly research cycle. Read this first each run.
Update "Known open items" at the end of every run.

## 2026-09-27 — first run of this file

This file, `IDEA_BACKLOG.md`, and `WEEKLY_RESEARCH_LOG.md` did not exist
anywhere in this repo's git history before this run (checked with
`git log --all` across all branches). The weekly-research-cycle task prompt
references a "validated ROC early-warning layer (composite_5d_chg,
hyg_5d_pct — validated 2026-08-25)" as if it were already built and wired
in. It is not: there is no `composite_5d_chg` anywhere in the codebase, and
`hyg_5d_change` exists only as a single-day-diff column in `regime_log.csv`
(live history starting 2026-03-30, n too small to validate anything). So
either that validation happened in a past session whose notes were never
committed, or the reference is aspirational. Treating this run as cycle 1
and documenting the real, current state below rather than assuming prior
work that isn't in the repo.

## Signal framework, as it actually exists in the code today

- `gex_tracker.py` — daily SPY/QQQ dealer-gamma pull (net GEX, zero gamma,
  call/put walls, max pain) plus VIX term structure, SKEW, RSI, PCR. Writes
  `gex_log.csv`. Sends Telegram summary via `telegram_notify.py`.
- `regime_analyzer.py` — reads `macro_history.csv` (own log, 2021-08-17
  onward, ~1290 rows as of this run — NOT a 30-year series) + `gex_log.csv`,
  computes a composite regime score in **[-8, +8]** from five sub-scores:
  `credit_score` (HYG, 0-3), `vol_score` (VIX, 0-3), `flow_score`
  (DXY/gold, 0-2), `growth_score` (copper/EEM, 0-2), `skew_score` (SKEW
  index, -1 to +1). Combined with GEX sign/magnitude into `regime_signal`
  (STRONG_BUY/BUY_WATCH/STRONG_HOLD/HOLD/CAUTION/DEFENSIVE/CRISIS) and a
  `black_swan_watch` flag (3+ simultaneous warning signals). Writes
  `regime_log.csv`, live history starts 2026-03-30.
- `deep_history_backtest.py` — the actual validation tool. Imports
  `regime_analyzer`'s real scoring functions (not reimplemented) and
  replays them over Yahoo Finance history back to **1995-10-17**, for
  SPY/VIX/HYG/DXY/gold/copper/EEM/SKEW, producing
  `deep_history_backtest_log.csv` (7,762 rows, 1995-10-17 to 2026-08-21)
  with `composite_score`, `flow_regime`, `regime_signal`, and forward
  5/10/20-day returns already computed per row. **This is the only
  dataset in the repo with real 1995-2026 daily coverage** — it is the
  right base for any backtest of composite-score-derived features, and it
  requires a live Yahoo Finance fetch to regenerate (network-gated in this
  sandbox — see below).
- `mag7_tracker.py` / `mag7_signals.py`, `market_scanner.py`,
  `sector_rotation.py`, `signal_tiers.py`, `track_signal_performance.py` —
  downstream consumers / tier framework and live signal-accuracy tracking.
  `signal_performance_summary.json` currently has very small per-bucket n
  (STRONG_BUY n=13 at 5d) since the regime-signal system itself only
  started 2026-03-30 — treat as exploratory, not proof, until n grows.
- `deep_history_backtest_summary.json` already flagged one real pooling
  trap (worth remembering as a template for how to phrase caveats): the
  "stress" composite bucket looks bearish pooled across all 30 years but
  that's a pre-2010 artifact — every era since 2010 shows the opposite
  sign. Always cross-check `by_era`/recency windows before trusting a
  pooled full-history number.

## Network reachability in this sandbox (checked 2026-09-27)

Both are policy-denied (403 at the egress proxy CONNECT), not flaky:
- `query1.finance.yahoo.com` — blocked. Cannot regenerate/extend
  `deep_history_backtest_log.csv` or pull any new ticker (e.g. LQD) from
  this environment. Any idea needing a fresh Yahoo pull is blocked until
  run from an environment with that host allowlisted.
- `api.telegram.org` — blocked. Cannot send the weekly summary from this
  sandbox even though `telegram_notify.py` exists and works from the
  scheduled GitHub Actions runners (those clearly have a different
  network policy). Skipped silently per instructions.
- FRED/CFTC (COT data, net liquidity) — not tested yet since this run's
  test didn't need them; check before attempting idea #1 or #3 in
  `IDEA_BACKLOG.md`.

## This run's finding (2026-09-27) — see WEEKLY_RESEARCH_LOG.md for full numbers

Tested the composite-score ROC layer (`composite_5d_chg` = composite_score
change over 5 trading days, and `hyg_5d_pct` = HYG % change over 5 trading
days) as a standalone stress/risk-on early-warning trigger, using the real
1995-2026 `deep_history_backtest_log.csv`.

**Verdict: real lead time, poor standalone precision — not wired in.**
`composite_5d_chg <= -3` fired with positive lead time ahead of the -10%
drawdown point in all 4 benchmark episodes tested (2008 GFC: 43 trading
days lead, 2020 COVID: 3 days, 2022 bear: 22 days, 2025 tariff selloff: 14
days) — genuine 100% recall on the named crashes. But across the full
2007-2026 sample it fires 137 times, and only 10.9% of those firings are
followed by a real ≥5% 20-day drawdown; the average 20-day forward return
after a firing is **positive** (+1.56%). Tried three precision filters
(HYG confirmation, low-composite-level filter, VIX>20 filter, 3-day
persistence) — none pushed hit rate materially above ~16%. So this is a
high-recall/low-precision "necessary but not sufficient" flag: useful as
one input, not usable alone as a de-risk trigger. Full numbers, thresholds
tested, and the risk-on-turn side (which fared somewhat better, 35.7%
precision, and caught the post-bottom turn within 5-15 trading days after
the 2020/2022/2025 lows) are in `WEEKLY_RESEARCH_LOG.md`.

Not wiring `composite_5d_chg` into `regime_analyzer.py` as a signal this
run — it failed the "known-risk" precision bar from the mission. It could
still be logged as a diagnostic column (not a signal) in a future pass if
a confirming filter is found that lifts precision meaningfully.

## Known open items

- IDEA_BACKLOG.md items 1-7 (seed list) are still untested: COT
  positioning, market breadth, net liquidity (needs FRED — untested
  reachability), yield curve 2s10s, VIX term structure backwardation, yen
  carry trade stress, gold-specific drivers (real yields / GDX-GLD ratio).
- Idea #3 (net liquidity, FRED) and idea #1 (COT, CFTC) both need a live
  fetch from hosts not yet confirmed reachable from this sandbox — check
  reachability before attempting, and say plainly if blocked rather than
  faking data.
- `composite_5d_chg` / `hyg_5d_pct` need a precision-improving filter
  before they're worth wiring in anywhere — see new backlog idea added
  this run (credit-spread / persistence-combo variants).
- `deep_history_backtest_log.csv` is the one full-history dataset in this
  repo; extending it (new tickers, e.g. LQD for a credit-spread idea)
  requires re-running `deep_history_backtest.py`, which needs Yahoo
  Finance reachability this sandbox doesn't have. Flag for a run from an
  environment where that host is allowlisted.
- No PR opened this run — the one finding tested didn't clear the bar for
  wiring into the live signal set.
