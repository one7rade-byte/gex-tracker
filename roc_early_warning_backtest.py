"""
roc_early_warning_backtest.py
──────────────────────────────
Tests whether the RATE OF CHANGE of composite_score and HYG (5-trading-day
delta), rather than their raw LEVEL, gives earlier warning of real drawdowns
— and whether a sharp positive reversal in the same series flags the
recovery/bottom early enough to participate in it.

WHY THIS TEST: deep_history_backtest_summary.json's crash_window_analysis
already shows the LEVEL-based signal (composite_score / flow_regime) missed
a large share of real crash days — during 2020 COVID only 33-42% of days in
the crash window were flagged defensive, and 2022 BEAR only 45-54%. A level
threshold is inherently reactive: composite_score has to actually cross into
"stress" territory before it fires, which can lag a fast unwind. A
rate-of-change measure asks a different question — "is this deteriorating
fast," independent of what level it started from — and could fire earlier.

DATA SOURCE: reads deep_history_backtest_log.csv, which deep_history_backtest.py
already built from real Yahoo daily history (spy_close, composite_score, hyg,
etc., 1995-10-17 to the latest run). This script does NOT fetch anything new —
it only derives composite_5d_chg and hyg_5d_pct from data already on disk, per
this project's own network-allowlist constraints and existing discipline
(reuse regime_analyzer.py's actual scoring logic and the deep-history file
rather than re-deriving things by hand).

METHOD:
  - composite_5d_chg = composite_score[t] - composite_score[t-5]
  - hyg_5d_pct       = (hyg[t] / hyg[t-5] - 1) * 100   (HYG data starts 2007-04-11,
                        so this half of the test only covers 2007-present —
                        2008 GFC onward, not the full 1995- history)
  - For a grid of thresholds, at every day where the metric crosses the
    threshold, check the REAL forward max drawdown in SPY over the next 15
    trading days (computed from spy_close directly, not the return_Nd point
    estimates, so a fast interim drop isn't averaged away).
  - Compare the trigger's hit rate (forward drawdown >= 5%) against the
    UNCONDITIONAL base rate over the same era, to see if the signal actually
    adds anything beyond "sometimes markets just drop."
  - For each of the four real crash windows already defined in
    deep_history_backtest.py (2008 GFC, 2020 COVID, 2022 BEAR) plus a newly
    identified 2025 SELLOFF window (SPY -19.0% from 2025-02-19 to
    2025-04-08 in this dataset), report first-trigger lead time vs the
    window start, and vs when the LEVEL-based flow_regime first flagged
    defensive in the same window (so ROC vs level lead time is a direct,
    honest comparison, not a claim in isolation).
  - Same thing in reverse for the recovery side: does the metric swinging
    back sharply positive near the trough flag the turn early, measured by
    forward 20d SPY return from the first reversal trigger inside each
    window.

Output: roc_early_warning_summary.json
"""

import csv
import json

LOG_CSV = "deep_history_backtest_log.csv"
OUT_JSON = "roc_early_warning_summary.json"

CRASH_WINDOWS = {
    "2008_GFC": ("2008-09-01", "2009-03-09"),
    "2020_COVID": ("2020-02-19", "2020-03-23"),
    "2022_BEAR": ("2022-01-03", "2022-10-13"),
    "2025_SELLOFF": ("2025-02-19", "2025-04-08"),
}

COMPOSITE_THRESHOLDS = [-2, -3, -4]
HYG_PCT_THRESHOLDS = [-1.0, -1.5, -2.0]
FORWARD_WINDOW = 15          # trading days, for forward max-drawdown check
DRAWDOWN_HIT_PCT = -5.0      # what counts as "the warning was right"
REVERSAL_LOOKFORWARD = 20    # trading days, for recovery-side return check


def load_rows():
    rows = list(csv.DictReader(open(LOG_CSV, encoding="utf-8")))
    for r in rows:
        for k in ("spy_close", "composite_score", "hyg"):
            r[k] = float(r[k]) if r[k] not in ("", None) else None
    return rows


