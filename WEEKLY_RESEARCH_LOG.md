# Weekly Research Log

## 2026-08-30 — Composite/HYG 5-day rate-of-change as an early-warning overlay

**VERDICT: PASS — ready for review**

*(Backfilled into this log 2026-09-06 — see that entry's housekeeping note for why. The
work and numbers below are unchanged from when they were first produced on 2026-08-30;
they just never reached `main` until now.)*

### What was tested (idea backlog #8: "wire the ROC layer into regime_analyzer.py")

`deep_history_backtest_summary.json` (from `deep_history_backtest.py`'s real Yahoo
history replay, 1995-10-17 to 2026-08-21) already shows the LEVEL-based signal missing a
meaningful share of real crash days: during 2020 COVID only 33.3-41.7% of days in the
crash window were flagged defensive by `regime_signal`/`flow_regime`; during the 2022
bear only 44.7-53.8%. A level threshold only fires once `composite_score` actually
crosses into stress/crisis territory, which can lag a fast unwind.

Tested whether the RATE OF CHANGE of the same inputs — `composite_5d_chg`
(composite_score minus its value 5 trading days back) and `hyg_5d_pct` (HYG's
5-trading-day % change) — fires earlier, using data already on disk
(`deep_history_backtest_log.csv`, no new fetch needed — this sandbox's network policy
denies Yahoo/FRED/CFTC directly, see notes file). Script: `roc_early_warning_backtest.py`,
output `roc_early_warning_summary.json`.

### Method

- Derived `composite_5d_chg`/`hyg_5d_pct` for every day in the 7,762-day log (HYG data
  starts 2007-04-11, so the HYG half only covers 2007-present).
- For each candidate threshold, checked the REAL forward max drawdown in SPY over the
  next 15 trading days (from `spy_close` directly, not the point-estimate `return_Nd`
  columns, so a fast interim drop isn't averaged away).
- Compared trigger hit rate (forward drawdown ≤ -5% within 15 days) against the
  UNCONDITIONAL base rate over the same sample.
- Re-ran on the 2016-present subsample (same by-era discipline as
  `deep_history_backtest.py`) to check the finding isn't a pre-2016 artifact.
- For four real crash windows (2008 GFC, 2020 COVID, 2022 BEAR, and a newly identified
  2025 SELLOFF window — SPY -19.0% from 2025-02-19 to 2025-04-08, found by scanning the
  log directly), measured lead time vs. the existing LEVEL-based `flow_regime` signal.
- For the recovery side: searched the 40 trading days after each window's actual SPY low
  for the first `composite_5d_chg >= +3` reversal, and recorded forward 20-day SPY return.

### Results — false-positive / base-rate check (the real test)

| metric, threshold | n days | trigger rate | hit rate (≤-5% dd/15d) | base rate | lift |
|---|---|---|---|---|---|
| composite_5d_chg ≤ -3, full history (n=7,742) | | 3.4% | 25.1% | 14.2% | +10.9pp |
| composite_5d_chg ≤ -3, since 2016 (n=2,659) | | 5.5% | 23.8% | 11.4% | +12.4pp |
| hyg_5d_pct ≤ -1.5%, since 2007 (n=4,853) | | 8.5% | 29.0% | 13.8% | +15.2pp |
| hyg_5d_pct ≤ -1.5%, since 2016 (n=2,659) | | 5.4% | 29.2% | 11.4% | +17.8pp |

Both signals show a real, consistent lift over the unconditional base rate, and the lift
does NOT decay in the 2016-present subsample — if anything it's slightly larger recently.
HYG is the stronger of the two on pure hit-rate lift. Honest caveat: hit rate is still
only ~24-35%, i.e. roughly 65-75% of individual triggers are NOT followed by a real
15-day drawdown — a real edge, not a reliable per-trigger call.

### Results — named crash windows (lead time vs the existing level signal)

| episode | composite_5d_chg≤-3 first fires | hyg_5d_pct≤-1.5% first fires | existing level signal first fires defensive | ROC lead vs level |
|---|---|---|---|---|
| 2008 GFC (2008-09-01 start) | 2008-09-09 (+5d) | 2008-09-15 (+9d) | 2008-09-15 (+9d) | composite: 4 days earlier |
| 2020 COVID (2020-02-19 start) | 2020-02-24 (+3d) | 2020-02-25 (+4d) | 2020-03-09 (+13d) | composite: 10 days earlier |
| 2022 BEAR (2022-01-03 start) | 2022-01-20 (+12d) | 2022-03-07 (+43d) | 2022-04-26 (+78d) | composite: 66 days earlier |
| 2025 SELLOFF (2025-02-19 start) | 2025-02-21 (+2d) | 2025-04-04 (+32d) | 2025-02-21 (+2d) | composite: tied, no improvement |

`composite_5d_chg` beats the existing level signal in 3 of 4 named crashes, dramatically
so in 2020 (10 trading days) and 2022 (66 trading days — the level signal missed nearly
the entire first leg of that bear market). `hyg_5d_pct` is a weaker lead-time indicator
than composite_5d_chg in three of four episodes despite the better base-rate lift
overall — lead time in specific episodes and hit-rate lift across the full sample are two
different properties, not to be conflated.

### Results — catching the bottom/recovery

| episode | actual SPY bottom | composite_5d_chg≥+3 reversal fires | days after bottom | fwd 20d SPY return from trigger |
|---|---|---|---|---|
| 2008 GFC | 2009-03-09 | 2009-04-09 | +23d | +8.36% |
| 2020 COVID | 2020-03-23 | 2020-03-26 | +3d | +8.33% |
| 2022 BEAR | 2022-10-12 | 2022-11-04 | +17d | +6.18% |
| 2025 SELLOFF | 2025-04-08 | 2025-04-11 | +3d | +9.19% |

Consistently positive and sizable across all four real episodes, firing within 3-23
trading days of the actual low every time — the strongest, most consistent part of the
finding, and it directly hits the mission's second benchmark (flag the turn early enough
to participate in the recovery).

