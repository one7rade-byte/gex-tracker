"""
sequential_confirmation_backtest.py
────────────────────────────────────
Follow-up to confirmation_signal_backtest.py (WEEKLY_RESEARCH_LOG.md 2026-09-06),
which found that requiring composite_5d_chg <= -3 AND hyg_5d_pct <= -1.5% on the
SAME day raises hit rate (+20.4pp lift full-history) but destroys most of
composite_5d_chg's lead-time edge in the 2022 bear (+56 days lag) and 2025
selloff (+30 days lag) — the two episodes where that edge mattered most.

IDEA_BACKLOG.md item 8: does requiring hyg_5d_pct to confirm WITHIN N TRADING
DAYS AFTER composite_5d_chg fires (rather than the exact same day) keep more
of composite's lead time while still cutting some false positives, compared
to composite alone and to the same-day AND version already rejected?

DATA SOURCE: deep_history_backtest_log.csv only (already on disk, no fetch).
Same derivation and forward-drawdown methodology as the prior two scripts in
this family so results are directly comparable.

SIGNAL DEFINITION: a composite_5d_chg <= -3 trigger on day T is "sequentially
confirmed" if hyg_5d_pct <= -1.5% fires on any day in [T, T+N] (N trading
days, inclusive of same-day). The confirmed signal's ACTIONABLE date is the
day the confirmation condition is actually known — i.e. day T if hyg already
fired by then, otherwise the day hyg fires within the window. This is the
realistic walk-forward date: you cannot know a composite trigger is
"confirmed" until hyg actually follows through.
"""

import csv
import json

LOG_CSV = "deep_history_backtest_log.csv"
OUT_JSON = "sequential_confirmation_summary.json"

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
CONFIRM_WINDOWS_N = [3, 5, 10, 20]


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


def is_composite(r):
    return r["composite_5d_chg"] is not None and r["composite_5d_chg"] <= COMPOSITE_THRESHOLD


def is_hyg(r):
    return r["hyg_5d_pct"] is not None and r["hyg_5d_pct"] <= HYG_PCT_THRESHOLD


def mark_sequential_confirmed(rows, n_days):
    """For each composite trigger day T, look ahead [T, T+n_days] for the first
    hyg trigger. If found at T+k, mark that day (T+k) as the actionable
    sequential-confirmed trigger for this episode of composite firing.
    A composite trigger with no hyg follow-through within the window never
    confirms (excluded, same as requiring genuine confirmation)."""
    n = len(rows)
    confirmed_flags = [False] * n
    for i in range(n):
        if not is_composite(rows[i]):
            continue
        for k in range(0, n_days + 1):
            j = i + k
            if j >= n:
                break
            if is_hyg(rows[j]):
                confirmed_flags[j] = True
                break
    for i, r in enumerate(rows):
        r[f"seq_confirmed_{n_days}"] = confirmed_flags[i]
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


def crash_window_report(rows, n_days):
    key = f"seq_confirmed_{n_days}"
    report = {}
    for name, (start, end) in CRASH_WINDOWS.items():
        subset = [r for r in rows if start <= r["date"] <= end]
        if not subset:
            report[name] = {"note": "no data in this window"}
            continue
        composite_date = first_trigger_date(rows, start, end, is_composite)
        hyg_date = first_trigger_date(rows, start, end, is_hyg)
        seq_date = first_trigger_date(rows, start, end, lambda r: r[key])
        report[name] = {
            "composite_alone_first_trigger": composite_date,
            "hyg_alone_first_trigger": hyg_date,
            "sequential_confirmed_first_trigger": seq_date,
            "seq_lag_vs_composite_alone_days": (
                trading_days_between(rows, composite_date, seq_date)
                if composite_date and seq_date else None
            ),
            "seq_lag_vs_hyg_alone_days": (
                trading_days_between(rows, hyg_date, seq_date)
                if hyg_date and seq_date else None
            ),
        }
    return report


def main():
    rows = load_rows()
    rows = add_derived(rows)
    for n_days in CONFIRM_WINDOWS_N:
        mark_sequential_confirmed(rows, n_days)

    hyg_start_idx = next(i for i, r in enumerate(rows) if r["hyg_5d_pct"] is not None)
    hyg_era_rows = rows[hyg_start_idx:]
    hyg_era_recent = [r for r in hyg_era_rows if r["date"] >= RECENT_START]

    by_n = {}
    for n_days in CONFIRM_WINDOWS_N:
        key = f"seq_confirmed_{n_days}"
        trigger_fn = lambda r, key=key: r[key]
        by_n[f"N={n_days}"] = {
            "hyg_era_full_history": stats_for(hyg_era_rows, trigger_fn, f"seq_confirmed_{n_days}d"),
            "hyg_era_since_2016": stats_for(hyg_era_recent, trigger_fn, f"seq_confirmed_{n_days}d"),
            "crash_window_report": crash_window_report(rows, n_days),
        }

    baseline = {
        "composite_alone": {
            "hyg_era_full_history": stats_for(hyg_era_rows, is_composite, "composite_5d_chg<=-3"),
            "hyg_era_since_2016": stats_for(hyg_era_recent, is_composite, "composite_5d_chg<=-3"),
        },
        "hyg_alone": {
            "hyg_era_full_history": stats_for(hyg_era_rows, is_hyg, "hyg_5d_pct<=-1.5"),
            "hyg_era_since_2016": stats_for(hyg_era_recent, is_hyg, "hyg_5d_pct<=-1.5"),
        },
    }

    summary = {
        "data_source": LOG_CSV,
        "hyg_era_range": f"{hyg_era_rows[0]['date']} to {hyg_era_rows[-1]['date']}",
        "recent_era_range": f"{hyg_era_recent[0]['date']} to {hyg_era_recent[-1]['date']}" if hyg_era_recent else None,
        "forward_window_days": FORWARD_WINDOW,
        "drawdown_hit_threshold_pct": DRAWDOWN_HIT_PCT,
        "thresholds": {"composite_5d_chg": COMPOSITE_THRESHOLD, "hyg_5d_pct": HYG_PCT_THRESHOLD},
        "confirm_windows_tested_days": CONFIRM_WINDOWS_N,
        "baseline_single_signals": baseline,
        "sequential_confirmation_by_window": by_n,
        "note": (
            "Actionable trigger date for sequential confirmation is the day the "
            "confirmation is actually known (whichever of composite/hyg fires "
            "second, within N days) -- not day T itself if hyg hasn't fired yet. "
            "Compare seq_lag_vs_composite_alone_days across N to the same-day "
            "confirmation lags already in confirmation_signal_summary.json "
            "(N=0 equivalent: 2008 +4d, 2020 +1d, 2022 +56d, 2025 +30d)."
        ),
    }
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(f"Wrote {OUT_JSON}")
    print(json.dumps(baseline, indent=2))
    for n_days in CONFIRM_WINDOWS_N:
        print(f"\n=== N={n_days} ===")
        print(json.dumps(by_n[f"N={n_days}"], indent=2))


if __name__ == "__main__":
    main()
