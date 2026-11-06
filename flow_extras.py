"""
flow_extras.py — "where is the big money moving" data layer.

Collects cross-asset series the core pipeline doesn't, chosen because each
one says something about INSTITUTIONAL positioning or stress that SPY/VIX/GEX
alone can't:

  Leadership / breadth
    SMH  semiconductors: the epicenter of the 2026-11-05 selloff, and AI-capex leadership
    RSP  equal-weight S&P: RSP/SPY falling = rally carried by a few megacaps (narrow)
    IWM  small caps: risk appetite beyond megacaps
    QQQ  Nasdaq-100: QQQ lagging SPY led the Nov-5 drop by ~2 weeks
  Credit quality (whales sell credit before equities)
    HYG/LQD  junk vs investment grade: risk appetite inside credit
    HYG/IEF  junk vs Treasuries: cleaner spread proxy than the HYG level
    KRE      regional banks: credit-plumbing stress (2023 SVB-style)
  Rotation (risk-on vs defensive)
    XLU+XLP vs XLY+XLK  defensives vs cyclicals/tech
  Volatility of volatility / rates
    ^VVIX  vol of VIX: VVIX falling while VIX stays high = fear exhausting
    ^MOVE  Treasury volatility: bond-market stress often leads equity stress
    ^VIX3M 3-month VIX (for VIX/VIX3M term structure history)
  Global / macro plumbing
    JPY=X    USD/JPY: a sharp yen rally = carry-trade unwind (Aug 2024)
    HG=F/GC=F copper/gold: growth vs fear; tracks real yields
    BTC-USD  trades 24/7: the weekend risk-appetite read before Monday's open
  Footprints
    SPY volume vs its 20-day average: capitulation/accumulation days

Output: flow_history.csv (repo root), one row per date, raw closes + derived
ratios. Idempotent: re-running a date replaces that date's row.

  python flow_extras.py             # daily: fetch the last ~1 month and upsert
  python flow_extras.py --backfill  # full history (chunked, from 1999)

Uses the same Yahoo chart API and chunked-fetch approach as
deep_history_backtest.py (range=max silently downsamples to monthly bars).
Never raises on a single ticker failure: missing tickers are left blank.
"""

import csv
import os
import sys
import time
from datetime import datetime, timezone

import requests

