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
            continue  # not enough time to resolve a 20-trading-day forward return

        date_str = row_date.isoformat()
        regime_row = regime_by_date.get(date_str)
        if not regime_row or
