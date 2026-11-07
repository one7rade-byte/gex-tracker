# Weekly Research Log

## 2026-11-07 — P1: STRONG_BUY macro gate with vol_score removed (composite-ex-vol >= 1 vs composite >= 1)

**VERDICT: rejected. Keep the current `composite >= 1` gate.** Removing vol_score from the gate adds a small number of coin-flip setups with roughly double the drawdown risk. The vol leg is not a useful confirmation step either: waiting for it costs about 1.2% and does not reduce drawdown. Neither version of the gate explains the live Oct 16–Nov 3 losers. Those fired with composite 4.5–4.7, far above either threshold.

**Why P1 before P0:** the mission names P1 explicitly, and P1 is the direct question raised on 11-05 ("the gate penalizes the panic STRONG_BUY is meant to buy"). P0/P0b are still open and come next.

**Data and method** (`research/p1_vol_gate.py`, `research/p1_confirmation_wait.py`; raw output is in `research/*_output.txt` and `p1_vol_gate_results.json`):
- `deep_history_backtest_log.csv`, 7,762 days, 1995-10-17 to 2026-08-21. GEX has no history, so the setup is the non-GEX legs of STRONG_BUY: RSI<50 (the backtest's own simple 14-day RSI), SKEW>138, VIX>17. This is a proxy. The live rule also needs GEX < −10B.
- vol_score is not stored in the log. I recovered it exactly as (composite − 1.5·credit − flow − growth − skew)/1.2, with the other legs taken from regime_analyzer's own `score_*` functions. 1,278 rows could not be recovered because composite was clamped at +8. 16 of those are setup days, but all have ex-vol ≥ 6, so they land in the same group under both gates and no classification changes.
- Groups among setup days: **A** = current gate passes (comp ≥ 1). **B** = blocked *only* by vol (comp < 1 but ex-vol ≥ 1); this is the group the proposal would add. **C** = blocked by non-vol legs (ex-vol < 1). **NEW** = A + B. Forward return and MAE come from SPY closes. MAE = worst close within the next h days vs the entry close. Episode = first day of a cluster of fire days separated by more than 10 trading days.
- **by_era:** SKEW > 138 occurred on only 2 days before 2010, so the setup never fires pre-2010. In practice this is a post-2010 rule. Pooled "full" ≈ 2010+.

**Results, 20-day horizon, day level** (base = all days in the same era):

| Era | Group | Days (% of days) | Episodes | Hit | Avg fwd | Avg MAE | P(MAE ≤ −3%) |
|---|---|---|---|---|---|---|---|
| full | base | 7762 | – | 63.8% | +0.77% | −2.75% | 34.5% |
| full | A current gate | 147 (1.89%) | 35 | 68.5% | +1.34% | −2.66% | 35.0% |
| full | **B vol-only block** | 16 (0.21%) | 9 | **50.0%** | +0.88% | **−3.98%** | **62.5%** |
| full | C non-vol block | 26 (0.33%) | 10 | 80.8% | +2.00% | −2.28% | 26.9% |
| full | NEW ex-vol gate | 160 (2.06%) | 34 | 66.7% | +1.29% | −2.75% | 37.8% |
| 2018+ | base | 2171 | – | 67.2% | +1.06% | −2.69% | 33.2% |
| 2018+ | A current gate | 137 (6.31%) | 29 | 69.2% | +1.42% | −2.61% | 33.1% |
| 2018+ | B vol-only block | 13 (0.60%) | 6 | 53.8% | +1.14% | −4.12% | 61.5% |
| 2018+ | NEW ex-vol gate | 147 (6.77%) | 28 | 67.8% | +1.40% | −2.70% | 35.7% |
| 2010–17 | A current gate | 10 | 6 | 60.0% | +0.30% | −3.26% | 60.0% |
| 2010–17 | B vol-only block | 3 | 3 | 33.3% | −0.29% | −3.37% | 66.7% |

At 10 days the picture is the same: B hit 50.0%, MAE −2.65%, P(MAE ≤ −3%) 50.0%, vs A at 59.2% / −1.87% / 27.2% (full). At the episode level (20d, full), NEW looks a bit better than A (79.4% / +1.83% / MAE −1.83% vs 77.1% / +1.33% / −2.30%), but that is 34 vs 35 episodes differing by a handful, and B's own episodes hit only 55.6% (5/9).

**The 9 B episodes (the days the proposal would turn into STRONG_BUY), fwd20 / MAE20:** 2015-12-11 −4.07/−4.93 ✗; 2016-01-08 −3.39/−3.39 ✗; 2016-06-24 (Brexit) +6.60/−1.79 ✓; 2022-04-27 −4.77/−6.66 ✗; 2024-08-05 (yen unwind) +6.71/+0.25 ✓; 2024-10-31 +5.96/+0.21 ✓; 2025-03-03 −4.18/−5.54 ✗; 2025-04-03 +5.60/**−7.49** ✓ (eventually); 2026-03-27 +12.79/−0.33 ✓. All 4 failures were VIX 22.8–31.6 days in an ongoing decline (2015-16 and 2022 bear legs, early Mar-2025). The wins include sharp one-off shocks (Brexit, Aug-2024 yen unwind, Apr-2025 tariffs) at similar VIX levels (23.2–38.6). The ex-vol composite cannot tell these apart: 2.0–3.0 for the failures vs 1.5–3.5 for the wins.

**Is the vol gate a useful "wait for confirmation" step? No.** For the 9 B episodes, waiting for the first later day with comp ≥ 1 took 1–13 days (all 9 confirmed within 20). Median cost of waiting was +1.56% (mean +1.21%). Mean MAE20 was −3.30% entering early vs −3.29% entering on confirmation, so no drawdown was avoided. To a common endpoint (blocked day + 20), early averaged +2.36% vs late +1.15%. The failures (2015-12, 2022-04, 2025-03) kept falling after confirmation, with late MAE −7.9%, −9.2% and −12.5%. A one-notch VIX drop is not confirmation of institutional buying.

**Side finding (not tested properly, logged as a backlog idea):** RSI depth matters more than the vol gate. 2018+, group A with RSI < 40: 52 days / 17 episodes, 20d hit 88.2%, avg +3.18%, MAE −2.03%, vs RSI < 50 at 69.2% / +1.42% / −2.61%. Without GEX, A at RSI < 50 is only marginally better than base (69.2% vs 67.2% hit), so in the live rule GEX < −10B and/or RSI depth must be doing most of the work.

**Caveats:** GEX leg missing (proxy setup); n(B) = 9 episodes; the deep log ends 2026-08-21, so the Nov-2026 event is outside it; the RSI method (simple average) may differ slightly from the live tracker's; overlapping 20-day windows at day level inflate apparent n.

**Live check (signal_performance_log.csv, resolved through 2026-10-30; tracking data through 11-06):**
- Resolved STRONG_BUY: 5d n=17, 82.4% hit, +1.67%, worst −2.60%; 10d n=15, 86.7%, +2.31%, worst −3.86%; 20d n=13, 100%, +2.88%. BUY_WATCH: 5d n=29, 55.2%, +0.42%; 10d n=29, 65.5%, +0.27%, worst −4.19%; 20d n=25, 80.0%, +1.13%.
- The first losses have resolved: 10-22 STRONG_BUY 10d −3.86%; 10-26 5d −1.40%; 10-30 5d −2.60%; 10-23 BUY_WATCH 10d −4.19%.
- Every STRONG_BUY from 10-16 to 11-03 (7 fires, SPY 751.96–763.86) is underwater against 11-06's 735.40, from −2.20% to −3.73%, with worst close −2.34% to −3.86%. **All 7 had composite 4.5–4.7 (vol_score 0 to +1), so neither gate version would have blocked them.** They fired at moderate VIX (18.4–21.2) and repeatedly over 3 weeks while price drifted lower and SMH/SPY was breaking down (P0). That is "early", not "confirmed", and it contradicts the philosophy more than the vol gate does. This is the real accuracy gap: see new backlog item P8.
- 11-05 was a B day (comp 0.9, ex-vol 4.5, GEX −19.4B, RSI 35.5) at 734.40. The current gate passed on 11-06 at 735.40 (comp 2.1). Cost of the one-day delay so far: +0.14%. Event state UNRESOLVED, 0/6 escalation, 0/6 stabilization, and no confirmation entry rule has fired yet.
- Note: `signal_performance_summary.json` still only reports hit rate and average return (no MAE); that is P2.

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