OUT = "flow_history.csv"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json,text/html,*/*",
}
TICKERS = {
    "spy": "SPY", "qqq": "QQQ", "smh": "SMH", "rsp": "RSP", "iwm": "IWM",
    "hyg": "HYG", "lqd": "LQD", "ief": "IEF", "kre": "KRE",
    "xlu": "XLU", "xlp": "XLP", "xly": "XLY", "xlk": "XLK",
    "vix": "^VIX", "vix3m": "^VIX3M", "vvix": "^VVIX", "move": "^MOVE",
    "usdjpy": "JPY=X", "copper": "HG=F", "gold": "GC=F", "btc": "BTC-USD",
}
FETCH_START_YEAR = 1999
CHUNK_YEARS = 3


def fetch(ticker, period1, period2, want_volume=False):
    """{date: (close, volume)} for one window. Empty dict on failure."""
    for base in ("query1", "query2"):
        try:
            url = (f"https://{base}.finance.yahoo.com/v8/finance/chart/{ticker}"
                   f"?interval=1d&period1={period1}&period2={period2}")
            r = requests.get(url, headers=HEADERS, timeout=20)
            res = (r.json().get("chart") or {}).get("result")
            if not res:
                continue
            ts = res[0].get("timestamp") or []
            q = res[0]["indicators"]["quote"][0]
            closes, vols = q.get("close") or [], q.get("volume") or []
            out = {}
            for i, t in enumerate(ts):
                c = closes[i] if i < len(closes) else None
                if c is None:
                    continue
                d = datetime.fromtimestamp(t, tz=timezone.utc).date().isoformat()
                v = vols[i] if want_volume and i < len(vols) else None
                out[d] = (round(c, 4), v)
            return out
        except Exception:
            continue
    return {}


def fetch_series(ticker, backfill, want_volume=False):
    now = int(time.time())
    if not backfill:
        return fetch(ticker, now - 40 * 86400, now, want_volume)
    merged, p1 = {}, int(datetime(FETCH_START_YEAR, 1, 1).timestamp())
    step = CHUNK_YEARS * 365 * 86400
    while p1 < now:
        p2 = min(p1 + step, now)
        merged.update(fetch(ticker, p1, p2, want_volume))
        p1 = p2
        time.sleep(0.15)
    return merged


def ratio(a, b):
    return round(a / b, 5) if a and b else None


def derive(row):
    g = lambda k: row.get(k) if row.get(k) not in ("", None) else None
    f = lambda k: float(g(k)) if g(k) is not None else None
    row["qqq_spy"] = ratio(f("qqq"), f("spy"))
    row["smh_spy"] = ratio(f("smh"), f("spy"))
    row["rsp_spy"] = ratio(f("rsp"), f("spy"))
    row["iwm_spy"] = ratio(f("iwm"), f("spy"))
    row["hyg_lqd"] = ratio(f("hyg"), f("lqd"))
    row["hyg_ief"] = ratio(f("hyg"), f("ief"))
    d = (f("xlu") or 0) + (f("xlp") or 0)
    c = (f("xly") or 0) + (f("xlk") or 0)
    row["defensive_cyclical"] = ratio(d, c) if all(f(k) for k in ("xlu", "xlp", "xly", "xlk")) else None
    row["copper_gold"] = ratio(f("copper"), f("gold"))
    row["vix_vix3m"] = ratio(f("vix"), f("vix3m"))
    return row


def main():
    backfill = "--backfill" in sys.argv
    data = {}
    for col, tk in TICKERS.items():
        s = fetch_series(tk, backfill, want_volume=(col == "spy"))
        print(f"  {tk:8s} {len(s):5d} days")
        for d, (c, v) in s.items():
            data.setdefault(d, {})[col] = c
            if col == "spy" and v:
                data[d]["spy_volume"] = v

    existing = {}
    if os.path.exists(OUT):
        with open(OUT, newline="", encoding="utf-8") as fh:
            existing = {r["date"]: r for r in csv.DictReader(fh)}

    # Upsert: fresh values replace old ones per field; untouched fields kept.
    # Only dates where SPY traded become rows (drops weekend BTC/FX-only dates,
    # since BTC's weekend move is already captured by Monday's row).
    for d, vals in data.items():
        if "spy" not in vals:
            continue
        row = existing.get(d, {"date": d})
        row.update({k: v for k, v in vals.items() if v is not None})
        existing[d] = row

    rows = [derive(existing[d]) for d in sorted(existing)]
    # SPY volume vs trailing 20-day average (excludes today).
    for i, r in enumerate(rows):
        try:
            v = float(r.get("spy_volume") or "")
            prev = [float(x["spy_volume"]) for x in rows[max(0, i - 20):i] if x.get("spy_volume")]
            r["spy_vol_ratio20"] = round(v / (sum(prev) / len(prev)), 3) if len(prev) >= 10 else None
        except ValueError:
            r["spy_vol_ratio20"] = None

    fields = ["date"] + list(TICKERS) + ["spy_volume", "qqq_spy", "smh_spy", "rsp_spy", "iwm_spy",
              "hyg_lqd", "hyg_ief", "defensive_cyclical", "copper_gold", "vix_vix3m", "spy_vol_ratio20"]
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print(f"Wrote {OUT}: {len(rows)} rows, {rows[0]['date'] if rows else '-'} -> {rows[-1]['date'] if rows else '-'}")
    if not rows or rows[-1].get("spy") in (None, ""):
        sys.exit(1)


if __name__ == "__main__":
    main()
