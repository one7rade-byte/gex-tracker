# GEX Tracker — Project Notes

Living reference for the weekly research cycle. Keep this current: update "Known open
items" every run, and correct anything here that this run's data contradicts.

## What this project is

Daily automated tracking of SPY dealer gamma exposure (GEX), a macro regime scorer, a
Mag7 signal tracker, a broad market scanner, sector rotation, and a signal-tiering layer
on top — all driven by GitHub Actions workflows (`.github/workflows/*.yml`) that run
scripts and commit CSV logs. No live user is watching most of these runs; the CSVs are
the ground truth.

Core daily pipeline (in run order): `gex_tracker.py` → `regime_analyzer.py` →
`mag7_tracker.py` / `mag7_signals.py` → `market_scanner.py` → `sector_rotation.py` →
`track_signal_performance.py`. `deep_history_backtest.py` runs separately (its own
workflow) and is the only piece with pre-2021 history.

## Current signal framework

**`regime_analyzer.py`** — daily macro regime score, `-8` to `+8`, from five sub-scores:
credit (HYG level), volatility (VIX + VIX9D ratio + term structure), flow (DXY/gold/TLT),
growth (copper/EEM), and SKEW (contrarian). Outputs `flow_regime`, `regime_signal`
(STRONG_BUY/BUY_WATCH/STRONG_HOLD/HOLD/CAUTION/DEFENSIVE/CRISIS), and a `black_swan_watch`
flag that fires when 3+ of 6 independent stress signals (elevated SKEW+low VIX, HYG 5d
drop, VIX backwardation, composite dropping fast over 10d, DXY rising while composite
still positive, HYG < $76) are true simultaneously. Writes `regime_log.csv`.

As of 2026-08-30, `regime_log.csv` only has **105 rows, starting 2026-03-30** — under 5
months of live history. It has NOT lived through a real crash yet. Anything about its
real-world hit rate is unverifiable until it does; don't overstate its track record.

**`deep_history_backtest.py`** — the only source of pre-2021 history. Reconstructs
`composite_score`/`flow_regime` back to 1995-10-17 (7,762 trading days) from spy_close,
vix, hyg, dxy, gold, copper, eem, skew (gex is NOT included — no free historical
dealer-positioning data exists, so `regime_signal` here never shows STRONG_BUY/BUY_WATCH;
use `flow_regime` instead when working with this file). Per-field data availability
varies: hyg valid from 2007-04-11 (ETF inception), gold from 2004-11-18, eem from
2003-04-14, copper from 2011-11-15, dxy/vix/skew/spy_close valid the full range.

Documented finding (still holds, re-confirmed 2026-08-21): a pooled full-history read of
`by_composite_bucket` makes the "stress" bucket (-1 to -3) look bearish (negative forward
returns), but that's almost entirely a pre-2010 artifact — every era since 2010 shows the
OPPOSITE (positive forward returns) for the same bucket. **Always cross-check a pooled
finding against `by_era` and `recency_windows` in `deep_history_backtest_summary.json`
before treating it as current.** This correction is why every new backtest in this
project must do the same by-era check — see the Method section of the weekly research
prompt.

Known real-crash episodes in this dataset (`crash_window_analysis` in the summary json):
2008 GFC (2008-09-02 to 2009-03-09), 2020 COVID (2020-02-19 to 2020-03-23), 2022 bear
(2022-01-03 to 2022-10-13). The 2025 tariff selloff (SPY peak 2025-02-19 at 612.93,
trough 2025-04-08 at 496.48, -19%) is in the raw log but not yet added to that
crash-window table — worth adding next time `deep_history_backtest.py` is touched.

**`signal_tiers.py`** — adds a signed `conviction_score` (-10 to +10) and 5-tier
STRONG BUY → STRONG AVOID classification on top of `market_scanner.py`'s one-directional
`opportunity_score`, for long/cash accounts only (bottom tiers mean "don't go long,"
never "go short"). Explicitly documented as running on ~98 days of one rising-market
regime as of its own header comment — same caveat as regime_log.csv above.