def add_derived(rows):
    n = len(rows)
    for i in range(n):
        r = rows[i]
        r["composite_5d_chg"] = None
        r["hyg_5d_pct"] = None
        r["fwd_max_dd_15d"] = None
        if i >= 5:
            prev = rows[i - 5]
            if r["composite_score"] is not None and prev["composite_score"] is not None:
                r["composite_5d_chg"] = round(r["composite_score"] - prev["composite_score"], 2)
            if r["hyg"] is not None and prev["hyg"] is not None and prev["hyg"] != 0:
                r["hyg_5d_pct"] = round((r["hyg"] / prev["hyg"] - 1) * 100, 3)
        if i + FORWARD_WINDOW < n and r["spy_close"]:
            window = rows[i + 1: i + 1 + FORWARD_WINDOW]
            closes = [w["spy_close"] for w in window if w["spy_close"] is not None]
            if closes:
                trough = min(closes)
                r["fwd_max_dd_15d"] = round((trough / r["spy_close"] - 1) * 100, 2)
    return rows


def threshold_stats(rows, metric, threshold, subset_filter=None):
    pool = [r for r in rows if r["fwd_max_dd_15d"] is not None and r[metric] is not None]
    if subset_filter:
        pool = [r for r in pool if subset_filter(r)]
    if not pool:
        return {"n_total": 0}
    triggered = [r for r in pool if r[metric] <= threshold]
    base_hits = sum(1 for r in pool if r["fwd_max_dd_15d"] <= DRAWDOWN_HIT_PCT)
    base_rate = round(base_hits / len(pool) * 100, 1)
    if not triggered:
        return {"n_total": len(pool), "n_triggered": 0, "base_rate_pct": base_rate}
    trig_hits = sum(1 for r in triggered if r["fwd_max_dd_15d"] <= DRAWDOWN_HIT_PCT)
    return {
        "n_total": len(pool),
        "n_triggered": len(triggered),
        "trigger_rate_pct": round(len(triggered) / len(pool) * 100, 1),
        "hit_rate_pct": round(trig_hits / len(triggered) * 100, 1),
        "base_rate_pct": base_rate,
        "lift_pct_points": round(trig_hits / len(triggered) * 100 - base_rate, 1),
        "avg_fwd_max_dd_15d_pct": round(sum(r["fwd_max_dd_15d"] for r in triggered) / len(triggered), 2),
    }


def first_trigger_in_window(rows, metric, threshold, start, end, direction="below"):
    for r in rows:
        if start <= r["date"] <= end and r[metric] is not None:
            if (direction == "below" and r[metric] <= threshold) or \
               (direction == "above" and r[metric] >= threshold):
                return r["date"], r[metric]
    return None, None


def first_level_defensive_in_window(rows, start, end):
    defensive_labels = {"recession_fear", "risk_off", "credit_crisis", "mild_risk_off", "cash_hoarding"}
    for r in rows:
        if start <= r["date"] <= end and r["flow_regime"] in defensive_labels:
            return r["date"]
    return None


def trading_days_between(rows, d1, d2):
    if d1 is None or d2 is None:
        return None
    dates = [r["date"] for r in rows]
    try:
        i1, i2 = dates.index(d1), dates.index(d2)
    except ValueError:
        return None
    return i2 - i1


