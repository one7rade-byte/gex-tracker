# GEX Tracker — Project Notes

Living reference for the weekly research cycle. Keep this current: update "Known open
items" every run, and correct anything here that this run's data contradicts.

## Bootstrap note (2026-09-06)

This file, `IDEA_BACKLOG.md`, and `WEEKLY_RESEARCH_LOG.md` were NOT present on `main` —
checked directly, they don't exist there. What actually happened: two prior weekly runs
(2026-08-30) independently created these files on two different branches
(`claude/beautiful-goodall-d1odxv` and `claude/beautiful-goodall-92fsty`), each unaware of
the other, and opened them as PRs #1 and #2. Both PRs are still **open and unmerged** as
of this run. Neither got reviewed/merged, so `main` never picked up any of it, and this
run's own "read the notes first" step found nothing until it checked those branches
directly.

Both prior runs did essentially the same research in parallel (validating
`composite_5d_chg` / `hyg_5d_pct` 5-day-ROC as an early-warning signal) and reached the
same conclusion. PR #2 (`92fsty`)'s implementation is the more complete one — it wires
BOTH `composite_5d_chg` and `hyg_5d_pct` into `regime_analyzer.py`'s black-swan detector
as a 7th independent signal, versus PR #1's simpler single-column addition. This run
brings PR #2's validated `regime_analyzer.py` change forward onto current `main` (it
applied cleanly, no conflicts) and reconstructs this notes/backlog/log trio from the
better parts of both stale branches, rather than losing the work. **The two open stale
PRs (#1, #2) should be closed once this run's PR is reviewed/merged** — they're now
superseded duplicates of each other and of this PR.

**Process gap worth fixing:** this scheduled routine has no way to discover in-flight
research PRs before starting, and evidently doesn't get told to check for or close
superseded ones after opening a new PR. Until that's fixed, treat "no notes file on
main" as a signal to check open PRs / other `claude/*` branches before assuming this is
truly the first run.

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
flag that fires when 3+ of now **7** independent stress signals are true simultaneously:
elevated SKEW+low VIX, HYG 5d drop, VIX backwardation, composite dropping fast over 10d,
DXY rising while composite still positive, HYG < $76, and (as of this run, 2026-09-06)
**composite_score dropping <= -3 over 5 trading days** — see "ROC early-warning" below.
Writes `regime_log.csv`.

As of 2026-09-06, `regime_log.csv` has **109 rows, starting 2026-03-30** — a little over 5
months of live history. It has NOT lived through a real crash yet. Anything about its
real-world hit rate is unverifiable until it does; don't overstate its track record.

**ROC early-warning layer (`composite_5d_chg`, `hyg_5d_pct`)** — validated 2026-08-30
against `deep_history_backtest_log.csv` (1995-2026), wired into `regime_analyzer.py` as
of this run (2026-09-06; the code existed since 2026-08-30 but was stuck in an unmerged
PR — see Bootstrap note). Real numbers from `roc_early_warning_summary.json`:
`composite_5d_chg <= -3` fired 10 trading days earlier than the level-based
`flow_regime` signal in the 2020 COVID crash and 66 days earlier in the 2022 bear, with a
hit-rate lift of +10.9 pts over base rate (25.1% vs 14.2%) full-history and +12.4 pts
since 2016 — holds up in the recent-era check, not just a pooled artifact. Also flagged
each recovery within 3-23 days of the actual bottom. Follow-up confirmation-signal test
(this run, 2026-09-06) found requiring composite AND hyg to both fire the same day raises
hit rate further (+20.4 pts full-history) but **loses most of the lead-time advantage in
the 2022 bear and 2025 selloff** (fires 25-56 trading days later than either signal
alone) — rejected as an early-warning upgrade; see `WEEKLY_RESEARCH_LOG.md` 2026-09-06.

**`deep_history_backtest.py`** — the only source of pre-2021 history. Reconstructs
`composite_score`/`flow_regime` back to 1995-10-17 (7,762 trading days) from spy_close,
vix, hyg, dxy, gold, copper, eem, skew (gex is NOT included — no free historical
dealer-positioning data exists, so `regime_signal` here never shows STRONG_BUY/BUY_WATCH;
use `flow_regime` instead when working with this file). Per-field data availability
varies: hyg valid from 2007-04-11 (ETF inception), gold from 2004-11-18, eem from
2003-04-14, copper from 2011-11-15, dxy/vix/skew/spy_close valid the full range. Latest
run's log data currently ends 2026-08-21 — re-run the backtest workflow to refresh before
relying on it for anything time-sensitive.

Documented finding (still holds, re-confirmed 2026-08-21): a pooled full-history read of
`by_composite_bucket` makes the "stress" bucket (-1 to -3) look bearish (negative forward
returns), but that's almost entirely a pre-2010 artifact — every era since 2010 shows the
OPPOSITE (positive forward returns) for the same bucket. **Always cross-check a pooled
finding against `by_era` and `recency_windows` in `deep_history_backtest_summary.json`
before treating it as current.** This correction is why every new backtest in this
project must do the same by-era check — see the Method section of the weekly research
prompt.

Known real-crash episodes in this dataset: 2008 GFC (2008-09-02 to 2009-03-09), 2020
COVID (2020-02-19 to 2020-03-23), 2022 bear (2022-01-03 to 2022-10-13), and the 2025
tariff selloff (2025-02-19 to 2025-04-08, SPY -19%) — all four are now used consistently
across the ROC and confirmation-signal backtests, though `crash_window_analysis` inside
`deep_history_backtest_summary.json` itself still only has the first three; worth adding
2025 there directly next time that file is touched, so future scripts don't have to
redefine the window by hand.

**`signal_tiers.py`** — adds a signed `conviction_score` (-10 to +10) and 5-tier
STRONG BUY → STRONG AVOID classification on top of `market_scanner.py`'s one-directional
`opportunity_score`, for long/cash accounts only (bottom tiers mean "don't go long,"
never "go short"). Explicitly documented as running on a short window of one rising-market
regime as of its own header comment — same caveat as regime_log.csv above.

**`track_signal_performance.py`** / `signal_performance_summary.json` — forward-return
tracking by `regime_signal` bucket. 104 unique signal days as of 2026-09-06; several
buckets are still far too small to trust — treat as exploratory per the file's own note
field.

## Data actually available for research (no live fetch needed)

These CSVs already hold real multi-year history and don't require network access:
`deep_history_backtest_log.csv` (1995-2026: spy_close, vix, hyg, dxy, gold, copper, eem,
skew, composite_score, flow_regime, regime_signal, return_5d/10d/20d), `macro_history.csv`
(2021-08-17 to present: adds tlt, xlre, yield10y), `regime_log.csv` (2026-03-30 to
present: full scoring breakdown incl. gex_b, spy_rsi), `mag7_log.csv`, `market_scan_log.csv`,
`sector_rotation_log.csv`, `signal_performance_log.csv`.

**Not in the repo yet, would need a live fetch:** CFTC COT data, FRED series (net
liquidity, 2y yield), individual-stock breadth (%>50MA/200MA, advance-decline), VIX3M,
USDJPY/Nikkei, GDX, TIPS breakeven yields, LQD. The research sandbox's network policy
blocks `fred.stlouisfed.org`, `www.cftc.gov`, and `query1.finance.yahoo.com` directly
(confirmed 2026-08-30, re-confirmed 2026-09-06 — all three still return a 403 CONNECT
tunnel failure from the egress proxy) — a `curl`/`requests` fetch to any of these will
fail. If an idea needs one of these, it can only be tested if a future run finds a
reachable substitute, or if the daily GitHub Actions runners (which already fetch VIX,
HYG, DXY, gold, etc. successfully) are extended to also pull it into a new CSV column
during their normal daily run — the research sandbox itself does not have unrestricted
internet.

## Known open items

- Two stale duplicate research PRs (#1 `d1odxv`, #2 `92fsty`) from 2026-08-30 are still
  open against `main` and should be closed once this run's PR lands — see Bootstrap note.
- Confirmation-signal test (composite_5d_chg AND hyg_5d_pct same day) — tested and
  rejected as an early-warning upgrade this run (2026-09-06); real hit-rate lift but bad
  lead time in the two fastest-moving crash windows. Not wired into `regime_analyzer.py`.
- 2025 tariff selloff still missing from `crash_window_analysis` inside
  `deep_history_backtest_summary.json` itself (only defined ad hoc inside each research
  script so far) — worth adding directly to `deep_history_backtest.py` next time it's
  touched.
- Does `composite_5d_chg` flicker on/off for weeks before a real move, or fire once
  cleanly? Not yet tested — only first-fire date per crash window has been checked.
- Items 1-7 of the original seed backlog (COT, breadth, net liquidity, 2s10s, VIX3M,
  yen carry, gold drivers) remain blocked on network access — re-confirmed blocked
  2026-09-06, no change from 2026-08-30.
- HYG/LQD spread as a credit-specific stress detector (nets out generic rate moves) —
  not yet tested, needs LQD history; check reachability before attempting.