**`track_signal_performance.py`** / `signal_performance_summary.json` — forward-return
tracking by `regime_signal` bucket. 99 unique signal days as of 2026-08-30; several
buckets (e.g. CAUTION, n=1) are far too small to trust — treat as exploratory per the
file's own note field.

## Data actually available for research (no live fetch needed)

These CSVs already hold real multi-year history and don't require network access:
`deep_history_backtest_log.csv` (1995-2026: spy_close, vix, hyg, dxy, gold, copper, eem,
skew, composite_score, flow_regime, regime_signal, return_5d/10d/20d), `macro_history.csv`
(2021-08-17 to present: adds tlt, xlre, yield10y), `regime_log.csv` (2026-03-30 to
present: full scoring breakdown incl. gex_b, spy_rsi), `mag7_log.csv`, `market_scan_log.csv`,
`sector_rotation_log.csv`, `signal_performance_log.csv`.

**Not in the repo yet, would need a live fetch:** CFTC COT data, FRED series (net
liquidity, 2y yield), individual-stock breadth (%>50MA/200MA, advance-decline), VIX3M,
USDJPY/Nikkei, GDX, TIPS breakeven yields. The research sandbox's network policy blocks
`fred.stlouisfed.org`, `www.cftc.gov`, and `query1.finance.yahoo.com` directly (confirmed
2026-08-30) — a `curl`/`requests` fetch to any of these will fail with a 403 from the
egress proxy. If an idea needs one of these, it can only be tested if a future run finds
a reachable substitute, or if the daily GitHub Actions runners (which already fetch VIX,
HYG, DXY, gold, etc. successfully) are extended to also pull it into a new CSV column
during their normal daily run — the research sandbox itself does not have unrestricted
internet.

## Known open items

- **`composite_5d_chg` early-warning column** — added to `regime_analyzer.py` /
  `regime_log.csv` 2026-08-30 (see `WEEKLY_RESEARCH_LOG.md` same date). Backtested
  against `deep_history_backtest_log.csv`: fires within 2-33 trading days of the actual
  market peak for all four known crashes (2008/2020/2022/2025), consistently earlier than
  the current production `composite_score` LEVEL threshold (which lagged by 3 weeks to
  10+ months on the same episodes). Hit-rate lift is modest (~1.6-1.9x over unconditional
  base rate, fires ~5% of days) — it is a WATCH-tier flag, not a standalone action signal.
  Revisit once it has accumulated real out-of-sample days in `regime_log.csv`.
- **No prior "validated ROC layer" exists.** A version of this research prompt referenced
  a `composite_5d_chg`/`hyg_5d_pct` early-warning layer as already "validated 2026-08-25"
  and asked this file to already contain that context. Neither this file, `IDEA_BACKLOG.md`,
  `WEEKLY_RESEARCH_LOG.md`, nor any commit/PR in this repo's history contained any of
  that — confirmed via `git log --all` across both branches and a fresh GitHub clone. This
  run built the equivalent research from scratch (see 2026-08-30 log entry) and created
  these three files for the first time. If that prior validation genuinely happened
  somewhere, it was never committed to this repo and should be treated as lost, not as
  settled fact, until re-derived.
- `regime_log.csv` (the live regime_analyzer output) is only 105 rows / ~5 months old and
  has not lived through a real drawdown yet — its own hit-rate claims are unverifiable
  until it does. Don't treat `signal_performance_summary.json`'s small-n buckets (several
  n<10) as settled.
- `deep_history_backtest_summary.json`'s `crash_window_analysis` doesn't yet include the
  2025 tariff selloff window (2025-02-19 to 2025-04-08) — only 2008/2020/2022. Worth
  adding next time that script is touched.
- COT positioning, market breadth, net liquidity (FRED), 2s10s yield curve, VIX3M term
  structure, yen carry (USDJPY/Nikkei), and gold-specific drivers (real yields, GDX/GLD)
  all remain untested — no reachable data source yet from inside the research sandbox.
  See "Data actually available" above.
