"""
sector_rotation.py
────────────────────
Answers "where is money flowing to/from" across the 11 GICS sectors and a
handful of cross-asset proxies, using the classic relative-strength /
rotation-quadrant method (the same idea behind a Relative Rotation Graph):

  1. For each sector/asset, compute its RELATIVE STRENGTH vs SPY over a
     ~1-month (21 trading day) window: RS = (1 + own_return) / (1 + SPY's
     return) * 100. RS > 100 means it beat SPY over that window (money
     flowing toward it); RS < 100 means it lagged (money flowing away).
  2. Compute the same RS ratio as of 5 trading days ago, and take the
     difference — RS_MOMENTUM. This tells you the DIRECTION of change,
     not just the current level.
  3. Combine level + momentum into one of four quadrants:
       LEADING    (RS > 100, momentum > 0)  — outperforming AND still
                                               accelerating: money already
                                               in, still flowing in.
       WEAKENING  (RS > 100, momentum <= 0) — still outperforming, but
                                               losing steam: money starting
                                               to leave.
       LAGGING    (RS <= 100, momentum <= 0)— underperforming and still
                                               losing ground: money still
                                               flowing out.
       IMPROVING  (RS <= 100, momentum > 0) — underperforming, but gaining
                                               ground: money starting to
                                               rotate IN.
     IMPROVING and LEADING are where money is flowing TOWARD; WEAKENING and
     LAGGING are where it's flowing AWAY FROM.

This needs no accumulated history to be meaningful — the "5 trading days
ago" comparison point comes from the same 1-year price pull used for
"today," so day one already produces a real momentum read (unlike the GEX
scanner's percentile columns, which needed weeks to fill in).

Universe: the 11 SPDR sector ETFs (a standard proxy for GICS sectors) plus
5 cross-asset proxies (long treasuries, gold, the dollar, high-yield
credit, emerging markets) — all benchmarked against SPY, so "money flowing
into gold" and "money flowing into financials" are read on the same scale.

Known limitation: trading-day alignment between tickers is done by index
position, not by matching actual calendar dates. All of these are US-listed
and share the same trading calendar, so misalignment should be rare, but a
single missing bar on one ticker (a data gap) could shift things off by one
day. Good enough for a directional read; not something to bet on down to
the day if two numbers are extremely close.

Output:
  - sector_rotation_log.csv    — full daily history, one row per sector/
                                  asset per day (collapses same-day stale
                                  rows on rerun, same pattern as the other
                                  daily scripts in this repo).
  - sector_rotation_top.json   — today's snapshot: every sector/asset
                                  ranked by RS_momentum, grouped by quadrant.
"""

import csv
import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

LOG_CSV = "sector_rotation_log.csv"
TOP_JSON = "sector_rotation_top.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json,text/html,*/*",
    "Accept-Language": "en-US,en;q=0.5",
}

BENCHMARK = "SPY"

UNIVERSE = {
    # 11 GICS sectors via SPDR select sector ETFs
    "XLK": "Technology", "XLF": "Financials", "XLE": "Energy",
    "XLV": "Healthcare", "XLY": "Consumer Discretionary", "XLP": "Consumer Staples",
    "XLI": "Industrials", "XLB": "Materials", "XLU": "Utilities",
    "XLRE": "Real Estate", "XLC": "Communication Services",
    # Cross-asset proxies
    "TLT": "Long-Term US Treasuries (20yr+)", "GLD": "Gold",
    "UUP": "US Dollar Index", "HYG": "High-Yield Credit", "EEM": "Emerging Market Equities",
}

RS_WINDOW_DAYS = 21     # ~1 trading month, the primary relative-strength window
MOMENTUM_LAG_DAYS = 5   # compare RS now vs RS this many trading days ago
SHORT_WINDOW_DAYS = 5   # extra context: raw 1-week return
LONG_WINDOW_DAYS = 63   # extra context: raw ~3-month return

LOG_CSV_HEADERS = [
    "date", "ticker", "label",
    "return_5d", "return_21d", "return_63d",
    "rs_now", "rs_prior", "rs_momentum", "quadrant",
]


def yf_fetch_history(ticker, period="1y"):
    """Same free Yahoo chart-endpoint pattern used elsewhere in this repo."""
    for base in ["query1", "query2"]:
        try:
            url = f"https://{base}.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range={period}"
            r = requests.get(url, headers=HEADERS, timeout=15)
            data = r.json()
            result = data.get("chart", {}).get("result")
            if not result:
                continue
            closes = result[0]["indicators"]["quote"][0]["close"]
            closes = [c for c in closes if c is not None]
            if closes:
                return closes
        except Exception:
            continue
    return []


def trailing_return(closes, days, offset=0):
    """% return over `days` trading days, ending `offset` trading days ago."""
    end_idx = len(closes) - 1 - offset
    start_idx = end_idx - days
    if start_idx < 0 or end_idx < 0 or end_idx >= len(closes):
        return None
    start, end = closes[start_idx], closes[end_idx]
    if start == 0:
        return None
    return (end - start) / start * 100


