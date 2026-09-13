# GEX Tracker — Project Notes

Living reference for the weekly research cycle. Keep this current: update "Known open
items" every run, and correct anything here that this run's data contradicts.

## Bootstrap note (2026-09-06, escalated 2026-09-13 — READ THIS FIRST)

This file, `IDEA_BACKLOG.md`, and `WEEKLY_RESEARCH_LOG.md` were NOT present on `main` —
checked directly, they don't exist there, again, for the THIRD consecutive run. What
actually happened: two prior weekly runs (2026-08-30) independently created these files
on two different branches (`claude/beautiful-goodall-d1odxv` and
`claude/beautiful-goodall-92fsty`), opened as PRs #1 and #2. A third run (2026-09-06,
`claude/beautiful-goodall-a7ueon`) found both still unmerged, consolidated the better of
the two into a single branch, and opened PR #3. **As of this run (2026-09-13,
`claude/beautiful-goodall-07xlj5` / PR #4), all three of PRs #1, #2, AND #3 are still
open and unmerged.** None has been reviewed. The validated `composite_5d_chg`/
`hyg_5d_pct` ROC early-warning wiring into `regime_analyzer.py` — real, tested, working
code — has now been sitting unreviewed for 14 days (PR #1/#2) to 7 days (PR #3) without
going live on `main`. This run again reapplies that same diff cleanly onto current
`main` (still applies with zero conflicts) and carries the work forward as PR #4.

**This is now a two-run-running process failure, not a one-off**, and it was flagged to
the user directly via notification this run rather than just left in this file for a
fifth run to rediscover silently. **Once PR #4 is reviewed/merged, PRs #1, #2, and #3
should all be closed as superseded** — they are now stale duplicates of each other and
of PR #4.

**Process gap, still not fixed:** this scheduled routine has no way to discover in-flight
research PRs before starting, and does not get told to check for or close superseded
ones after opening a new PR. Until that's fixed, treat "no notes file on main" as a
signal to check open PRs / other `claude/*` branches before assuming this is truly the
first run — and expect the number of stale PRs to keep growing by one every week until
a human actually reviews and merges one.

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
DXY rising while composite still positive, HYG < $76, and **composite_score dropping
<= -3 over 5 trading days** (coded 2026-08-30, still only on `main` via this run's PR #4
— see Bootstrap note) — see "ROC early-warning" below. Writes `regime_log.csv`.

As of 2026-09-13, `regime_log.csv` has **114 rows, starting 2026-03-30** — a little over 5.5
months of live history. It has NOT lived through a real crash yet. Anything about its
real-world hit rate is unverifiable until it does; don't overstate its track record.

**ROC early-warning layer (`composite_5d_chg`, `hyg_5d_pct`)** — validated 2026-08-30
against `deep_history_backtest_log.csv` (1995-2026). Coded since 2026-08-30 but stuck in
unmerged PRs the whole time (see Bootstrap note) — as of this run (2026-09-13) it is
STILL not live on `main`, only present in this run's own PR #4. Real numbers from
`roc_early_warning_summary.json`: `composite_5d_chg <= -3` fired 10 trading days earlier
than the level-based `flow_regime` signal in the 2020 COVID crash and 66 days earlier in
the 2022 bear, with a hit-rate lift of +10.9 pts over base rate (25.1% vs 14.2%)
full-history and +12.4 pts since 2016 — holds up in the recent-era check, not just a
pooled artifact. Also flagged each recovery within 3-23 days of the actual bottom.

Two follow-up confirmation designs have now both been tested and rejected as
early-warning upgrades, for the same underlying reason: **same-day AND-confirmation**
(2026-09-06, composite_5d_chg AND hyg_5d_pct both fire the same day) raises hit rate
(+20.4 pts full-history) but loses 25-56 trading days of lead time in the 2022
bear/2025 selloff specifically. **Sequential confirmation** (2026-09-13, hyg allowed up
to N=3/5/10/20 trading days after composite to confirm) gets essentially the same
hit-rate lift (32-34%) but the crash-window lag barely improves with a wider window
(still +30 to +56 days in 2022/2025) — because HYG itself, not the same-day requirement,
is the slow signal in those two episodes (credit lagging equity/vol stress badly). See
`WEEKLY_RESEARCH_LOG.md` 2026-09-06 and 2026-09-13 entries. Neither confirmation design
is wired in; the single-signal columns remain as originally shipped.

**`deep_history_backtest.py`** — the only source of pre-2021 history. Reconstructs
`composite_score`/`flow_regime` back to 1995-10-17 (7,762 trading days) from spy_close,
vix, hyg, dxy, gold, copper, eem, skew (gex is NOT included — no free historical
dealer-positioning data exists, so `regime_signal` here never shows STRONG_BUY/BUY_WATCH;
use `flow_regime` instead when working with this file). Per-field data availability
varies: hyg valid from 2007-04-11 (ETF inception), gold from 2004-11-18, eem from
2003-04-14, copper from 2011-11-15, dxy/vix/skew/spy_close valid the full range. Latest
run's log data currently ends 2026-08-21 — re-run the backtest workflow (needs live
Yahoo fetch, not available from the research sandbox) to refresh before relying on it
for anything time-sensitive. `deep_history_backtest_summary.json` CAN be regenerated
from the existing log with no fetch (`build_summary(rows)` is a pure function of
already-derived rows) — used this run (2026-09-13) to add the 2025 crash window without
needing new data.

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
tariff selloff (2025-02-19 to 2025-04-08, SPY -19%) — as of this run (2026-09-13) all
four are codified directly in `deep_history_backtest.py`'s own `CRASH_WINDOWS`/
`crash_window_analysis`, not just re-derived ad hoc inside individual research scripts
(that cost real time across three separate runs before being fixed). One new fact from
adding 2025: it has the worst `regime_signal`-vs-`flow_regime` defensive-detection gap of
the four (17.1% vs 68.6% of days flagged defensive) — not yet explained, see backlog.

