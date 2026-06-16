"""
backfill_mag7.py
────────────────
Backfills mag7_log.csv with historical data from 2026-03-30 onwards.
Uses Yahoo Finance price history for RSI/200MA.
Options data (P/C, IV) is not historically available so those columns
are left empty — they populate from today's live run forward.
GEX is also live-only — left empty for historical rows.
"""

import csv
import os
import requests
from datetime import datetime, date

OUTPUT_CSV = "mag7_log.csv"
TICKERS = ["AAPL", "MSFT", "NVDA", "GOOGL", "META", "AMZN", "TSLA"]
START_DATE = "2026-03-30"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
}

CSV_HEADERS = [
    "date", "ticker",
    "spot_price", "rsi_14", "ma_200", "above_200ma",
    "rsi_pct", "iv_pct", "pc_pct",
    "iv_current", "pc_ratio",
    "gex_b", "gex_regime",
    "opportunity_score", "signal", "signal_detail",
]


def fetch_history(ticker):
    for base in ["query1", "query2"]:
        try:
            url = f"https://{base}.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=2y"
            r = requests.get(url, headers=HEADERS, timeout=15)
            data = r.json()
            result = data.get("chart", {}).get("result")
            if not result:
                continue
            timestamps = result[0].get("timestamp", result[0].get("timestamps", []))
            closes = result[0]["indicators"]["quote"][0]["close"]
            pairs = [(datetime.utcfromtimestamp(t).strftime("%Y-%m-%d"), c)
                     for t, c in zip(timestamps, closes) if c is not None]
            pairs.sort(key=lambda x: x[0])
            print(f"  {ticker}: {len(pairs)} days from {base}")
            return pairs
        except Exception as e:
            print(f"  {ticker} {base} failed: {e}")
    return []


def calc_rsi(closes, period=14):
    if len(closes) < period + 1:
        return None
    deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
    gains  = [max(d, 0) for d in deltas[-period:]]
    losses = [abs(min(d, 0)) for d in deltas[-period:]]
    ag = sum(gains) / period
    al = sum(losses) / period
    if al == 0: return 100.0
    return round(100 - (100 / (1 + ag / al)), 2)


def calc_ma(closes, window=200):
    w = min(window, len(closes))
    return round(sum(closes[-w:]) / w, 2)


def compute_percentile(value, series):
    if not series or value is None: return None
    valid = [x for x in series if x is not None]
    if not valid: return None
    below = sum(1 for x in valid if x <= value)
    return round((below / len(valid)) * 100, 1)


def compute_score_price_only(rsi_pct, above_200ma, rsi_raw):
    """
    Simplified score using only price-based data (no options/GEX for historical).
    Max 5 pts — leaves room for options/GEX to add the other 5 on live days.
    """
    score = 0
    detail = []

    if rsi_pct is not None:
        if rsi_pct <= 10:
            score += 3
            detail.append(f"RSI extremely oversold vs own history (bottom {rsi_pct:.0f}%)")
        elif rsi_pct <= 20:
            score += 2
            detail.append(f"RSI very oversold vs own history (bottom {rsi_pct:.0f}%)")
        elif rsi_pct <= 35:
            score += 1
            detail.append(f"RSI oversold vs own history (bottom {rsi_pct:.0f}%)")
    elif rsi_raw is not None:
        if rsi_raw < 30:   score += 3; detail.append(f"RSI absolute oversold ({rsi_raw})")
        elif rsi_raw < 40: score += 2; detail.append(f"RSI weak ({rsi_raw})")
        elif rsi_raw < 50: score += 1; detail.append(f"RSI below midline ({rsi_raw})")

    if above_200ma is True:
        score += 1
        detail.append("Above 200MA — uptrend intact")
    elif above_200ma is False:
        detail.append("Below 200MA — downtrend, scale in slowly")

    # Partial score label (price-only)
    if score >= 4:
        signal = "WATCH — price-based setup (options data from today forward)"
    elif score >= 2:
        signal = "NEUTRAL — mild dip in own history"
    else:
        signal = "NO SIGNAL — not oversold vs own history"

    return min(5, score), signal, " | ".join(detail) + " [price-based only]"


def get_existing_dates():
    existing = set()
    if not os.path.isfile(OUTPUT_CSV):
        return existing
    try:
        with open(OUTPUT_CSV, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("date") and row.get("ticker"):
                    existing.add((row["date"], row["ticker"]))
    except:
        pass
    return existing


def main():
    print("=" * 60)
    print("  Mag 7 Historical Backfill")
    print("=" * 60)

    existing = get_existing_dates()
    print(f"Existing rows: {len(existing)}")

    all_rows = []

    for ticker in TICKERS:
        print(f"\nFetching {ticker}...")
        pairs = fetch_history(ticker)
        if not pairs:
            print(f"  No data for {ticker}")
            continue

        dates  = [p[0] for p in pairs]
        closes = [p[1] for p in pairs]
        date_idx = {d: i for i, d in enumerate(dates)}

        # Only process dates from START_DATE onwards
        target_dates = [d for d in dates if d >= START_DATE]
        print(f"  Processing {len(target_dates)} dates from {START_DATE}")

        for d in target_dates:
            if (d, ticker) in existing:
                continue

            idx = date_idx[d]
            closes_up_to = closes[:idx + 1]

            spot  = closes_up_to[-1]
            rsi   = calc_rsi(closes_up_to)
            ma200 = calc_ma(closes_up_to, 200)
            above = spot > ma200 if ma200 else None

            # RSI percentile using all history UP TO this date
            rsi_pct = compute_percentile(rsi, closes_up_to) if rsi else None
            # Better: compute RSI for each day and rank
            # Build RSI series up to this point
            rsi_series = []
            for j in range(15, idx + 1):
                r = calc_rsi(closes[:j + 1])
                if r: rsi_series.append(r)
            rsi_pct = compute_percentile(rsi, rsi_series) if len(rsi_series) >= 5 else None

            score, signal, detail = compute_score_price_only(rsi_pct, above, rsi)

            all_rows.append({
                "date":              d,
                "ticker":            ticker,
                "spot_price":        round(spot, 2),
                "rsi_14":            rsi,
                "ma_200":            ma200,
                "above_200ma":       above,
                "rsi_pct":           rsi_pct,
                "iv_pct":            "",
                "pc_pct":            "",
                "iv_current":        "",
                "pc_ratio":          "",
                "gex_b":             "",
                "gex_regime":        "",
                "opportunity_score": score,
                "signal":            signal,
                "signal_detail":     detail,
            })

    print(f"\nNew rows to write: {len(all_rows)}")

    if not all_rows:
        print("Nothing to write.")
        return

    # Sort by date then ticker
    all_rows.sort(key=lambda x: (x["date"], x["ticker"]))

    # Load existing rows
    existing_rows = []
    if os.path.isfile(OUTPUT_CSV):
        with open(OUTPUT_CSV, newline="", encoding="utf-8") as f:
            existing_rows = list(csv.DictReader(f))

    all_rows_final = existing_rows + all_rows
    all_rows_final.sort(key=lambda x: (x.get("date",""), x.get("ticker","")))

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(all_rows_final)

    print(f"Done. {OUTPUT_CSV} has {len(all_rows_final)} total rows.")


if __name__ == "__main__":
    main()