### Caveats

- Only 4 named crash episodes — the lead-time/reversal table is illustrative, not a
  statistically large sample on its own; the base-rate table (thousands of days) is the
  real statistical backbone of the PASS verdict.
- HYG data starts 2007-04-11, so `hyg_5d_pct` cannot be checked against the dot-com bust.
- `deep_history_backtest_log.csv` was built with `gex=None` — same structural caveat
  `deep_history_backtest.py` already documents.
- `fwd_max_dd_15d` uses daily closes, not intraday lows — slightly understates real
  drawdown risk in fast single-day moves.
- The 2025 SELLOFF window is defined ad hoc inside this research script, not yet
  codified in `deep_history_backtest.py`'s own `crash_window_analysis` table.

### What was wired in (landed on `main` 2026-09-06 — see that entry)

Added `hyg_5d_pct` and `composite_5d_chg` as persisted, live-accumulating columns in
`regime_log.csv` (`regime_analyzer.py`). Added `composite_5d_chg ≤ -3` as a 7th
black-swan advisory warning condition (text-only, same as the existing 6 — does not
change `get_regime_signal()`'s BUY/SELL logic or any position sizing).

---

## 2026-09-06 — Housekeeping: two duplicate unmerged PRs found, then confirmation-signal follow-up test

**Housekeeping first.** This run's first step (read `claude/gex-tracker-notes.md`) found
nothing on `main` — the file didn't exist there. Checking further: two prior runs, both
dated 2026-08-30, had independently built this exact notes/backlog/log infrastructure and
the ROC early-warning finding above on two separate branches (`claude/beautiful-goodall-
d1odxv` and `claude/beautiful-goodall-92fsty`), opened as PRs #1 and #2, and **both are
still open and unmerged** a week later. Neither run saw the other's work. This run brings
the more complete of the two `regime_analyzer.py` implementations (PR #2's — it wires
both `composite_5d_chg` and `hyg_5d_pct` into the black-swan detector, vs PR #1's single
column) forward onto current `main`, and reconstructs the notes/backlog/log trio from
both. **PRs #1 and #2 should be closed as superseded once this run's PR is reviewed.**
This is a process gap, not a data finding — flagged in `claude/gex-tracker-notes.md` →
Known open items.

### What was tested (idea backlog #8, `92fsty` numbering): confirmation-signal follow-up

Natural next question after the finding above: does requiring `composite_5d_chg <= -3`
**AND** `hyg_5d_pct <= -1.5%` to fire on the *same day* (rather than either alone) raise
the forward-drawdown hit rate meaningfully, or does it just filter the single signal down
without adding real information? Script: `confirmation_signal_backtest.py`, output
`confirmation_signal_summary.json`. Same data source, same 15-trading-day forward
max-drawdown / ≥5% hit definition as the 2026-08-30 test above, for direct comparability.

### Results — base rate (real test)

HYG era, full history (2007-04-18 to 2026-08-21, n=4,853 days with both metrics valid):

| signal | n triggered | trigger rate | hit rate | base rate | lift |
|---|---|---|---|---|---|
| composite_5d_chg ≤ -3 alone | 246 | 5.07% | 26.4% | 13.8% | +12.6pp |
| hyg_5d_pct ≤ -1.5% alone | 411 | 8.47% | 29.0% | 13.8% | +15.2pp |
| **both, same day (confirmed)** | **117** | **2.41%** | **34.2%** | 13.8% | **+20.4pp** |

Since 2016 (n=2,659): composite alone 23.8% hit rate (+12.4pp lift, n=147 triggers), HYG
alone 29.2% (+17.8pp, n=144), confirmed **36.7%** (+25.3pp, n=60). The lift from
confirmation is real and gets larger in the recent-era check, not smaller — same
direction as the underlying signals, not an artifact of the pooled sample.

### Results — crash-window lead time (where this fails)

| episode | composite alone fires | hyg alone fires | confirmed fires | confirmed lag vs composite alone | confirmed lag vs hyg alone |
|---|---|---|---|---|---|
| 2008 GFC | 2008-09-09 (+5d) | 2008-09-15 (+9d) | 2008-09-15 (+9d) | +4 days | +0 days |
| 2020 COVID | 2020-02-24 (+3d) | 2020-02-25 (+4d) | 2020-02-25 (+4d) | +1 day | +0 days |
| 2022 BEAR | 2022-01-20 (+12d) | 2022-03-07 (+43d) | 2022-04-11 (+68d) | **+56 days** | +25 days |
| 2025 SELLOFF | 2025-02-21 (+2d) | 2025-04-04 (+32d) | 2025-04-04 (+32d) | **+30 days** | +0 days |

In 2008 and 2020, confirmation costs almost nothing (0-4 trading days) because both
signals already agreed close together. In 2022 and 2025 — the two episodes where
`composite_5d_chg` alone gave the biggest lead-time edge over the existing level signal
last week (66 days and tied-fastest, respectively) — confirmation throws that edge away:
it doesn't fire until 56 days after composite-alone in 2022 (68 days into a bear that
eventually ran ~200 trading days — not immediately actionable, but no longer an early
warning either) and 30 days after composite-alone in 2025 (by which point HYG had
already caught up and the SPY trough was only 4 trading days away — the "warning" arrives
essentially at the bottom, not ahead of the drop).

