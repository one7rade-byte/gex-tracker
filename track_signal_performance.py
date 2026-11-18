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
  5. Records the path, not just the endpoint: mae_pct (maximum adverse
     excursion = worst SPY close in days t+1..t+h vs the entry close) and
     mfe_pct (best close). A 100% hit rate can hide a -3% dip first; the
     summary reports avg/median/worst MAE, P(MAE <= -2% / -3%) and how many
     eventual winners first dipped <= -2%. Older rows logged before these
     columns existed are backfilled from gex_log.csv on the next run
     (closes only, so intraday lows are not captured: MAE is understated).
  6. Lists STRONG_BUY / BUY_WATCH calls whose 20d window is still open,
     with return and MAE to date, so a losing cluster is visible before it
     resolves (e.g. the Oct 16 - Nov 3 2026 STRONG_BUY cluster).

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
FIELDNAMES = ["date", "regime_signal", "composite_score", "entry_price",
              "horizon_days", "exit_date", "exit_price", "return_pct",
              "mae_pct", "mfe_pct"]
OPEN_WINDOW_SIGNALS = ("STRONG_BUY", "BUY_WATCH")

# All labels get_regime_signal() in regime_analyzer.py can emit. Used so the
# summary can call out signals that have NEVER fired live yet (e.g. DEFENSIVE/
# CRISIS, which require real credit stress that hasn't occurred since this
# system launched 2026-03-30) instead of just silently omitting them.
ALL_REGIME_SIGNALS = ["STRONG_BUY", "BUY_WATCH", "HOLD", "CAUTION", "STRONG_HOLD", "DEFENSIVE", "CRISIS"]

# Confidence tiers for n — purely a labeling discipline (no thresholds here
# touch regime_analyzer.py's actual signal logic). Keeps the project's
# "never treat small-n results as proven" rule enforced automatically in the
# output, not just in a note someone has to remember to add by hand.
def confidence_tier(n):
    if n < 10:
        return "small_sample — exploratory only, do not rely on this bucket"
    if n < 30:
        return "developing — directional, treat cautiously"
    return "reasonably sampled — still not a guarantee, but n supports the read"


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


def path_excursions(prices, dates_sorted, idx, horizon, entry_price):
    """(mae_pct, mfe_pct) over closes idx+1..idx+horizon vs entry_price, or (None, None)."""
    if entry_price == 0 or idx + horizon >= len(dates_sorted):
        return None, None
    path = [prices[dates_sorted[j]] for j in range(idx + 1, idx + horizon + 1)]
    mae = round((min(path) - entry_price) / entry_price * 100, 2)
    mfe = round((max(path) - entry_price) / entry_price * 100, 2)
    return mae, mfe


def backfill_excursions(rows, prices, dates_sorted, date_index):
    """Fill mae_pct/mfe_pct on rows logged before those columns existed. Returns count filled."""
    filled = 0
    for r in rows:
        if r.get("mae_pct") not in (None, "") and r.get("mfe_pct") not in (None, ""):
            continue
        d = r["date"]
        if d not in date_index:
            continue
        try:
            entry = float(r["entry_price"])
        except (TypeError, ValueError):
            continue
        mae, mfe = path_excursions(prices, dates_sorted, date_index[d], int(r["horizon_days"]), entry)
        if mae is None:
            continue
        r["mae_pct"], r["mfe_pct"] = mae, mfe
        filled += 1
    return filled


def open_windows(signals, prices, dates_sorted, date_index, horizon=20):
    """STRONG_BUY/BUY_WATCH calls whose `horizon` window hasn't closed: return and MAE to date."""
    out = []
    last = len(dates_sorted) - 1
    for sig in signals:
        if sig["regime_signal"] not in OPEN_WINDOW_SIGNALS or sig["date"] not in date_index:
            continue
        idx = date_index[sig["date"]]
        if idx + horizon <= last:
            continue
        entry = prices[sig["date"]]
        if entry == 0:
            continue
        path = [prices[dates_sorted[j]] for j in range(idx + 1, last + 1)]
        out.append({
            "date": sig["date"],
            "regime_signal": sig["regime_signal"],
            "composite_score": sig["composite_score"],
            "entry_price": entry,
            "days_elapsed": len(path),
            "return_to_date_pct": round((path[-1] - entry) / entry * 100, 2) if path else None,
            "mae_to_date_pct": round((min(path) - entry) / entry * 100, 2) if path else None,
        })
    return out


