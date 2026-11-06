# Event study — 2026-11-05 black swan watch

**Tracking window:** 2026-11-05 → 2026-12-04 (≈20 trading days). Updated daily by a scheduled task after the 6pm pull.

## What happened
- SPY −4.4% (766.14 → 734.40), QQQ −6.5%, SOXX −12% (worst day since Mar 2020). VIX 16.6 → 28.2 (+70% in one day), term structure flipped to backwardation.
- Catalyst: AI/chip selloff on fears that the Democratic midterm wins slow data-center buildout (permits, local opposition), on top of expensive financing for AI capex. Oil is volatile (Iran war). The Dec 8–9 FOMC is pricing ~70% odds of a hike.
- System readings: `regime_signal` BUY_WATCH, composite 5.9 → 0.9, `black_swan_watch=True`, GEX −19.4B, put wall dropped to 730. SPY closed 0.6% above its 200-day MA (730.15).
- The Oct 30–Nov 3 STRONG_BUY (SPY 751–755) is now −2.3%. That's the first live loss for a signal that was 13/13.

## Data bug found
`regime_analyzer.py` computes `hyg_5d_change` against `macro_history.csv`, which stopped updating 2026-08-17. Every "HYG dropped $X in 5 days" warning since then has compared against mid-August HYG (~79.5), not 5 days ago. **The true 5-day HYG change on 11-05 is −0.39%.** Credit is calm. One of today's three black-swan reasons is false. The other two (backwardation, and the composite dropping 4 points in 10 days) are real. This tracker computes HYG 5d directly from `gex_log.csv`.

## Signs before the drop (in our own data)
| Signal | What it showed | Lead time |
|---|---|---|
| **QQQ breaking while SPY held** | QQQ −4.7% (724.8 → 691.1) from Oct 21 to Nov 4 while SPY was only −0.9%; QQQ GEX hit −17.2B on Oct 30. The `qqq_divergence` field said "Aligned" the whole time, because it compares scores, not price. | ~2 weeks |
| **SKEW elevated + low VIX** | SKEW 148–153 every day from Oct 27 with VIX ~17; flagged Oct 29 and again **Nov 4, the day before**. | 1–7 days |
| **VIX9D > VIX** | Short-dated fear above 30-day on Nov 2–3 (ratio 1.06), then collapsed on Nov 4's bounce. | 2–3 days |
| **Put wall stepping down** | 755 → 750 → 740, then 730 on the day. | days |
| **Copper sliding** | 40.3 → 38.6 (Oct 28 → Nov 4). | ~1 week |
| **Nov 4 "all clear" was a trap** | GEX flipped +3.7B and the signal went GREEN Hold for one day after a week of negative GEX, and VIX9D/VIX dropped to 0.92. A one-day positive GEX flip inside a negative stretch was not a reliable all-clear. | — |

All of these are from **one event**. They are candidates to test against history, not validated rules.

## Historical analogs (deep history 1995–2026, SPY ≥3.5% one-day drop, events ≥20 days apart)
| Group | n | Median further drop | Worst | >5% more downside | Median days to low | Up after 60d |
|---|---|---|---|---|---|---|
| All | 28 | −6.6% | −37.2% | 16/28 | 11 | 20/28 |
| From near highs (<2% off 60d high), like now | 6 | −1.7% | −5.5% | 1/6 | 7.5 | 6/6 |
| Already falling (≥2% off high) | 22 | −8.7% | −37.2% | 15/22 | 16.5 | 14/22 |

**Robustness check:** at a −3% threshold the near-highs group grows to 9 and picks up **2020-02-24 (−30.9% more)** and **2008-06-06 (−11.2% more)**. History leans toward a shallow drop that recovers, but roughly 1 in 5 of these turned into a real decline. In those cases credit broke and backwardation persisted, and the escalation checklist below is built to catch exactly that.

## Pre-registered checklists (fixed 2026-11-05, do not tune)
**ESCALATION** (crash path), 3+ = `ESCALATING`:
`credit_breaking` (true HYG 5d ≤ −1.5%) · `backwardation_3d` · `below_trigger_close` (< 734.40) · `below_200ma` · `deep_neg_gex_3d_vix25` · `qqq_new_low` (< 647.98)

**STABILIZATION** (fear unwinding), 4+ with ≤1 escalation = `STABILIZING`:
`contango_restored` · `vix_below_22` · `vix9d_below_vix` · `credit_holding` (HYG 5d ≥ 0) · `gex_positive` · `above_zero_gamma`

**Entry ledger** (`entry_ledger.csv`): records the first firing date and outcome of 9 candidate add rules: trigger-day close, first contango, VIX < 22, GEX > 0, close above zero gamma, first STABILIZING day, −5% / −10% from high, RSI < 30. At the end this answers "which add rule worked best for this event."

## Files
- `track_event.py`: run from the repo root; idempotent.
- `tracking_log.csv`: one row per trading day.
- `entry_ledger.csv`: add-rule results.
- `DAILY_NOTES.md`: one short entry per day from the scheduled task.

## Daily log
See `DAILY_NOTES.md`.

## Alert lookback (live log 2026-03-30 → 11-05, run 2026-11-05)
Base rate: a ≥3% SPY dip within the next 10 days followed 11/143 days (7.7%).
| Alert | Fired | Followed by ≥3% dip | Read |
|---|---|---|---|
| HYG "dropped $X in 5 days" | 31d | 7/30 | **Broken.** It compares to stale Aug-17 data. |
| SKEW elevated + VIX low | 19–25d | 5/19 | ~3x live, but **no edge over 30 yrs** (11.0% vs 11.9% for all VIX<18 days). Likely a 2026 fluke. |
| QQQ lags SPY ≥2% over 10d (new) | 32d | 6/31 | ~2.5x live. Can't test long history yet (no QQQ in deep history). |
| QQQ lag ≥2% AND SKEW≥148/VIX<18 | 10d | 3/10 | ~4x live, fired Oct 14–27 and Nov 4. Tiny n. |
| GEX flips + after ≥3 neg days | 15d | 3/15 | ~2.5x. Nov 4 was one of these. A one-day flip is not an all-clear. |
| VIX9D/VIX > 1 | 13d | 0/12 | Coincident, not leading. |
| Backwardation / composite drop | 1–2d | 0/1 | Coincident: they fire on the drop day itself. |
| Put wall stepping down | 67d | 7/66 | Noise (≈ base rate). |
All live numbers come from one bull-market window with overlapping 10-day windows, so they are hypotheses only.
