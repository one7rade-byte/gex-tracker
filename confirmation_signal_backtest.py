"""
confirmation_signal_backtest.py
────────────────────────────────
Follow-up to the composite_5d_chg / hyg_5d_pct early-warning validation
(WEEKLY_RESEARCH_LOG.md 2026-08-30, wired into regime_analyzer.py). That work
validated each ROC signal ALONE. This tests the natural next question
(IDEA_BACKLOG.md item 8): does requiring BOTH composite_5d_chg <= -3 AND
hyg_5d_pct <= -1.5% to fire on the SAME day (confirmation) meaningfully raise
the forward-drawdown hit rate above either alone, or just cut the trigger
count without adding real signal?

DATA SOURCE: deep_history_backtest_log.csv only (already on disk, no fetch).
Reuses the exact derivation and forward-drawdown methodology already
validated in roc_early_warning_backtest.py so results are directly
comparable to the single-signal numbers already in the log.

METHOD:
  - Same composite_5d_chg / hyg_5d_pct derivation, same 15-trading-day
    forward max-drawdown, same >=5% drawdown "hit" definition.
  - Confirmed signal = both metrics cross their threshold on the same date.
  - Compare confirmed vs. composite-alone vs. hyg-alone: trigger rate, hit
    rate, base rate, lift — over the HYG era (2007-04-18 on) since
    confirmation requires HYG data, and separately since 2016 to check the
    finding isn't a pre-2010 artifact per this project's own recency
    discipline.
  - Crash-window check: does confirmation fire at all in each real crash
    window, and if so, how many trading days after (or before) the
    single-signal triggers already reported?
"""

import csv
import json

LOG_CSV = "deep_history_backtest_log.csv"
OUT_JSON = "confirmation_signal_summary.json"

CRASH_WINDOWS = {
    "2008_GFC": ("2008-09-01", "2009-03-09"),
    "2020_COVID": ("2020-02-19", "2020-03-23"),
    "2022_BEAR": ("2022-01-03", "2022-10-13"),
    "2025_SELLOFF": ("2025-02-19", "2025-04-08"),
}

COMPOSITE_THRESHOLD = -3
HYG_PCT_THRESHOLD = -1.5
FORWARD_WINDOW = 15
DRAWDOWN_HIT_PCT = -5.0
RECENT_START = "2016-01-01"


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
        r["confirmed"] = False
        r["fwd_max_dd_15d"] = None
        if i >= 5:
            prev = rows[i - 5]
            if r["composite_score"] is not None and prev["composite_score"] is not None:
                r["composite_5d_chg"] = round(r["composite_score"] - prev["composite_score"], 2)
            if r["hyg"] is not None and prev["hyg"] is not None and prev["hyg"] != 0:
                r["hyg_5d_pct"] = round((r["hyg"] / prev["hyg"] - 1) * 100, 3)
        if r["composite_5d_chg"] is not None and r["hyg_5d_pct"] is not None:
            r["confirmed"] = (
                r["composite_5d_chg"] <= COMPOSITE_THRESHOLD
                and r["hyg_5d_pct"] <= HYG_PCT_THRESHOLD
            )
        if i + FORWARD_WINDOW < n and r["spy_close"]:
            window = rows[i + 1: i + 1 + FORWARD_WINDOW]
            closes = [w["spy_close"] for w in window if w["spy_close"] is not None]
            if closes:
                trough = min(closes)
                r["fwd_max_dd_15d"] = round((trough / r["spy_close"] - 1) * 100, 2)
    return rows


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