### Verdict: tested and rejected as an early-warning upgrade

The hit-rate lift is real (not sampling noise — holds up and gets larger in the
2016-present subsample, n=60-117 triggers is small but not tiny), so confirmation is
a legitimately higher-precision signal in isolation. But it fails the mission's actual
bar — "would this have helped de-risk ahead of a real crash" — for exactly the two
episodes (2022, 2025) where speed mattered most and where the single-signal version's
lead time was the whole point of validating it last week. Requiring agreement between
two signals that "solve different problems" (per this project's existing framing) turns
out to mean they typically only agree once the move is already well underway. **Not
wired into `regime_analyzer.py`** — the existing single-signal `composite_5d_chg`/
`hyg_5d_pct` columns from the 2026-08-30 entry remain as shipped, unchanged.

### Caveats

- n_triggered for the confirmed signal (60-117) is meaningfully smaller than either
  single signal — the base-rate lift number is directionally trustworthy (same sign and
  magnitude in both the full-history and 2016+ cuts) but shouldn't be treated as
  precisely estimated.
- This only tests the AND-of-thresholds confirmation design. A different combination
  (e.g., either signal fires, then the other confirms within N days rather than the same
  day) might preserve more lead time while still filtering noise — not tested this run;
  candidate for a future pass if there's ever a reason to revisit this family of signal.
- Same structural caveats as the 2026-08-30 entry apply (gex=None in deep history,
  daily-close-based drawdown, HYG-era-only for the hyg half).

### New ideas added to `IDEA_BACKLOG.md` this run

- **Sequential (not same-day) confirmation** — does requiring hyg_5d_pct to confirm
  within N trading days AFTER composite_5d_chg fires (rather than the same day) preserve
  more of composite's lead-time edge while still cutting false positives? Directly
  suggested by this run's finding that same-day AND-confirmation destroys lead time in
  exactly the episodes where it matters most.
- **HYG/LQD spread ROC** — carried forward from `92fsty`'s prior backlog (its item #10);
  still untested, still the most promising "no local data yet" credit-market gap now that
  the HYG-alone version is fully validated and (mostly) shipped.
- **Codify the two open stale PRs' resolution** — after this run's PR is reviewed, PRs #1
  and #2 need to be explicitly closed as superseded; otherwise a future run may find three
  divergent unmerged research branches instead of two.