def crash_window_report(rows):
    report = {}
    for name, (start, end) in CRASH_WINDOWS.items():
        subset = [r for r in rows if start <= r["date"] <= end]
        if not subset:
            report[name] = {"note": "no data in this window"}
            continue
        window_start = subset[0]["date"]
        level_defensive_date = first_level_defensive_in_window(rows, start, end)

        composite_trigger_date, composite_trigger_val = first_trigger_in_window(
            rows, "composite_5d_chg", -3, start, end, "below"
        )
        hyg_trigger_date, hyg_trigger_val = first_trigger_in_window(
            rows, "hyg_5d_pct", -1.5, start, end, "below"
        )

        min_row = min(subset, key=lambda r: r["spy_close"] if r["spy_close"] else 1e18)
        bottom_date = min_row["date"]
        bottom_idx = [r["date"] for r in rows].index(bottom_date)
        # Search the 40 trading days AFTER the actual bottom for the reversal —
        # the crash window itself ends at/near the bottom by construction, so
        # looking inside it can never find a post-bottom recovery signal.
        search_end_idx = min(bottom_idx + 40, len(rows) - 1)
        recovery_slice_start = rows[bottom_idx]["date"]
        recovery_slice_end = rows[search_end_idx]["date"]

        composite_reversal_date, _ = first_trigger_in_window(
            rows, "composite_5d_chg", 3, recovery_slice_start, recovery_slice_end, "above"
        )
        reversal_return_20d = None
        reversal_lead_days_vs_bottom = None
        if composite_reversal_date:
            idx = [r["date"] for r in rows].index(composite_reversal_date)
            reversal_lead_days_vs_bottom = idx - bottom_idx
            if idx + REVERSAL_LOOKFORWARD < len(rows):
                reversal_return_20d = rows[idx]["return_20d"]

        report[name] = {
            "window": f"{start} to {end}",
            "spy_bottom_date": bottom_date,
            "composite_5d_chg<=-3_first_trigger": composite_trigger_date,
            "composite_5d_chg_lead_days_vs_window_start": trading_days_between(rows, window_start, composite_trigger_date)
            if composite_trigger_date else None,
            "hyg_5d_pct<=-1.5_first_trigger": hyg_trigger_date,
            "hyg_5d_pct_lead_days_vs_window_start": trading_days_between(rows, window_start, hyg_trigger_date)
            if hyg_trigger_date else None,
            "level_flow_regime_first_defensive": level_defensive_date,
            "level_lead_days_vs_window_start": trading_days_between(rows, window_start, level_defensive_date)
            if level_defensive_date else None,
            "composite_reversal(>=+3)_within_40d_after_bottom": composite_reversal_date,
            "reversal_lead_days_after_bottom": reversal_lead_days_vs_bottom,
            "reversal_trigger_fwd_return_20d_pct": reversal_return_20d,
        }
    return report


def main():
    rows = load_rows()
    rows = add_derived(rows)

    hyg_start_idx = next(i for i, r in enumerate(rows) if r["hyg_5d_pct"] is not None)
    hyg_era_rows = rows[hyg_start_idx:]

    composite_grid = {
        str(t): threshold_stats(rows, "composite_5d_chg", t) for t in COMPOSITE_THRESHOLDS
    }
    hyg_grid = {
        str(t): threshold_stats(hyg_era_rows, "hyg_5d_pct", t) for t in HYG_PCT_THRESHOLDS
    }

    # Recency check — same discipline as deep_history_backtest.py: a pooled
    # full-history number can hide a regime change, so re-check the last 10y.
    recent_start = "2016-01-01"
    composite_grid_recent = {
        str(t): threshold_stats(rows, "composite_5d_chg", t, lambda r: r["date"] >= recent_start)
        for t in COMPOSITE_THRESHOLDS
    }
    hyg_grid_recent = {
        str(t): threshold_stats(hyg_era_rows, "hyg_5d_pct", t, lambda r: r["date"] >= recent_start)
        for t in HYG_PCT_THRESHOLDS
    }

    summary = {
        "data_source": LOG_CSV,
        "date_range": f"{rows[0]['date']} to {rows[-1]['date']}",
        "hyg_data_starts": rows[hyg_start_idx]["date"],
        "forward_window_days": FORWARD_WINDOW,
        "drawdown_hit_threshold_pct": DRAWDOWN_HIT_PCT,
        "composite_5d_chg_full_history": composite_grid,
        "composite_5d_chg_since_2016": composite_grid_recent,
        "hyg_5d_pct_since_hyg_start": hyg_grid,
        "hyg_5d_pct_since_2016": hyg_grid_recent,
        "crash_window_report": crash_window_report(rows),
        "note": (
            "hit_rate_pct/base_rate_pct/lift_pct_points is the real test: lift near "
            "zero or negative means the ROC threshold isn't adding anything over the "
            "unconditional odds of a >=5% 15-day drawdown in this sample. "
            "crash_window_report compares ROC first-trigger date against the existing "
            "LEVEL-based flow_regime first-defensive date in the same real window — "
            "a positive lead_days difference in ROC's favor is the actual claim being "
            "tested, not an assumption."
        ),
    }
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(f"Wrote {OUT_JSON}")
    print(json.dumps(summary["crash_window_report"], indent=2))


if __name__ == "__main__":
    main()