def crash_window_report(rows):
    report = {}
    for name, (start, end) in CRASH_WINDOWS.items():
        subset = [r for r in rows if start <= r["date"] <= end]
        if not subset:
            report[name] = {"note": "no data in this window"}
            continue
        window_start = subset[0]["date"]
        composite_date = first_trigger_date(
            rows, start, end, lambda r: r["composite_5d_chg"] is not None and r["composite_5d_chg"] <= COMPOSITE_THRESHOLD
        )
        hyg_date = first_trigger_date(
            rows, start, end, lambda r: r["hyg_5d_pct"] is not None and r["hyg_5d_pct"] <= HYG_PCT_THRESHOLD
        )
        confirmed_date = first_trigger_date(rows, start, end, lambda r: r["confirmed"])
        report[name] = {
            "window": f"{start} to {end}",
            "composite_alone_first_trigger": composite_date,
            "composite_alone_lead_days_vs_window_start": trading_days_between(rows, window_start, composite_date),
            "hyg_alone_first_trigger": hyg_date,
            "hyg_alone_lead_days_vs_window_start": trading_days_between(rows, window_start, hyg_date),
            "confirmed_first_trigger": confirmed_date,
            "confirmed_lead_days_vs_window_start": trading_days_between(rows, window_start, confirmed_date),
            "confirmed_lag_vs_composite_alone_days": (
                trading_days_between(rows, composite_date, confirmed_date)
                if composite_date and confirmed_date else None
            ),
            "confirmed_lag_vs_hyg_alone_days": (
                trading_days_between(rows, hyg_date, confirmed_date)
                if hyg_date and confirmed_date else None
            ),
        }
    return report


def main():
    rows = load_rows()
    rows = add_derived(rows)

    hyg_start_idx = next(i for i, r in enumerate(rows) if r["hyg_5d_pct"] is not None)
    hyg_era_rows = rows[hyg_start_idx:]
    hyg_era_recent = [r for r in hyg_era_rows if r["date"] >= RECENT_START]

    def is_composite(r):
        return r["composite_5d_chg"] is not None and r["composite_5d_chg"] <= COMPOSITE_THRESHOLD

    def is_hyg(r):
        return r["hyg_5d_pct"] is not None and r["hyg_5d_pct"] <= HYG_PCT_THRESHOLD

    def is_confirmed(r):
        return r["confirmed"]

    full_era = {
        "composite_alone": stats_for(hyg_era_rows, is_composite, "composite_5d_chg<=-3"),
        "hyg_alone": stats_for(hyg_era_rows, is_hyg, "hyg_5d_pct<=-1.5"),
        "confirmed_both": stats_for(hyg_era_rows, is_confirmed, "both same day"),
    }
    recent_era = {
        "composite_alone": stats_for(hyg_era_recent, is_composite, "composite_5d_chg<=-3"),
        "hyg_alone": stats_for(hyg_era_recent, is_hyg, "hyg_5d_pct<=-1.5"),
        "confirmed_both": stats_for(hyg_era_recent, is_confirmed, "both same day"),
    }

    summary = {
        "data_source": LOG_CSV,
        "hyg_era_range": f"{hyg_era_rows[0]['date']} to {hyg_era_rows[-1]['date']}",
        "recent_era_range": f"{hyg_era_recent[0]['date']} to {hyg_era_recent[-1]['date']}" if hyg_era_recent else None,
        "forward_window_days": FORWARD_WINDOW,
        "drawdown_hit_threshold_pct": DRAWDOWN_HIT_PCT,
        "thresholds": {"composite_5d_chg": COMPOSITE_THRESHOLD, "hyg_5d_pct": HYG_PCT_THRESHOLD},
        "hyg_era_full_history": full_era,
        "hyg_era_since_2016": recent_era,
        "crash_window_report": crash_window_report(rows),
        "note": (
            "Question is whether confirmed_both's hit_rate_pct/lift_pct_points beats "
            "both single-signal rows by more than sampling noise would explain given "
            "its much smaller n_triggered, and whether confirmation still fires early "
            "enough in each crash window to be useful rather than just filtering the "
            "single signal down to near the window's own trough."
        ),
    }
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(f"Wrote {OUT_JSON}")
    print(json.dumps({"hyg_era_full_history": full_era, "hyg_era_since_2016": recent_era}, indent=2))
    print(json.dumps(summary["crash_window_report"], indent=2))


if __name__ == "__main__":
    main()
