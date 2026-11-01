# Weekly Research Log

## 2026-11-01 — Idea #8 (ROC early-warning layer): independent re-test on deep-history data

**VERDICT: inconclusive — NOT ready for review; wiring into regime_analyzer.py not done.**

**Setup problems (stated plainly):**
- `claude/gex-tracker-notes.md` does not exist on this branch or on main, so the 2026-08-25 ROC validation record and any "already wired" status could not be read. `grep` finds no `composite_5d_chg` / `hyg_5d_pct` anywhere in the repo, so the layer is not wired into `regime_analyzer.py` (it only has `hyg_5d_change`).
- Sandbox egress allowlist blocks Yahoo, FRED and cftc.gov (HTTP 403 from proxy). Ideas 1, 3, 4, 5 (VIX3M), 7 cannot be tested here. Not faked.
- `macro_history.csv` ends 2026-08-17 and `deep_history_backtest_log.csv` ends 2026-08-21, so there is nothing newer than ~10 weeks old to evaluate.

**What was tested:** definitions reconstructed from the names: `composite_5d_chg` = 5-day change in composite_score; `hyg_5d_pct` = 5-day % change in HYG. Event = SPY falls >=8% (close to the min of the next 20 trading days). Source: `deep_history_backtest_log.csv`, 7762 days, 1995-10-17 to 2026-08-21; HYG exists only from 2007-04-11. Fire counts are days; clusters = fires separated by >30 days.

| Era | Trigger | Days fired | Clusters | P(event \| fire) | Base rate |
|---|---|---|---|---|---|
| full | composite_5d_chg <= -3 | 265 (3.4%) | 79 | 15.8% | 8.0% |
| full | hyg_5d_pct <= -2 | 247 (5.1%) | 37 | 24.7% | 8.2% |
| 2010+ | composite_5d_chg <= -3 | 195 (4.7%) | 57 | 12.3% | 6.2% |
| 2010+ | hyg_5d_pct <= -2 | 151 (3.6%) | 27 | 15.2% | 6.2% |
| 2020+ | composite_5d_chg <= -3 | 103 (6.2%) | 28 | 18.4% | 8.1% |
| 2020+ | hyg_5d_pct <= -2 | 64 (3.8%) | 8 | 29.7% | 8.1% |
| 2020+ | both (c5<=-3 & h5<=-1) | 55 (3.3%) | 16 | 25.5% | 8.1% |

(Other thresholds -2/-4 and -1/-1.5 were run too; same direction.)

**Findings:**
- Real but modest lift: a fire raises P(>=8% drop in next 20d) about 1.5-3x over base. But 70-88% of fires are NOT followed by such a drop (false-positive rate by this definition), and the 2010+ lift is weaker than full-history (pooled-vs-recent check: lift shrinks, e.g. 15.8% -> 12.3%).
- Lead time in the two benchmark crashes is poor. COVID: composite_5d_chg first hit -7.1 on 2026-02-26 (SPY 311.5 vs ~337 on 02-20, already ~-7.6% off the high); hyg_5d_pct did not reach -1 until 2020-03-09 (SPY 274). 2025: composite_5d_chg was -2.4 on 02-24 and -2.2 on 03-06 (SPY 597 / 573 vs 611 on 02-18), HYG 5d never below about -1.4% until 04-03, i.e. after the low-volatility drop was under way. These are coincident-to-slightly-leading, not early.
- Fires also precede positive average 20d returns (avg fwd20 +1.77% for c5<=-3 vs +0.77% unconditional full history): the signal catches sharp dips that often bounce, so it is not a de-risk signal by itself, and is not a bottom signal either (bottom/risk-on turn was not tested this run).
- Caveat: event definition and thresholds are mine, not the 08-25 validation's; I cannot say whether that validation used a different target. Differences vs it should be reconciled once the notes are restored.

**Next:** restore notes file; wire columns as live-accumulating (do not use for sizing yet).

**New backlog items added:** see IDEA_BACKLOG.md (3).