**`signal_tiers.py`** — adds a signed `conviction_score` (-10 to +10) and 5-tier
STRONG BUY → STRONG AVOID classification on top of `market_scanner.py`'s one-directional
`opportunity_score`, for long/cash accounts only (bottom tiers mean "don't go long,"
never "go short"). Explicitly documented as running on a short window of one rising-market
regime as of its own header comment — same caveat as regime_log.csv above.

**`track_signal_performance.py`** / `signal_performance_summary.json` — forward-return
tracking by `regime_signal` bucket. 109 unique signal days as of 2026-09-13; several
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
(confirmed 2026-08-30, re-confirmed 2026-09-06 and 2026-09-13 — all three still return
a connection failure from the egress proxy) — a `curl`/`requests` fetch to any of these will
fail. If an idea needs one of these, it can only be tested if a future run finds a
reachable substitute, or if the daily GitHub Actions runners (which already fetch VIX,
HYG, DXY, gold, etc. successfully) are extended to also pull it into a new CSV column
during their normal daily run — the research sandbox itself does not have unrestricted
internet.

## Known open items

- **Three stale unmerged research PRs (#1 `d1odxv`, #2 `92fsty`, #3 `a7ueon`) are open
  against `main`, none reviewed, oldest is 14 days old** — this run's PR #4 supersedes
  all three; they should be closed once #4 is reviewed/merged. Flagged directly to the
  user this run (2026-09-13), not just logged here — see Bootstrap note. This has now
  gotten worse for two runs in a row (2 stale PRs → 3 stale PRs); if PR #4 also goes
  unreviewed, expect a 5th run to find 4.
- Confirmation-signal tests (composite_5d_chg AND hyg_5d_pct, both same-day 2026-09-06
  and sequential-within-N-days 2026-09-13) — both tested and rejected as early-warning
  upgrades; real hit-rate lift in both, but bad lead time in the 2022/2025 crash windows
  specifically because HYG itself is the slow-confirming signal there, not an artifact
  of the same-day requirement. Not wired into `regime_analyzer.py`.
- 2025 tariff selloff crash window — done 2026-09-13, now codified directly in
  `deep_history_backtest.py`'s `CRASH_WINDOWS`/`crash_window_analysis`.
- VIX/SKEW-based confirmation (instead of HYG) for `composite_5d_chg` — new idea this run
  (2026-09-13), not yet tested. See `IDEA_BACKLOG.md` item 11.
- Why `regime_signal` underperforms `flow_regime` so much more in the 2025 selloff
  (17.1% vs 68.6% defensive-flagged days) than in 2008/2020/2022 — new idea this run,
  not yet tested. See `IDEA_BACKLOG.md` item 12.
- Does `composite_5d_chg` flicker on/off for weeks before a real move, or fire once
  cleanly? Not yet tested — only first-fire date per crash window has been checked
  (2026-08-30, 2026-09-06, 2026-09-13 runs all skipped this). See `IDEA_BACKLOG.md`
  item 10.
- Items 1-7 of the original seed backlog (COT, breadth, net liquidity, 2s10s, VIX3M,
  yen carry, gold drivers) remain blocked on network access — re-confirmed blocked
  2026-09-13 (fred.stlouisfed.org, www.cftc.gov, query1.finance.yahoo.com all still
  return connection failures from the egress proxy), no change since 2026-08-30.
- HYG/LQD spread as a credit-specific stress detector (nets out generic rate moves) —
  not yet tested, needs LQD history; check reachability before attempting.
  `IDEA_BACKLOG.md` item 8, now the top untested item for the next run.
