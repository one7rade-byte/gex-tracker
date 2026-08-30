# Weekly Research Log

## 2026-08-30 — Composite/HYG 5-day rate-of-change as an early-warning overlay

**VERDICT: PASS — ready for review**

### What was tested (idea backlog #8: "wire the ROC layer into regime_analyzer.py")

This repo had no prior `IDEA_BACKLOG.md`, `WEEKLY_RESEARCH_LOG.md`, or
`claude/gex-tracker-notes.md` — checked `git log --all --full-history` for
all three paths, nothing on either branch. So this run built and validated
the idea from scratch rather than assuming a prior result.

`deep_history_backtest_summary.json` (already in the repo, from
`deep_history_backtest.py`'s real Yahoo history replay, 1995-10-17 to
2026-08-21) already shows the LEVEL-based signal missing a meaningful share
of real crash days: during 2020 COVID only 33.3-41.7% of days in the crash
window were flagged defensive by `regime_signal`/`flow_regime`; during the
2022 bear only 44.7-53.8%. A level threshold only fires once
`composite_score` actually crosses into stress/crisis territory, which can
lag a fast unwind.

Tested whether the RATE OF CHANGE of the same inputs — `composite_5d_chg`
(composite_score minus its value 5 trading days back) and `hyg_5d_pct`
(HYG's 5-trading-day % change) — fires earlier, using data already on disk
(`deep_history_backtest_log.csv`, no new fetch — this sandbox's network
policy denies Yahoo/FRED/CFTC, see notes file). New script:
`roc_early_warning_backtest.py`.

### Method

- Derived `composite_5d_chg`/`hyg_5d_pct` for every day in the 7,762-day log
  (HYG data starts 2007-04-11, so the HYG half only covers 2007-present).
- For each candidate threshold, checked the REAL forward max drawdown in
  SPY over the next 15 trading days (from `spy_close` directly, not the
  point-estimate `return_Nd` columns, so a fast interim drop isn't averaged
  away).
- Compared trigger hit rate (forward drawdown ≤ -5% within 15 days) against
  the UNCONDITIONAL base rate over the same sample — the real test of
  whether this adds anything over "markets sometimes just drop."
- Re-ran everything on the 2016-present subsample (same discipline as
  `deep_history_backtest.py`'s `by_era`/`recency_windows` correction) to
  check the finding isn't a pre-2016 artifact.
- For the four real crash windows already used elsewhere in this repo
  (2008 GFC, 2020 COVID, 2022 BEAR) plus a newly identified 2025 SELLOFF
  window (SPY -19.0% from 2025-02-19 to 2025-04-08, found by scanning
  `deep_history_backtest_log.csv` directly, not assumed), measured: how many
  trading days after the window's real start did each ROC threshold first
  fire, versus when the existing LEVEL-based `flow_regime` first flagged
  defensive in the same window.
- For the recovery side: searched the 40 trading days AFTER each window's
  actual SPY low for the first `composite_5d_chg >= +3` reversal, and
  recorded the forward 20-day SPY return from that trigger date.

### Results — false-positive / base-rate check (the real test)

| metric, threshold | n days | trigger rate | hit rate (≤-5% dd/15d) | base rate | lift |
|---|---|---|---|---|---|
| composite_5d_chg ≤ -3, full history (n=7,742) | | 3.4% | 25.1% | 14.2% | +10.9pp |
| composite_5d_chg ≤ -3, since 2016 (n=2,659) | | 5.5% | 23.8% | 11.4% | +12.4pp |
| hyg_5d_pct ≤ -1.5%, since 2007 (n=4,853) | | 8.5% | 29.0% | 13.8% | +15.2pp |
| hyg_5d_pct ≤ -1.5%, since 2016 (n=2,659) | | 5.4% | 29.2% | 11.4% | +17.8pp |

Both signals show a real, consistent lift over the unconditional base rate,
and — unlike the pooled-history trap `deep_history_backtest.py` already
flagged once — the lift does NOT decay in the 2016-present subsample; if
anything it's slightly larger recently. HYG is the stronger of the two
(higher lift, higher absolute hit rate). Honest caveat: hit rate is still
only ~24-35%, i.e. roughly 65-75% of individual triggers are NOT followed by
a real 15-day drawdown — this is a real edge, not a reliable per-trigger
call, consistent with using it as an early-warning flag rather than a
standalone trading signal.

### Results — named crash windows (lead time vs the existing level signal)

| episode | composite_5d_chg≤-3 first fires | hyg_5d_pct≤-1.5% first fires | existing level signal first fires defensive | ROC lead vs level |
|---|---|---|---|---|
| 2008 GFC (2008-09-01 start) | 2008-09-09 (+5 trading days) | 2008-09-15 (+9d) | 2008-09-15 (+9d) | composite: 4 days earlier |
| 2020 COVID (2020-02-19 start) | 2020-02-24 (+3d) | 2020-02-25 (+4d) | 2020-03-09 (+13d) | composite: 10 days earlier |
| 2022 BEAR (2022-01-03 start) | 2022-01-20 (+12d) | 2022-03-07 (+43d) | 2022-04-26 (+78d) | composite: 66 days earlier |
| 2025 SELLOFF (2025-02-19 start) | 2025-02-21 (+2d) | 2025-04-04 (+32d) | 2025-02-21 (+2d) | composite: tied, no improvement |

`composite_5d_chg` beats the existing level signal in 3 of 4 named crashes,
dramatically so in 2020 (10 trading days) and 2022 (66 trading days — the
level signal missed nearly the entire first leg of that bear market). It
ties in 2025, where the level signal itself was already fast. `hyg_5d_pct`
is a weaker lead-time indicator than composite_5d_chg in three of the four
episodes despite having the better base-rate lift overall — those are two
different properties (lead time in specific episodes vs. hit-rate lift
across the full sample) and shouldn't be conflated.

### Results — catching the bottom/recovery (both crash AND recovery benchmarks)

| episode | actual SPY bottom | composite_5d_chg≥+3 reversal fires | days after bottom | fwd 20d SPY return from trigger |
|---|---|---|---|---|
| 2008 GFC | 2009-03-09 | 2009-04-09 | +23d | +8.36% |
| 2020 COVID | 2020-03-23 | 2020-03-26 | +3d | +8.33% |
| 2022 BEAR | 2022-10-12 | 2022-11-04 | +17d | +6.18% |
| 2025 SELLOFF | 2025-04-08 | 2025-04-11 | +3d | +9.19% |

Consistently positive and sizable across all four real episodes, firing
within 3-23 trading days of the actual low every time. This is the
strongest, most consistent part of the finding — it directly hits the
mission's second benchmark ("flag the bottom/risk-on turn early enough to
participate in the recovery").

### Caveats

- Only 4 named crash episodes — the lead-time/reversal table is illustrative
  of real historical behavior, not a statistically large sample on its own;
  the base-rate table above (thousands of days) is the real statistical
  backbone of the PASS verdict.
- HYG data starts 2007-04-11, so `hyg_5d_pct` cannot be checked against the
  dot-com bust or any pre-2007 stress.
- `deep_history_backtest_log.csv` was built with `gex=None` (no free
  historical dealer-positioning data) — same structural caveat
  `deep_history_backtest.py` already documents. This test inherits it.
- `fwd_max_dd_15d` uses daily closes, not intraday lows — slightly
  understates real drawdown risk in fast single-day moves.
- The 2025 SELLOFF window was found by scanning for it in this run, not
  previously codified in `deep_history_backtest.py`'s `CRASH_WINDOWS` —
  worth adding there too for consistency in future re-runs.

### What was wired in

Added `hyg_5d_pct` and `composite_5d_chg` as persisted, live-accumulating
columns in `regime_log.csv` (`regime_analyzer.py`), computed the same way
`hyg_5d_change` already was. Added `composite_5d_chg ≤ -3` as a 7th
black-swan advisory warning condition (text-only, same as the existing 6 —
does not change `get_regime_signal()`'s BUY/SELL logic or any position
sizing). Not merged directly — opened as a PR for review per the project's
standing instructions on passing findings. New script:
`roc_early_warning_backtest.py`, output `roc_early_warning_summary.json`.

### New backlog ideas added (see IDEA_BACKLOG.md for full text)

- #8: does requiring composite_5d_chg AND hyg_5d_pct to both fire same-day
  raise the hit rate above either alone? Directly testable locally already.
- #9: re-validate against regime_log.csv's own live history (not just the
  historical replay) once it has 6-12 months of real days with gex not None.
- #10: HYG/LQD spread as a credit-specific stress detector, netting out
  generic rate moves that a HYG-only ROC can't distinguish from real spread
  widening.
