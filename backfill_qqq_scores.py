"""
backfill_qqq_scores.py
──────────────────────
Backfills QQQ scores for all historical rows using:
- QQQ price vs 200MA (from Yahoo Finance history)
- QQQ RSI-14 (from Yahoo Finance history)
- VIX (already in CSV)
- SPY GEX regime (proxy for broad market stress)

Since we don't have historical QQQ GEX, we derive meaningful scores
from price-based technicals which are historically accurate.
"""

import csv
import requests
from datetime import datetime

CSV_PATH = "gex_log.csv"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
}

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


def fetch_qqq_history():
    """Fetch 2 years of QQQ daily closes. Returns date->close map and sorted lists."""
    for base in ["query1", "query2"]:
        try:
            url = f"https://{base}.finance.yahoo.com/v8/finance/chart/QQQ?interval=1d&range=2y"
            r = requests.get(url, headers=HEADERS, timeout=15)
            data = r.json()
            result = data["chart"]["result"]
            if not result:
                continue
            result = result[0]
            timestamps = result.get("timestamp", result.get("timestamps", []))
            closes = result["indicators"]["quote"][0]["close"]
            pairs = []
            for ts, c in zip(timestamps, closes):
                if c is not None:
                    d = datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d")
                    pairs.append((d, round(float(c), 2)))
            pairs.sort(key=lambda x: x[0])
            print(f"  QQQ: {len(pairs)} trading days from {base}")
            return pairs
        except Exception as e:
            print(f"  {base} failed: {e}")
    return []


def calc_ma(closes, window=200):
    w = min(window, len(closes))
    return round(sum(closes[-w:]) / w, 2)


def calc_rsi(closes, period=14):
    if len(closes) < period + 1:
        return None
    deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
    gains  = [max(d, 0) for d in deltas[-period:]]
    losses = [abs(min(d, 0)) for d in deltas[-period:]]
    ag = sum(gains) / period
    al = sum(losses) / period
    if al == 0:
        return 100.0
    return round(100 - (100 / (1 + ag / al)), 2)


def compute_qqq_scores(qqq_spot, qqq_ma200, qqq_rsi, vix, spy_gex):
    """
    Score QQQ using price-based technicals + VIX + SPY GEX as proxy.
    Returns (fear, bear, bull).
    """
    fear = 0
    bull = 0
    bear = 0

    # QQQ vs 200MA
    if qqq_spot is not None and qqq_ma200 is not None:
        if qqq_spot < qqq_ma200:
            fear += 1
            bear += 1   # below 200MA = downtrend
        else:
            bull += 1   # above 200MA = uptrend

    # QQQ RSI
    if qqq_rsi is not None:
        if qqq_rsi < 30:
            fear += 2   # oversold = buy zone signal
        elif qqq_rsi < 40:
            fear += 1
        if qqq_rsi > 70:
            bear += 2   # overbought = vulnerable
        elif qqq_rsi > 60:
            bull += 2
        elif qqq_rsi > 50:
            bull += 1
        if 30 < qqq_rsi < 45:
            bear += 1   # momentum rolling over

    # VIX — shared macro environment
    if vix is not None:
        if vix > 28:    fear += 2; bear += 2
        elif vix > 22:  fear += 1; bear += 1
        if vix < 15:    bull += 2
        elif vix < 18:  bull += 1
        if vix > 25:    bear += 1

    # SPY GEX as proxy for dealer positioning
    if spy_gex is not None:
        if spy_gex < -5:
            fear += 1; bear += 2
        elif spy_gex < 0:
            fear += 1; bear += 1
        elif spy_gex > 5:
            bull += 2
        elif spy_gex > 0:
            bull += 1

    fear = min(10, fear)
    bull = min(10, bull)
    bear = min(10, bear)
    return fear, bear, bull


def compute_divergence(spy_bull, spy_bear, qqq_bear, qqq_bull):
    try:
        spy_bull = int(spy_bull) if spy_bull else 0
        spy_bear = int(spy_bear) if spy_bear else 0
        qqq_bear = int(qqq_bear) if qqq_bear else 0
        qqq_bull = int(qqq_bull) if qqq_bull else 0
    except:
        return "No data"

    if spy_bull >= 6 and qqq_bear >= 5:
        return "BEARISH DIVERGENCE — SPY positive but QQQ bearish. Tech leading lower."
    if spy_bear >= 5 and qqq_bull >= 6:
        return "BULLISH DIVERGENCE — SPY bearish but QQQ turning positive. Tech stabilizing."
    if qqq_bear >= 6 and spy_bear < 4:
        return "QQQ WARNING — QQQ bear elevated before SPY. Early warning signal."
    if qqq_bull >= 7 and spy_bull >= 7:
        return "ALIGNED BULL — Both SPY and QQQ strongly positive."
    if qqq_bear >= 5 and spy_bear >= 5:
        return "ALIGNED BEAR — Both SPY and QQQ bearish. Broad market stress."
    return "Aligned — no divergence"


def safe_float(v):
    try:
        f = float(v)
        return None if (f != f) else f
    except:
        return None


def main():
    print("=" * 55)
    print("  QQQ Score Backfill (price-based technicals)")
    print("=" * 55)

    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    print(f"Loaded {len(rows)} rows")

    print("\nFetching QQQ price history (2y)...")
    qqq_pairs = fetch_qqq_history()
    if not qqq_pairs:
        print("ERROR: Could not fetch QQQ history. Aborting.")
        return

    # Build date->index lookup for point-in-time calculations
    qqq_dates  = [p[0] for p in qqq_pairs]
    qqq_closes = [p[1] for p in qqq_pairs]
    date_index = {d: i for i, d in enumerate(qqq_dates)}

    filled = 0
    for row in rows:
        d = row.get("date", "").strip()
        vix     = safe_float(row.get("vix"))
        spy_gex = safe_float(row.get("net_gex_b"))

        # Get QQQ spot (already in CSV from previous backfill)
        qqq_spot = safe_float(row.get("qqq_spot"))

        # Calculate point-in-time 200MA and RSI for QQQ
        qqq_ma200 = None
        qqq_rsi   = None

        if d in date_index:
            idx = date_index[d]
            closes_up_to = qqq_closes[:idx + 1]
            if len(closes_up_to) >= 1:
                qqq_ma200 = calc_ma(closes_up_to, 200)
            if len(closes_up_to) >= 15:
                qqq_rsi = calc_rsi(closes_up_to, 14)
        else:
            print(f"  WARNING: {d} not in QQQ history (weekend/holiday?)")

        # Compute scores
        qqq_fear, qqq_bear, qqq_bull = compute_qqq_scores(
            qqq_spot, qqq_ma200, qqq_rsi, vix, spy_gex
        )

        # Compute divergence
        divergence = compute_divergence(
            row.get("bull_score"), row.get("bear_score"),
            qqq_bear, qqq_bull
        )

        row["qqq_fear_score"] = qqq_fear
        row["qqq_bear_score"] = qqq_bear
        row["qqq_bull_score"] = qqq_bull
        row["qqq_divergence"] = divergence

        # Also update qqq_spot from our calculation if missing
        if not qqq_spot and d in date_index:
            row["qqq_spot"] = qqq_closes[date_index[d]]

        filled += 1
        print(f"  {d}  QQQ spot={row['qqq_spot']}  200MA={qqq_ma200}  RSI={qqq_rsi}  fear={qqq_fear}  bear={qqq_bear}  bull={qqq_bull}  {divergence[:40]}")

    print(f"\nFilled {filled} rows")

    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=ALL_COLS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    print(f"Done. {CSV_PATH} updated.")


if __name__ == "__main__":
    main()