def main():
    prices = load_spy_prices()
    dates_sorted = sorted(prices.keys())
    date_index = {d: i for i, d in enumerate(dates_sorted)}

    signals = load_regime_signals()
    seen, existing_rows = load_existing_log()
    backfilled = backfill_excursions(existing_rows, prices, dates_sorted, date_index)

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
            mae, mfe = path_excursions(prices, dates_sorted, idx, horizon, entry_price)
            new_rows.append({
                "date": d,
                "regime_signal": sig["regime_signal"],
                "composite_score": sig["composite_score"],
                "entry_price": entry_price,
                "horizon_days": horizon,
                "exit_date": exit_date,
                "exit_price": exit_price,
                "return_pct": return_pct,
                "mae_pct": mae,
                "mfe_pct": mfe,
            })

    if new_rows or backfilled or (existing_rows and "mae_pct" not in existing_rows[0]):
        # Rewrite the whole file (not append) so the header carries the new
        # columns and backfilled rows are saved. Existing rows' own values
        # (entry/exit/return) are kept exactly as logged.
        with open(PERF_LOG, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction="ignore")
            writer.writeheader()
            for row in existing_rows + new_rows:
                writer.writerow({k: row.get(k, "") for k in FIELDNAMES})
        print(f"Logged {len(new_rows)} newly-resolved signal outcome(s)"
              f"{f'; backfilled MAE/MFE on {backfilled} older row(s)' if backfilled else ''}.")
    else:
        print("No newly-resolved signal outcomes today "
              "(either nothing fired far enough back yet, or it's all already logged).")

    build_summary(open_windows(signals, prices, dates_sorted, date_index))


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def build_summary(open_list=None):
    if not os.path.exists(PERF_LOG):
        print("No performance log yet — nothing to summarize.")
        return

    with open(PERF_LOG, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    groups, mae_groups = {}, {}
    for r in rows:
        key = (r["regime_signal"], int(r["horizon_days"]))
        groups.setdefault(key, []).append(float(r["return_pct"]))
        mae, mfe = _f(r.get("mae_pct")), _f(r.get("mfe_pct"))
        if mae is not None and mfe is not None:
            mae_groups.setdefault(key, []).append((float(r["return_pct"]), mae, mfe))

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
            "confidence": confidence_tier(n),
        }
        triples = mae_groups.get((sig, horizon), [])
        if triples:
            maes = sorted(t[1] for t in triples)
            m = len(maes)
            med = maes[m // 2] if m % 2 else (maes[m // 2 - 1] + maes[m // 2]) / 2
            winners = [t for t in triples if t[0] > 0]
            summary[sig][str(horizon)].update({
                "n_with_mae": m,
                "avg_mae_pct": round(sum(maes) / m, 2),
                "median_mae_pct": round(med, 2),
                "worst_mae_pct": maes[0],
                "pct_mae_le_minus2": round(sum(1 for x in maes if x <= -2) / m * 100, 1),
                "pct_mae_le_minus3": round(sum(1 for x in maes if x <= -3) / m * 100, 1),
                "avg_mfe_pct": round(sum(t[2] for t in triples) / m, 2),
                "winners_that_first_dipped_le_minus2": sum(1 for t in winners if t[1] <= -2),
                "winners": len(winners),
            })

    signals_seen = {r["regime_signal"] for r in rows}
    never_fired_live = sorted(s for s in ALL_REGIME_SIGNALS if s not in signals_seen)

    total_rows = len(rows)
    unique_dates = len(set(r["date"] for r in rows))
    output = {
        "generated_from_rows": total_rows,
        "unique_signal_days": unique_dates,
        "note": (
            "Directional only while sample sizes are small (this regime_signal "
            "system's history starts 2026-03-30) — treat hit_rate/avg_return_pct "
            "as exploratory until each bucket has a meaningful n, not statistical proof. "
            "Each bucket below carries its own 'confidence' tag for the same reason — "
            "read it before acting on a bucket's numbers."
        ),
        "never_fired_live": never_fired_live,
        "never_fired_live_note": (
            "Signals in this list have zero occurrences in the live log above — "
            "either because the real triggering condition hasn't occurred since "
            "2026-03-30 (e.g. DEFENSIVE/CRISIS need real credit stress; this window "
            "has been a sustained bull run) or because only 1 occurrence exists "
            "(flagged via its own 'small_sample' confidence tag instead). No live "
            "accuracy claim can be made for anything in this list yet — see "
            "deep_history_backtest_summary.json for the only available (historical, "
            "pre-live) evidence on how these regimes have behaved."
        ),
        "mae_note": (
            "mae_pct = worst SPY close within the horizon vs the entry close "
            "(closes only, so intraday lows are not captured and MAE is understated); "
            "mfe_pct = best close. Read hit_rate alongside pct_mae_le_minus3: a "
            "signal that wins in 20d but first draws down 3%+ is a known-risk entry."
        ),
        "by_regime_signal": summary,
        "open_20d_windows": open_list or [],
        "open_20d_windows_note": (
            "STRONG_BUY/BUY_WATCH calls whose 20-trading-day window has not closed yet, "
            "with return and MAE to date (not counted in by_regime_signal until resolved)."
        ),
    }

    with open(SUMMARY_JSON, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)
    print(f"Wrote {SUMMARY_JSON} — {unique_dates} unique signal day(s), "
          f"{total_rows} resolved outcome(s) across all horizons.")


if __name__ == "__main__":
    main()
