"""
vix_skew_confirmation_backtest.py
──────────────────────────────────
IDEA_BACKLOG.md item 11. Both the same-day AND-confirmation
(confirmation_signal_backtest.py, 2026-09-06) and the sequential
within-N-days version (sequential_confirmation_backtest.py, 2026-09-13)
of composite_5d_chg + hyg_5d_pct were rejected as early-warning upgrades:
real hit-rate lift, but HYG itself is the slow-confirming signal in the
2022 bear (+56 trading days lag) and 2025 selloff (+30 days), so no
confirmation window width fixes it.

Question this run: does a VOL-based confirming signal (vix_5d_pct or
skew_5d_chg, both already derivable from deep_history_backtest_log.csv,
no fetch needed) avoid that specific 2022/2025 lag, since vol/vix moved
faster than credit in both those episodes?

METHOD: same-day AND-confirmation only (not sequential — if same-day
already fails to preserve lead time the way HYG's same-day version did,
a wider window only matters if same-day actually looks promising; if it
doesn't, testing sequential windows on top adds no new information, per
the outcome already established for HYG in the 2026-09-13 run).
Thresholds for both vix_5d_pct and skew_5d_chg are chosen from the actual
distribution (80th/90th/95th percentile of 5-day changes in
deep_history_backtest_log.csv, computed directly, not guessed) and all
three are reported per signal — no cherry-picking a single "best" number
after the fact beyond what's disclosed here.
"""

import csv
import json

LOG_CSV = "deep_history_backtest_log.csv"
OUT_JSON = "vix_skew_confirmation_summary.json"

CRASH_WINDOWS = {
    "2008_GFC": ("2008-09-01", "2009-03-09"),
    "2020_COVID": ("2020-02-19", "2020-03-23"),
    "2022_BEAR": ("2022-01-03", "2022-10-13"),
    "2025_SELLOFF": ("2025-02-19", "2025-04-08"),
}

COMPOSITE_THRESHOLD = -3
FORWARD_WINDOW = 15
DRAWDOWN_HIT_PCT = -5.0
RECENT_START = "2016-01-01"

# Percentile-derived from the actual data (80th/90th/95th of 5-day changes),
# computed once via a one-off script, not hand-picked round numbers.
VIX_5D_PCT_THRESHOLDS = [9.65, 17.36, 25.11]     # 80th / 90th / 95th pct
SKEW_5D_CHG_THRESHOLDS = [3.32, 5.63, 8.22]      # 80th / 90th / 95th pct


def load_rows():
    rows = list(csv.DictReader(open(LOG_CSV, encoding="utf-8")))
    for r in rows:
        for k in ("spy_close", "composite_score", "vix", "skew"):
            r[k] = float(r[k]) if r[k] not in ("", None) else None
    return rows


def add_derived(rows):
    n = len(rows)
    for i in range(n):
        r = rows[i]
        r["composite_5d_chg"] = None
        r["vix_5d_pct"] = None
        r["skew_5d_chg"] = None
        r["fwd_max_dd_15d"] = None
        if i >= 5:
            prev = rows[i - 5]
            if r["composite_score"] is not None and prev["composite_score"] is not None:
                r["composite_5d_chg"] = round(r["composite_score"] - prev["composite_score"], 2)
            if r["vix"] is not None and prev["vix"] is not None and prev["vix"] != 0:
                r["vix_5d_pct"] = round((r["vix"] / prev["vix"] - 1) * 100, 2)
            if r["skew"] is not None and prev["skew"] is not None:
                r["skew_5d_chg"] = round(r["skew"] - prev["skew"], 2)
        if i + FORWARD_WINDOW < n and r["spy_close"]:
            window = rows[i + 1: i + 1 + FORWARD_WINDOW]
            closes = [w["spy_close"] for w in window if w["spy_close"] is not None]
            if closes:
                trough = min(closes)
                r["fwd_max_dd_15d"] = round((trough / r["spy_close"] - 1) * 100, 2)
    return rows


def is_composite(r):
    return r["composite_5d_chg"] is not None and r["composite_5d_chg"] <= COMPOSITE_THRESHOLD


def make_vix_trigger(t):
    return lambda r: r["vix_5d_pct"] is not None and r["vix_5d_pct"] >= t


def make_skew_trigger(t):
    return lambda r: r["skew_5d_chg"] is not None and r["skew_5d_chg"] >= t


def make_and_trigger(fn_a, fn_b):
    return lambda r: fn_a(r) and fn_b(r)


def stats_for(pool, trigger_fn, label):
    scoped = [r for r in pool if r["fwd_max_dd_15d"] is not None]
    if not scoped:
        return {"label": label, "n_total": 0}
    triggered = [r for r in scoped if trigger_fn(r)]
    base_hits = sum(1 for r in scoped if r["fwd_max_dd_15d"] <= DRAWDOWN_HIT_PCT)
    base_rate = round(base_hits / len(scoped) * 100, 1)
    out = {
        "label": label,
        "n_total": len(scoped),
        "n_triggered": len(triggered),
        "trigger_rate_pct": round(len(triggered) / len(scoped) * 100, 2) if scoped else None,
        "base_rate_pct": base_rate,
    }
    if triggered:
        trig_hits = sum(1 for r in triggered if r["fwd_max_dd_15d"] <= DRAWDOWN_HIT_PCT)
        out["hit_rate_pct"] = round(trig_hits / len(triggered) * 100, 1)
        out["lift_pct_points"] = round(out["hit_rate_pct"] - base_rate, 1)
        out["avg_fwd_max_dd_15d_pct"] = round(
            sum(r["fwd_max_dd_15d"] for r in triggered) / len(triggered), 2
        )
    return out


