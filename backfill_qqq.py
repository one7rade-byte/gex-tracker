"""
backfill_qqq.py
───────────────
Adds QQQ columns to existing gex_log.csv rows.
Since historical QQQ GEX is not publicly available, this backfill
populates qqq_spot from Yahoo Finance price history.
The GEX-based columns will fill from today forward via the daily script.
"""

import csv
import requests
from datetime import datetime

CSV_PATH = "gex_log.csv"

ALL_COLS = [
    "date", "ticker", "spot_price", "net_gex_b", "vix",
    "zero_gamma", "call_wall", "put_wall", "peak_gex_strike", "max_pain", "pc_ratio",
    "spy_200ma", "spy_above_200ma", "spy_rsi_14",
    "vix_3m", "vix_term_spread", "vix_term_structure",
    "skew_index",
    "fear_score", "bull_score", "bear_score", "score_label",
    "qqq_spot", "qqq_gex_b", "qqq_fear_score", "qqq_bear_score", "qqq_bull_score",
    "qqq_divergence",
    "signal", "l1_context",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
}


def fetch_qqq_history():
    """Fetch 2 years of QQQ daily closes from Yahoo Finance."""
    try:
        url = "https://query1.finance.yahoo.com/v8/finance/chart/QQQ?interval=1d&range=2y"
        r = requests.get(url, headers=HEADERS, timeout=15)
        data = r.json()
        result = data["chart"]["result"][0]
        timestamps = result.get("timestamp", result.get("timestamps", []))
        closes = result["indicators"]["quote"][0]["close"]
        date_map = {}
        for ts, c in zip(timestamps, closes):
            if c is not None:
                d = datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d")
                date_map[d] = round(float(c), 2)
        print(f"  QQQ history: {len(date_map)} days")
        return date_map
    except Exception as e:
        print(f"  QQQ history fetch failed: {e}")
        return {}


def compute_divergence(spy_bull, spy_bear, qqq_bear, qqq_bull):
    try:
        spy_bull = int(spy_bull) if spy_bull else 0
        spy_bear = int(spy_bear) if spy_bear else 0
        qqq_bear = int(qqq_bear) if qqq_bear else 0
        qqq_bull = int(qqq_bull) if qqq_bull else 0
    except:
        return "No data"
    if spy_bull >= 6 and qqq_bear >= 5:
        return "BEARISH DIVERGENCE — SPY positive but QQQ GEX bearish. Tech leading lower."
    if spy_bear >= 5 and qqq_bull >= 6:
        return "BULLISH DIVERGENCE — SPY bearish but QQQ GEX turning positive. Tech stabilizing."
    if qqq_bear >= 6 and spy_bear < 4:
        return "QQQ WARNING — QQQ bear score elevated before SPY. Early warning signal."
    if qqq_bull >= 7 and spy_bull >= 7:
        return "ALIGNED BULL — Both SPY and QQQ GEX strongly positive."
    if qqq_bear >= 5 and spy_bear >= 5:
        return "ALIGNED BEAR — Both SPY and QQQ GEX bearish. Broad market stress."
    return "Aligned — no divergence"


def main():
    print("=" * 50)
    print("  QQQ Backfill")
    print("=" * 50)

    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    print(f"Loaded {len(rows)} rows")

    print("\nFetching QQQ price history...")
    qqq_map = fetch_qqq_history()

    filled = 0
    for row in rows:
        d = row.get("date", "").strip()
        # Always overwrite to ensure new columns exist
        row["qqq_spot"]       = qqq_map.get(d, "")
        row["qqq_gex_b"]      = ""   # not backfillable — needs live options data
        row["qqq_fear_score"] = ""
        row["qqq_bear_score"] = ""
        row["qqq_bull_score"] = ""
        row["qqq_divergence"] = compute_divergence(
            row.get("bull_score"), row.get("bear_score"), "", ""
        )
        filled += 1

    print(f"Updated {filled} rows with QQQ price data")
    print("Note: qqq_gex_b and qqq scores will populate from today forward via daily script")

    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=ALL_COLS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    print(f"Done. {CSV_PATH} updated.")


if __name__ == "__main__":
    main()
