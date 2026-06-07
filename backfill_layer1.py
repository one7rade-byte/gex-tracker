"""
backfill_layer1.py
──────────────────
One-time script that adds Layer 1 columns to every existing row in gex_log.csv.

Run once in GitHub Actions (or locally) via:
    python backfill_layer1.py

It rewrites gex_log.csv in place with the new columns filled.
Safe to re-run — already-filled rows are skipped.
"""

import csv
import requests
from datetime import datetime, timedelta

CSV_PATH = "gex_log.csv"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
}

NEW_COLS = [
    "spy_200ma", "spy_above_200ma", "spy_rsi_14",
    "vix_3m", "vix_term_spread", "vix_term_structure",
    "skew_index", "l1_context",
]

ALL_COLS = [
    "date", "ticker", "spot_price", "net_gex_b", "vix",
    "zero_gamma", "call_wall", "put_wall", "peak_gex_strike", "max_pain", "pc_ratio",
    "spy_200ma", "spy_above_200ma", "spy_rsi_14",
    "vix_3m", "vix_term_spread", "vix_term_structure",
    "skew_index",
    "signal", "l1_context",
]


# ── Yahoo Finance helpers ─────────────────────────────────────────────────────

def yf_fetch(symbol, period="2y", interval="1d"):
    """Fetch full daily OHLCV from Yahoo Finance. Returns (timestamps, closes) lists."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{requests.utils.quote(symbol)}?interval={interval}&range={period}"
    r = requests.get(url, headers=HEADERS, timeout=15)
    data = r.json()
    result = data["chart"]["result"][0]
    ts     = result.get("timestamp", result.get("timestamps", []))
    closes = result["indicators"]["quote"][0]["close"]
    # pair up and drop None closes
    pairs = [(t, c) for t, c in zip(ts, closes) if c is not None]
    return pairs  # list of (unix_timestamp, close_price)


def ts_to_date(ts):
    return datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d")


def build_daily_map(pairs):
    """Dict of date_str -> close_price."""
    return {ts_to_date(t): c for t, c in pairs}


# ── Technical calculations ────────────────────────────────────────────────────

def calc_200ma(closes_list):
    window = min(200, len(closes_list))
    return round(sum(closes_list[-window:]) / window, 2)


def calc_rsi14(closes_list):
    if len(closes_list) < 15:
        return None
    deltas = [closes_list[i] - closes_list[i-1] for i in range(1, len(closes_list))]
    gains  = [max(d, 0) for d in deltas[-14:]]
    losses = [abs(min(d, 0)) for d in deltas[-14:]]
    avg_gain = sum(gains) / 14
    avg_loss = sum(losses) / 14
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


# ── Context builder ───────────────────────────────────────────────────────────

def compute_l1_context(spy_above, rsi, structure, skew, vix):
    parts = []
    if spy_above is not None:
        parts.append("SPY above 200MA (uptrend intact)" if spy_above else "SPY BELOW 200MA (downtrend warning)")
    if rsi is not None:
        if rsi < 30:   parts.append(f"RSI oversold ({rsi})")
        elif rsi > 70: parts.append(f"RSI overbought ({rsi})")
        else:          parts.append(f"RSI neutral ({rsi})")
    if structure == "backwardation": parts.append("VIX in backwardation (stress elevated)")
    elif structure == "contango":    parts.append("VIX in contango (calm)")
    if skew is not None:
        if skew > 135:   parts.append(f"SKEW elevated ({skew}) - tail hedging active")
        elif skew < 115: parts.append(f"SKEW low ({skew}) - minimal tail hedging")
        else:            parts.append(f"SKEW normal ({skew})")
    return " | ".join(parts) if parts else ""


# ── Main backfill ─────────────────────────────────────────────────────────────

def main():
    print("=" * 56)
    print("  Layer 1 Backfill")
    print("=" * 56)

    # ── Load existing CSV ─────────────────────────────────────────────────────
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        original_fieldnames = reader.fieldnames or []

    print(f"Loaded {len(rows)} rows from {CSV_PATH}")

    # Check how many already have Layer 1 data
    already_filled = sum(1 for r in rows if r.get("spy_200ma") not in (None, ""))
    print(f"Rows already with Layer 1 data: {already_filled}")
    if already_filled == len(rows):
        print("All rows already filled. Nothing to do.")
        return

    # ── Fetch all historical data up front (one API call per symbol) ──────────
    print("\nFetching SPY history (2y)...")
    spy_pairs = yf_fetch("SPY", period="2y")
    spy_map   = build_daily_map(spy_pairs)
    # Build an ordered list of (date, close) for rolling calculations
    spy_sorted = sorted(spy_pairs, key=lambda x: x[0])
    spy_dates  = [ts_to_date(t) for t, _ in spy_sorted]
    spy_closes = [c for _, c in spy_sorted]
    print(f"  SPY: {len(spy_closes)} trading days")

    print("Fetching VIX history (2y)...")
    vix_pairs = yf_fetch("%5EVIX", period="2y")
    vix_map   = build_daily_map(vix_pairs)
    print(f"  VIX: {len(vix_map)} days")

    print("Fetching VIX3M history (2y)...")
    try:
        vix3m_pairs = yf_fetch("%5EVIX3M", period="2y")
        vix3m_map   = build_daily_map(vix3m_pairs)
        print(f"  VIX3M: {len(vix3m_map)} days")
    except Exception as e:
        vix3m_map = {}
        print(f"  VIX3M FAILED: {e}")

    print("Fetching SKEW history (2y)...")
    try:
        skew_pairs = yf_fetch("%5ESKEW", period="2y")
        skew_map   = build_daily_map(skew_pairs)
        print(f"  SKEW: {len(skew_map)} days")
    except Exception as e:
        skew_map = {}
        print(f"  SKEW FAILED: {e}")

    # ── Build lookup: date -> index in spy_sorted for rolling calcs ───────────
    spy_date_index = {d: i for i, d in enumerate(spy_dates)}

    # ── Backfill each row ─────────────────────────────────────────────────────
    print(f"\nBackfilling {len(rows)} rows...")
    filled = 0

    for row in rows:
        d = row.get("date", "").strip()

        # Skip if already filled
        if row.get("spy_200ma") not in (None, ""):
            continue

        # ── SPY 200MA + RSI using all closes UP TO this date ─────────────────
        spy_200ma = None
        spy_above = None
        rsi       = None

        if d in spy_date_index:
            idx = spy_date_index[d]
            closes_up_to = spy_closes[: idx + 1]
            spot = closes_up_to[-1]
            if len(closes_up_to) >= 1:
                spy_200ma = calc_200ma(closes_up_to)
                spy_above = spot > spy_200ma
            if len(closes_up_to) >= 15:
                rsi = calc_rsi14(closes_up_to)
        else:
            print(f"  WARNING: {d} not found in SPY history (weekend/holiday row?)")

        # ── VIX term structure ────────────────────────────────────────────────
        vix_val   = vix_map.get(d)
        vix3m_val = vix3m_map.get(d)
        if vix_val is not None and vix3m_val is not None:
            spread    = round(float(vix3m_val) - float(vix_val), 2)
            structure = "contango" if spread > 0 else "backwardation"
        else:
            spread    = None
            structure = None

        # ── SKEW ──────────────────────────────────────────────────────────────
        skew = skew_map.get(d)
        if skew is not None:
            skew = round(float(skew), 2)

        # ── L1 context sentence ───────────────────────────────────────────────
        l1_ctx = compute_l1_context(spy_above, rsi, structure, skew, vix_val)

        # ── Write back into row ───────────────────────────────────────────────
        row["spy_200ma"]          = spy_200ma
        row["spy_above_200ma"]    = spy_above
        row["spy_rsi_14"]         = rsi
        row["vix_3m"]             = round(float(vix3m_val), 2) if vix3m_val else None
        row["vix_term_spread"]    = spread
        row["vix_term_structure"] = structure
        row["skew_index"]         = skew
        row["l1_context"]         = l1_ctx
        filled += 1

    print(f"Filled {filled} rows.")

    # ── Write updated CSV ─────────────────────────────────────────────────────
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=ALL_COLS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nDone. {CSV_PATH} updated with Layer 1 columns.")
    print("Commit and push to deploy.")


if __name__ == "__main__":
    main()