def first_trigger_date(rows, start, end, trigger_fn):
    for r in rows:
        if start <= r["date"] <= end and trigger_fn(r):
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


def crash_window_report(rows, and_trigger_fn, confirm_trigger_fn):
    report = {}
    for name, (start, end) in CRASH_WINDOWS.items():
        subset = [r for r in rows if start <= r["date"] <= end]
        if not subset:
            report[name] = {"note": "no data in this window"}
            continue
        composite_date = first_trigger_date(rows, start, end, is_composite)
        confirm_date = first_trigger_date(rows, start, end, confirm_trigger_fn)
        and_date = first_trigger_date(rows, start, end, and_trigger_fn)
        report[name] = {
            "composite_alone_first_trigger": composite_date,
            "confirm_signal_alone_first_trigger": confirm_date,
            "and_confirmed_first_trigger": and_date,
            "and_lag_vs_composite_alone_days": (
                trading_days_between(rows, composite_date, and_date)
                if composite_date and and_date else None
            ),
        }
    return report


def main():
    rows = load_rows()
    rows = add_derived(rows)

    vix_start_idx = next(i for i, r in enumerate(rows) if r["vix_5d_pct"] is not None)
    skew_start_idx = next(i for i, r in enumerate(rows) if r["skew_5d_chg"] is not None)
    vix_era_rows = rows[vix_start_idx:]
    skew_era_rows = rows[skew_start_idx:]
    vix_era_recent = [r for r in vix_era_rows if r["date"] >= RECENT_START]
    skew_era_recent = [r for r in skew_era_rows if r["date"] >= RECENT_START]

    baseline = {
        "composite_alone": {
            "full_history": stats_for(rows, is_composite, "composite_5d_chg<=-3"),
            "since_2016": stats_for([r for r in rows if r["date"] >= RECENT_START], is_composite, "composite_5d_chg<=-3"),
        },
    }

    vix_results = {}
    for t in VIX_5D_PCT_THRESHOLDS:
        vix_fn = make_vix_trigger(t)
        and_fn = make_and_trigger(is_composite, vix_fn)
        vix_results[f"vix_5d_pct>={t}"] = {
            "vix_alone_full_history": stats_for(vix_era_rows, vix_fn, f"vix_5d_pct>={t}"),
            "and_confirmed_full_history": stats_for(vix_era_rows, and_fn, f"composite AND vix_5d_pct>={t}"),
            "and_confirmed_since_2016": stats_for(vix_era_recent, and_fn, f"composite AND vix_5d_pct>={t}"),
            "crash_window_report": crash_window_report(rows, and_fn, vix_fn),
        }

    skew_results = {}
    for t in SKEW_5D_CHG_THRESHOLDS:
        skew_fn = make_skew_trigger(t)
        and_fn = make_and_trigger(is_composite, skew_fn)
        skew_results[f"skew_5d_chg>={t}"] = {
            "skew_alone_full_history": stats_for(skew_era_rows, skew_fn, f"skew_5d_chg>={t}"),
            "and_confirmed_full_history": stats_for(skew_era_rows, and_fn, f"composite AND skew_5d_chg>={t}"),
            "and_confirmed_since_2016": stats_for(skew_era_recent, and_fn, f"composite AND skew_5d_chg>={t}"),
            "crash_window_report": crash_window_report(rows, and_fn, skew_fn),
        }

    summary = {
        "data_source": LOG_CSV,
        "method": "same-day AND-confirmation only (see module docstring for why sequential wasn't tested)",
        "forward_window_days": FORWARD_WINDOW,
        "drawdown_hit_threshold_pct": DRAWDOWN_HIT_PCT,
        "composite_threshold": COMPOSITE_THRESHOLD,
        "vix_5d_pct_thresholds_pctile_basis": "80th/90th/95th percentile of actual 5d vix pct changes, 1995-2026",
        "skew_5d_chg_thresholds_pctile_basis": "80th/90th/95th percentile of actual 5d skew point changes, 1995-2026",
        "baseline_composite_alone": baseline,
        "vix_confirmation_by_threshold": vix_results,
        "skew_confirmation_by_threshold": skew_results,
        "for_comparison_hyg_same_day_and_lag_days": {
            "2008_GFC": 4, "2020_COVID": 1, "2022_BEAR": 56, "2025_SELLOFF": 30,
            "source": "confirmation_signal_summary.json, 2026-09-06 run",
        },
    }
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(f"Wrote {OUT_JSON}")
    print(json.dumps(baseline, indent=2))
    print("\n=== VIX confirmation ===")
    print(json.dumps(vix_results, indent=2))
    print("\n=== SKEW confirmation ===")
    print(json.dumps(skew_results, indent=2))


if __name__ == "__main__":
    main()
