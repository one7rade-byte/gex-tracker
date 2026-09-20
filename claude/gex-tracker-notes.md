# GEX Tracker — Project Notes

Living reference for the weekly research cycle. Keep this current: update "Known open
items" every run, and correct anything here that this run's data contradicts.

## Bootstrap note (2026-09-06, escalated 2026-09-13, escalated further 2026-09-20 — READ THIS FIRST)

This file, `IDEA_BACKLOG.md`, and `WEEKLY_RESEARCH_LOG.md` were NOT present on `main` —
checked directly, they don't exist there, again, for the FOURTH consecutive run. What
actually happened: two prior weekly runs (2026-08-30) independently created these files
on two different branches (`claude/beautiful-goodall-d1odxv` and
`claude/beautiful-goodall-92fsty`), opened as PRs #1 and #2. A third run (2026-09-06,
`claude/beautiful-goodall-a7ueon`) found both still unmerged, consolidated the better of
the two into a single branch, and opened PR #3. A fourth run (2026-09-13,
`claude/beautiful-goodall-07xlj5`) found all three still unmerged and opened PR #4. **As
of this run (2026-09-20, `claude/beautiful-goodall-bfwja8` / PR #5, confirmed directly
via the GitHub API — none of the four have been merged or closed), PRs #1 through #4 are
ALL still open and unreviewed.** PR #1 is now 21 days old. The validated
`composite_5d_chg`/`hyg_5d_pct` ROC early-warning wiring into `regime_analyzer.py` — real,
tested, PASS-graded code since 2026-08-30 — has now been sitting unreviewed for three full
weeks without going live on `main`. This run again reapplies that same diff cleanly onto
current `main` and carries the work forward as PR #5.

**This is now a THREE-run-running process failure** (2 stale PRs → 3 → 4, and now this
run would make it 5 if unreviewed), escalated directly to the user via notification again
this run. **Once PR #5 is reviewed/merged, PRs #1 through #4 should all be closed as
superseded** — they are now stale duplicates of each other and of PR #5.

**Process gap, still not fixed after being flagged three runs running:** this scheduled
routine has no way to discover in-flight research PRs before starting, and does not get
told to check for or close superseded ones after opening a new PR. Until that's fixed,
treat "no notes file on main" as a signal to check open PRs / other `claude/*` branches
before assuming this is truly the first run — and expect the number of stale PRs to keep
growing by one every week until a human actually reviews and merges one. **Recommendation
to the user, stated plainly since three prior escalations in this file went unactioned:**
either merge PR #5 (or any one of #1-#4, they're functionally identical) so the ROC
signal actually goes live, or explicitly tell a future run to stop reapplying this diff.
Continuing to let this accumulate costs real review surface area for no benefit — every
week adds one more stale duplicate PR to sort through.

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
unmerged PRs the whole time (see Bootstrap note) — as of this run (2026-09-20) it is
STILL not live on `main`, three weeks later, only present in this run's own PR #5. Real numbers from
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
is the slow signal in those two episodes (credit lagging equity/vol stress badly). A
third design, **VIX/SKEW same-day confirmation** (2026-09-20), was also rejected: VIX
confirmation looked perfect on the surface (zero crash-window lag in all four episodes)
but turned out to be an artifact — `vix_5d_pct` correlates -0.73 with `composite_5d_chg`
because VIX is a direct input to `composite_score`'s own `vol_score`, so it isn't an
independent confirming signal (90% trigger overlap with composite alone at the loosest
threshold tested). SKEW confirmation is independent but has no standalone edge (negative
hit-rate lift alone) and fails to confirm in 3 of 4 crash windows. See
`WEEKLY_RESEARCH_LOG.md` 2026-09-06, 2026-09-13, and 2026-09-20 entries. No confirmation
design has yet survived testing; the single-signal columns remain as originally shipped.

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
the four (17.1% vs 68.6% of days flagged defensive) — root-caused 2026-09-20: HYG never
traded below $74 in the entire 35-day episode (0.0% of days, vs 15-59% in the other three
crashes) and `composite_score` only hit ≤-3 on 8.6% of days (vs 29-75% elsewhere), so
`get_regime_signal`'s DEFENSIVE gate (`composite<=-3 OR hyg<74`) barely ever fires for a
fast, narrow, policy-driven equity/vol shock that spares credit markets. A real,
quantified blind spot, not yet fixed — candidate gate in `IDEA_BACKLOG.md` item 11.

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
blocks `fred.stlouisfed.org`, `www.cftc.gov`, `query1.finance.yahoo.com`, and (checked
as an alternate free source this run) `stooq.com` directly (confirmed 2026-08-30,
re-confirmed 2026-09-06, 2026-09-13, and 2026-09-20 — all still return connect_rejected/
403 from the egress proxy) — a `curl`/`requests` fetch to any of these will fail. If an
idea needs one of these, it can only be tested if a future run finds a reachable
substitute, or if the daily GitHub Actions runners (which already fetch VIX, HYG, DXY,
gold, etc. successfully) are extended to also pull it into a new CSV column during their
normal daily run — the research sandbox itself does not have unrestricted internet.

## Known open items

- **Five stale unmerged research PRs risk (#1 `d1odxv`, #2 `92fsty`, #3 `a7ueon`, #4
  `07xlj5`) are open against `main`, none reviewed, oldest is 21 days old** — this run's
  PR #5 supersedes all four; they should be closed once #5 is reviewed/merged. Escalated
  directly to the user again this run (2026-09-20) — see Bootstrap note. Three runs
  running now (2 stale PRs → 3 → 4 → this run's #5 makes it 5 if also unreviewed). The
  validated ROC signal has been ready and unmerged for three weeks.
- Candidate fix for the `regime_signal` 2025 blind spot (narrow `composite<0 AND
  vix_5d_pct>=threshold` DEFENSIVE override) — root cause diagnosed 2026-09-20, not yet
  tested for false-positive impact. `IDEA_BACKLOG.md` item 11, now the top item.
- A "composite-without-vol_score" 5-day-change confirming signal for `composite_5d_chg`
  — new idea this run (2026-09-20), motivated by vix_5d_pct's rejection for lack of
  independence. `IDEA_BACKLOG.md` item 12.
- Does `composite_5d_chg` flicker on/off for weeks before a real move, or fire once
  cleanly? Still not tested — only first-fire date per crash window has been checked
  across four runs now (2026-08-30, 2026-09-06, 2026-09-13, 2026-09-20 all skipped this).
  See `IDEA_BACKLOG.md` item 10.
- Items 1-7 of the original seed backlog (COT, breadth, net liquidity, 2s10s, VIX3M,
  yen carry, gold drivers), plus item 8 (HYG/LQD spread), remain blocked on network
  access — re-confirmed blocked 2026-09-20 (fred.stlouisfed.org, www.cftc.gov,
  query1.finance.yahoo.com, and stooq.com as an alternate source all still return
  connect_rejected/403 from the egress proxy), no change since 2026-08-30.
- All three tested confirmation designs for `composite_5d_chg` (HYG same-day, HYG
  sequential, VIX/SKEW same-day) are now rejected — see the ROC early-warning section
  above. No confirmation design has yet improved on the single-signal columns as shipped.
