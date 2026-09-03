import csv
import json
import re
import os
import requests
from datetime import datetime

ANSWER_LOG = "answer_log.csv"
REGIME_LOG = "regime_log.csv"
GEX_LOG = "gex_log.csv"
OUTPUT = "answer_accuracy_summary.json"

RAW_BASE = "https://raw.githubusercontent.com/one7rade-byte/gex-tracker/main"

# ---------------------------------------------------------------------------
# Shared fetch helpers (mirrors app.py's versions, kept standalone here since
# this script runs independently in GitHub Actions, not inside the Flask app)
# ---------------------------------------------------------------------------

def fetch_csv_tail(url, days=60):
    try:
        r = requests.get(f"{url}?t={os.urandom(4).hex()}", timeout=15)
        if not r.ok:
            return ""
        lines = r.text.strip().split("\n")
        if len(lines) <= 1:
            return r.text
        header, rows = lines[0], lines[1:]
        tail = rows[-days:] if days and days > 0 else rows
        return "\n".join([header] + tail)
    except Exception as e:
        print(f"fetch_csv_tail failed ({url}): {e}")
        return ""

def fetch_json(url):
    try:
        r = requests.get(f"{url}?t={os.urandom(4).hex()}", timeout=15)
        return r.text if r.ok else ""
    except Exception as e:
        print(f"fetch_json failed ({url}): {e}")
        return ""

SOURCE_FETCHERS = {
    "get_signal_performance": lambda: fetch_json(f"{RAW_BASE}/signal_performance_summary.json"),
    "get_sector_rotation": lambda: fetch_json(f"{RAW_BASE}/sector_rotation_top.json"),
    "get_intelligence_report": lambda: fetch_json(f"{RAW_BASE}/intelligence_report.json"),
    "get_gex_data": lambda: fetch_csv_tail(f"{RAW_BASE}/gex_log.csv", days=60),
    "get_regime_data": lambda: fetch_csv_tail(f"{RAW_BASE}/regime_log.csv", days=60),
    "get_mag7_signals": lambda: fetch_csv_tail(f"{RAW_BASE}/mag7_signals_log.csv", days=60),
}

# ---------------------------------------------------------------------------
# Loading local files
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
# 1. Extraction accuracy: do cited numbers appear in the tools actually used?
# ---------------------------------------------------------------------------

def check_extraction_accuracy(rows):
    """Compares numbers cited in each answer against the real content of
    every data source actually called for that row - not just one fixed
    file - so a number correctly pulled from get_gex_data isn't wrongly
    flagged just because get_signal_performance was also called that turn.

    Limitation, stated plainly: this only checks whether a cited number
    appears SOMEWHERE in the tools used, not whether it was attributed to
    the right claim. It catches outright invention, not misattribution."""
    checked, matched, flagged = 0, 0, []

    for row in rows:
        tools_used = [t for t in row.get("tools_called", "").split(";") if t in SOURCE_FETCHERS]
        if not tools_used:
            continue
        nums = extract_numbers(row.get("answer_preview", ""))
        if not nums:
            continue

        combined_source_text = ""
        for tool in tools_used:
            combined_source_text += SOURCE_FETCHERS[tool]() + "\n"
        source_nums = extract_numbers(combined_source_text)

        checked += 1
        if nums & source_nums:
            matched += 1
        else:
            flagged.append({
                "timestamp": row.get("timestamp"),
                "question": row.get("question"),
                "tools_used": tools_used,
                "reason": "no numbers from the answer found in any of the tools it actually called",
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
            continue

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
    regime_by_date = load_csv_by_date(REGIME_LOG)
    gex_by_date = load_csv_by_date(GEX_LOG)

    checked, matched, flagged = check_extraction_accuracy(rows)
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
            "extraction_accuracy checks whether numbers in an answer appear "
            "somewhere in the real content of every tool actually called for "
            "that row - a proxy for outright invention, not a full fact-check "
            "of whether the right number was attached to the right claim. "
            "predictive_accuracy_by_signal only includes rows 30+ days old "
            "with a resolved 20-day forward return. Small n means these "
            "results are provisional, not proven."
        ),
    }

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)
    print(f"{len(rows)} rows scanned, {checked} numeric claims checked, "
          f"{len(resolved)} predictions resolved")

if __name__ == "__main__":
    main()