def rs_ratio(ticker_closes, bench_closes, days, offset=0):
    """Relative strength: (1 + own_return) / (1 + benchmark_return) * 100,
    both measured over the same `days`-day window ending `offset` days ago."""
    t_ret = trailing_return(ticker_closes, days, offset)
    b_ret = trailing_return(bench_closes, days, offset)
    if t_ret is None or b_ret is None:
        return None
    return (1 + t_ret / 100) / (1 + b_ret / 100) * 100


def classify_quadrant(rs_now, rs_momentum):
    if rs_now is None or rs_momentum is None:
        return "unknown"
    if rs_now > 100 and rs_momentum > 0:
        return "LEADING"
    if rs_now > 100 and rs_momentum <= 0:
        return "WEAKENING"
    if rs_now <= 100 and rs_momentum <= 0:
        return "LAGGING"
    return "IMPROVING"


def save_log_rows(rows):
    """Same collapse-stale-same-day-rows pattern as market_scanner.py."""
    today = rows[0]["date"] if rows else None
    existing_rows = []
    if os.path.isfile(LOG_CSV):
        with open(LOG_CSV, newline="", encoding="utf-8") as f:
            existing_rows = list(csv.DictReader(f))
    other_rows = [r for r in existing_rows if r.get("date") != today]
    with open(LOG_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=LOG_CSV_HEADERS, extrasaction="ignore")
        w.writeheader()
        w.writerows(other_rows)
        w.writerows(rows)
    print(f"  Saved {len(rows)} rows for {today} ({len(existing_rows) - len(other_rows)} stale rows for that date replaced)")


def main():
    today = datetime.now(ZoneInfo("America/New_York")).date().strftime("%Y-%m-%d")
    print(f"Sector/asset rotation scan — {today}")

    print(f"Fetching benchmark ({BENCHMARK})...")
    bench_closes = yf_fetch_history(BENCHMARK)
    if not bench_closes:
        print(f"Could not fetch benchmark {BENCHMARK}, aborting.")
        return

    rows = []
    for tk, label in UNIVERSE.items():
        closes = yf_fetch_history(tk)
        if not closes:
            print(f"  {tk}: no data, skipping")
            continue

        r5 = trailing_return(closes, SHORT_WINDOW_DAYS)
        r21 = trailing_return(closes, RS_WINDOW_DAYS)
        r63 = trailing_return(closes, LONG_WINDOW_DAYS)
        rs_now = rs_ratio(closes, bench_closes, RS_WINDOW_DAYS, offset=0)
        rs_prior = rs_ratio(closes, bench_closes, RS_WINDOW_DAYS, offset=MOMENTUM_LAG_DAYS)
        rs_momentum = (rs_now - rs_prior) if (rs_now is not None and rs_prior is not None) else None
        quadrant = classify_quadrant(rs_now, rs_momentum)

        rows.append({
            "date": today, "ticker": tk, "label": label,
            "return_5d": round(r5, 2) if r5 is not None else None,
            "return_21d": round(r21, 2) if r21 is not None else None,
            "return_63d": round(r63, 2) if r63 is not None else None,
            "rs_now": round(rs_now, 2) if rs_now is not None else None,
            "rs_prior": round(rs_prior, 2) if rs_prior is not None else None,
            "rs_momentum": round(rs_momentum, 2) if rs_momentum is not None else None,
            "quadrant": quadrant,
        })
        time.sleep(0.3)

    if not rows:
        print("No rows produced, aborting.")
        return

    save_log_rows(rows)

    ranked = sorted(
        [r for r in rows if r["rs_momentum"] is not None],
        key=lambda r: r["rs_momentum"], reverse=True,
    )
    by_quadrant = {"LEADING": [], "IMPROVING": [], "WEAKENING": [], "LAGGING": [], "unknown": []}
    for r in ranked:
        by_quadrant.setdefault(r["quadrant"], []).append(r["ticker"])

    import json
    report = {
        "date": today,
        "benchmark": BENCHMARK,
        "rs_window_days": RS_WINDOW_DAYS,
        "momentum_lag_days": MOMENTUM_LAG_DAYS,
        "note": (
            "LEADING/IMPROVING = money flowing TOWARD (outperforming SPY and gaining, "
            "or still lagging but starting to gain). WEAKENING/LAGGING = money flowing "
            "AWAY FROM. Ranked by rs_momentum, most inflow-like first."
        ),
        "ranked": [
            {"ticker": r["ticker"], "label": r["label"], "quadrant": r["quadrant"],
             "rs_now": r["rs_now"], "rs_momentum": r["rs_momentum"],
             "return_21d": r["return_21d"]}
            for r in ranked
        ],
        "by_quadrant": by_quadrant,
    }
    with open(TOP_JSON, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"Wrote {TOP_JSON} — {len(ranked)} sectors/assets classified")


if __name__ == "__main__":
    main()
