"""
track_signal_performance.py
────────────────────────────
Continuously tracks how well the dashboard's regime_signal system
(STRONG_BUY / BUY_WATCH / HOLD / CAUTION / STRONG_HOLD, produced daily by
regime_analyzer.py from the composite score) actually predicts forward SPY
returns — turning the one-off, manually-run backtest_signals.py report into
an accumulating track record that grows a little more meaningful every day.

Each time this runs, it:
  1. Reads gex_log.csv (SPY spot prices) and regime_log.csv (regime_signal +
     composite_score) and pairs them up by date.
  2. For every past date whose signal has now had enough trading days pass to
     measure forward returns (5 / 10 / 20 trading days), computes the
     realized SPY return over that horizon.
  3. Appends any newly-resolved (date, horizon) pairs to
     signal_performance_log.csv. A pair already recorded is never re-logged,
     so running this daily (or re-running it manually) is always safe —
     nothing is duplicated or overwritten.
  4. Rewrites signal_performance_summary.json — aggregate stats (sample
     size, average forward return, hit rate, best/worst) grouped by
     regime_signal label and horizon, computed from every row accumulated
     so far.

This does NOT require the day's data to have just been updated — it only
ever processes historical signals whose forward-return window has already
closed using whatever is currently committed, so it's safe to run at any
time of day and safe to re-run.

regime_log.csv currently has regime_signal populated back to 2026-03-30
(the system's whole history), so this starts with real signal history on
day one, unlike market_scanner.py's percentile columns which needed to
build up from scratch.
"""

import csv
import json
import os

GEX_LOG = "gex_log.csv"
REGIME_LOG = "regime_log.csv"
PERF_LOG = "signal_performance_log.csv"
SUMMARY_JSON = "signal_performance_summary.json"
HORIZONS = [5, 10, 20]


def load_spy_prices():
    """date -> spot_price, from gex_log.csv's SPY rows, sorted by date."""
    with open(GEX_LOG, newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r.get("ticker") == "SPY"]
    rows.sort(key=lambda r: r["date"])
    prices = {}
    for r in rows:
        try:
            prices[r["date"]] = float(r["spot_price"])
        except (ValueError, TypeError):
            continue
    return prices


def load_regime_signals():
    """List of {date, regime_signal, composite_score}, sorted by date, rows without a signal skipped."""
    with open(REGIME_LOG, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    rows.sort(key=lambda r: r["date"])
    out = []
    for r in rows:
        sig = (r.get("regime_signal") or "").strip()
        if not sig:
            continue
        out.append({
            "date": r["date"],
            "regime_signal": sig,
            "composite_score": r.get("composite_score", ""),
        })
    return out


def load_existing_log():
    """(set of (date, horizon) already recorded, list of existing raw rows)."""
    if not os.path.exists(PERF_LOG):
        return set(), []
    with open(PERF_LOG, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    seen = {(r["date"], int(r["horizon_days"])) for r in rows}
    return seen, rows


def main():
    prices = load_spy_prices()
    dates_sorted = sorted(prices.keys())
    date_index = {d: i for i, d in enumerate(dates_sorted)}

    signals = load_regime_signals()
    seen, existing_rows = load_existing_log()

    new_rows = []
    for sig in signals:
        d = sig["date"]
        if d not in date_index:
            continue
        idx = date_index[d]
        entry_price = prices[d]

        for horizon in HORIZONS:
            if (d, horizon) in seen:
                continue
            target_idx = idx + horizon
            if target_idx >= len(dates_sorted):
                continue  # not enough trading days have elapsed yet — check again later
            exit_date = dates_sorted[target_idx]
            exit_price = prices[exit_date]
            if entry_price == 0:
                continue
            return_pct = round((exit_price - entry_price) / entry_price * 100, 2)
            new_rows.append({
                "date": d,
                "regime_signal": sig["regime_signal"],
                "composite_score": sig["composite_score"],
                "entry_price": entry_price,
                "horizon_days": horizon,
                "exit_date": exit_date,
                "exit_price": exit_price,
                "return_pct": return_pct,
            })

    if new_rows:
        fieldnames = ["date", "regime_signal", "composite_score", "entry_price",
                      "horizon_days", "exit_date", "exit_price", "return_pct"]
        write_header = not existing_rows
        with open(PERF_LOG, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if write_header:
                writer.writeheader()
            for row in new_rows:
                writer.writerow(row)
        print(f"Logged {len(new_rows)} newly-resolved signal outcome(s).")
    else:
        print("No newly-resolved signal outcomes today "
              "(either nothing fired far enough back yet, or it's all already logged).")

    build_summary()


def build_summary():
    if not os.path.exists(PERF_LOG):
        print("No performance log yet — nothing to summarize.")
        return

    with open(PERF_LOG, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    groups = {}
    for r in rows:
        key = (r["regime_signal"], int(r["horizon_days"]))
        groups.setdefault(key, []).append(float(r["return_pct"]))

    summary = {}
    for (sig, horizon), returns in sorted(groups.items()):
        n = len(returns)
        avg = round(sum(returns) / n, 2)
        hits = sum(1 for r in returns if r > 0)
        hit_rate = round(hits / n * 100, 1)
        summary.setdefault(sig, {})[str(horizon)] = {
            "n": n,
            "avg_return_pct": avg,
            "hit_rate_pct": hit_rate,
            "best_pct": max(returns),
            "worst_pct": min(returns),
        }

    total_rows = len(rows)
    unique_dates = len(set(r["date"] for r in rows))
    output = {
        "generated_from_rows": total_rows,
        "unique_signal_days": unique_dates,
        "note": (
            "Directional only while sample sizes are small (this regime_signal "
            "system's history starts 2026-03-30) — treat hit_rate/avg_return_pct "
            "as exploratory until each bucket has a meaningful n, not statistical proof."
        ),
        "by_regime_signal": summary,
    }

    with open(SUMMARY_JSON, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)
    print(f"Wrote {SUMMARY_JSON} — {unique_dates} unique signal day(s), "
          f"{total_rows} resolved outcome(s) across all horizons.")


if __name__ == "__main__":
    main()
