import csv
import json
import re
from datetime import datetime

ANSWER_LOG = "answer_log.csv"
REGIME_LOG = "regime_log.csv"
GEX_LOG = "gex_log.csv"
SIGNAL_PERF = "signal_performance_summary.json"
OUTPUT = "answer_accuracy_summary.json"

# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def load_answer_log():
    with open(ANSWER_LOG, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))

def load_csv_by_date(path, date_col="date"):
    """ASSUMPTION: adjust date_col if your CSV's date column has a
    different header (e.g. 'Date', 'timestamp')."""
    out = {}
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            d = r.get(date_col)
            if d:
                out[d] = r
    return out

def extract_numbers(text):
    return set(re.findall(r'-?\d+\.?\d*%?', text))

# ---------------------------------------------------------------------------
# 1. Extraction accuracy: do cited numbers actually appear in source data?
# ---------------------------------------------------------------------------

def check_extraction_accuracy(rows, signal_perf_text):
    checked, matched, flagged = 0, 0, []
    source_nums = extract_numbers(signal_perf_text)
    for row in rows:
        if "get_signal_performance" not in row.get("tools_called", ""):
            continue
        nums = extract_numbers(row.get("answer_preview", ""))
        if not nums:
            continue
        checked += 1
        if nums & source_nums:
            matched += 1
        else:
            flagged.append({
                "timestamp": row.get("timestamp"),
                "question": row.get("question"),
                "reason": "no numbers from the answer found in signal_performance_summary.json",
                "answer_preview": row.get("answer_preview"),
            })
    return checked, matched, flagged

# ---------------------------------------------------------------------------
# 2. Predictive accuracy: did regime calls that are now resolvable pan out?
# ---------------------------------------------------------------------------

def resolve_predictions(rows, regime_by_date, gex_by_date):
    """ASSUMPTION: gex_log.csv has a 'spy_close' column. Adjust if named
    differently (e.g. 'SPY_close', 'close')."""
    resolved = []
    today = datetime.utcnow().date()
    dates_sorted = sorted(gex_by_date.keys())

    for row in rows:
        tools = row.get("tools_called", "")
        if "get_regime_data" not in tools and "get_gex_data" not in tools:
            continue
        try:
            row_date = datetime.strptime(row.get("timestamp", "")[:10], "%Y-%m-%d").date()
        except ValueError:
            continue
        if (today - row_date).days < 30:
            continue  # not enough time to resolve a 20-trading-day forward return

        date_str = row_date.isoformat()
        regime_row = regime_by_date.get(date_str)
        if not regime_row or date_str not in dates_sorted:
            continue

        idx = dates_sorted.index(date_str)
        if idx + 20 >= len(dates_sorted):
            continue

        try:
            start_price = float(gex_by_date[dates_sorted[idx]].get("spy_close", 0) or 0)
            end_price = float(gex_by_date[dates_sorted[idx + 20]].get("spy_close", 0) or 0)
        except ValueError:
            continue
        if start_price <= 0:
            continue

        resolved.append({
            "date": date_str,
            "signal": regime_row.get("regime_signal"),
            "fwd_return_20d_pct": round((end_price - start_price) / start_price * 100, 2),
        })
    return resolved

def summarize_predictions(resolved):
    by_signal = {}
    for r in resolved:
        by_signal.setdefault(r["signal"], []).append(r["fwd_return_20d_pct"])
    return {
        signal: {
            "n": len(rets),
            "avg_fwd_return_20d_pct": round(sum(rets) / len(rets), 2),
            "hit_rate_pct": round(100 * sum(1 for x in rets if x > 0) / len(rets), 1),
        }
        for signal, rets in by_signal.items()
    }

# ---------------------------------------------------------------------------

def main():
    rows = load_answer_log()
    with open(SIGNAL_PERF, encoding="utf-8") as f:
        signal_perf_text = f.read()
    regime_by_date = load_csv_by_date(REGIME_LOG)
    gex_by_date = load_csv_by_date(GEX_LOG)

    checked, matched, flagged = check_extraction_accuracy(rows, signal_perf_text)
    resolved = resolve_predictions(rows, regime_by_date, gex_by_date)
    pred_summary = summarize_predictions(resolved)

    output = {
        "generated_at": datetime.utcnow().isoformat(),
        "total_answer_rows": len(rows),
        "extraction_accuracy": {
            "numeric_claims_checked": checked,
            "numeric_claims_matched": matched,
            "match_rate_pct": round(100 * matched / checked, 1) if checked else None,
            "flagged_examples": flagged[:10],
        },
        "predictive_accuracy_by_signal": pred_summary,
        "note": (
            "extraction_accuracy checks whether numbers in an answer citing "
            "get_signal_performance appear in the real source file — a proxy "
            "for hallucination, not a full fact-check. predictive_accuracy_by_signal "
            "only includes rows 30+ days old with a resolved 20-day forward "
            "return. Small n means these are provisional, not proven."
        ),
    }

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)
    print(f"{len(rows)} rows scanned, {checked} numeric claims checked, "
          f"{len(resolved)} predictions resolved")

if __name__ == "__main__":
    main()
