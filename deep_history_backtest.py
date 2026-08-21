"""
deep_history_backtest.py
──────────────────────────
Backtests the macro regime system (regime_analyzer.py's scoring functions,
imported directly here — NOT reimplemented, so this tests the actual live
logic) against real SPY forward returns across as much free history as each
underlying ticker allows, specifically to see how it behaved during real
bear markets and crashes — something the live 98-day dataset (one
continuous bull run) has never been able to show.

WHY THIS IS POSSIBLE NOW, UNLIKE THE GEX-BASED HALF OF THE SIGNAL:
Every scoring function in regime_analyzer.py (score_credit, score_volatility,
score_flow, score_growth, score_skew, compute_composite, get_flow_regime)
uses FIXED price/level thresholds (e.g. "HYG > 82 = healthy"), not
percentiles computed from accumulated own-history. That means they can be
computed for ANY historical date the raw ticker data covers, with no
bootstrap period needed — unlike market_scanner.py's rsi_pct/pc_pct, which
genuinely needed weeks of accumulated history to mean anything.

THE ONE THING THIS STILL CANNOT INCLUDE: dealer gamma exposure (GEX). No
free historical source exists for it (InsiderFinance-style feeds are
live-snapshot only), so get_regime_signal() is called here with gex=None.
Its STRONG_BUY and BUY_WATCH branches both require gex not to be None, so
neither will ever appear in this backtest — expect only STRONG_HOLD / HOLD
/ CAUTION / DEFENSIVE / CRISIS. get_flow_regime() doesn't need gex at all,
so it's the more complete signal here and the primary one this script
reports on.

DATA WINDOW PER TICKER (free Yahoo history, actual coverage, not a promise):
SPY/^VIX back to the 1990s; GLD from Nov 2004; TLT from Jul 2002; HYG from
Apr 2007; USO from Apr 2006; EEM from Apr 2003; CPER (copper) only from Nov
2011 — the one real gap, meaning score_growth runs EEM-only (still real,
just less complete) for anything before Nov 2011. ^VIX9D and ^VIX3M are
also newer (~2011) and degrade gracefully the same way (their modifiers
only apply "if not None"). DXY tries "DX-Y.NYB" first (long index history)
before falling back to UUP (ETF, since 2007) scaled by 3.57x — same
fallback gex_tracker.py already uses for the live daily run.

This means 2008's crash (Sept-Nov 2008) IS coverable (every ticker except
copper/VIX9D/VIX3M already existed), and both the 2020 COVID crash and the
2022 bear market are fully coverable — PROVIDED the fetch actually returns
daily bars. Yahoo's chart API silently downsamples interval=1d to a coarser
bar size (observed: monthly) once a single request's range gets long
enough, with no error — so yf_fetch_dated() below fetches in explicit
multi-year chunks (period1/period2, not range=max) specifically to avoid
that trap. A first run that used range=max hit this exact failure: SPY
came back as ~204 monthly bars instead of ~4,300+ daily ones, which
silently collapsed the crash-window analysis (2020 COVID down to 1 sampled
day; 2008 GFC showing zero days, since monthly-bar coverage didn't even
reach that far back). If a future edit ever reintroduces range=max for a
long window, re-check total_days in the summary against the expected
trading-day count for the date range — a suspiciously low number is this
same bug recurring.

Output:
  - deep_history_backtest_log.csv     — every trading day: raw inputs,
                                         composite_score, flow_regime,
                                         regime_signal, forward SPY returns.
  - deep_history_backtest_summary.json — aggregate hit-rate/avg-return
                                         stats by composite-score bucket and
                                         by flow_regime label, PLUS a
                                         specific breakdown of what the
                                         system was actually saying during
                                         the 2008, 2020, and 2022 windows.

This is a ONE-TIME (or occasional re-run) analysis, not a growing daily
log like the other trackers in this repo — run it via workflow_dispatch
when you want a refreshed view, not on a schedule.
"""

import csv
import json
import time
from datetime import datetime

import requests

from regime_analyzer import (
    score_credit, score_volatility, score_flow, score_growth, score_skew,
    compute_composite, get_flow_regime, get_regime_signal,
)

LOG_CSV = "deep_history_backtest_log.csv"
SUMMARY_JSON = "deep_history_backtest_summary.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json,text/html,*/*",
    "Accept-Language": "en-US,en;q=0.5",
}

HORIZONS = [5, 10, 20]

# Named historical windows to specifically report on — the whole point of
# this script. Dates are the rough crash windows, not exact bottoms/tops.
CRASH_WINDOWS = {
    "2008_GFC": ("2008-09-01", "2009-03-09"),
    "2020_COVID": ("2020-02-19", "2020-03-23"),
    "2022_BEAR": ("2022-01-03", "2022-10-13"),
}

COMPOSITE_BUCKETS = [
    ("strong_bull (+6 to +8)", 6, 8.01),
    ("mild_bull (+3 to +5)", 3, 6),
    ("neutral (0 to +2)", 0, 3),
    ("stress (-1 to -3)", -3, 0),
    ("crisis (-4 to -8)", -8, -3),
]


CHUNK_YEARS = 3          # fetch this many years per request
FETCH_START_YEAR = 1995  # oldest year to attempt (SPY/^VIX predate this; other
                          # tickers just return empty chunks before their own
                          # inception, which is harmless)


def yf_fetch_dated(ticker):
    """(date_str, close) pairs, TRUE DAILY granularity, covering as much
    history as Yahoo has for this ticker.

    IMPORTANT: a single request with interval=1d&range=max is NOT safe for
    long-history tickers — Yahoo's chart API silently substitutes a coarser
    bar size (observed: ~monthly) once the requested range would produce
    "too many" daily points, with NO error returned. A first real run of
    this script hit exactly that: SPY came back as ~204 monthly bars over
    17 years instead of ~4,300 daily bars, which silently collapsed the
    2008/2020/2022 crash-window analysis (2020 COVID showed only 1 sampled
    day; 2008 GFC showed none at all, since coverage didn't even reach that
    far back). Fetching in explicit period1/period2 chunks of a few years
    each forces Yahoo to return real daily bars for every chunk, and the
    chunks are merged by date afterward."""
    all_pairs = {}
    now = int(time.time())
    chunk_seconds = CHUNK_YEARS * 365 * 24 * 3600
    p1 = int(datetime(FETCH_START_YEAR, 1, 1).timestamp())
    while p1 < now:
        p2 = min(p1 + chunk_seconds, now)
        for base in ["query1", "query2"]:
            try:
                url = (
                    f"https://{base}.finance.yahoo.com/v8/finance/chart/{ticker}"
                    f"?interval=1d&period1={p1}&period2={p2}"
                )
                r = requests.get(url, headers=HEADERS, timeout=20)
                data = r.json()
                result = data.get("chart", {}).get("result")
                if not result:
                    continue
                timestamps = result[0].get("timestamp") or []
                closes = result[0]["indicators"]["quote"][0]["close"]
                for ts, c in zip(timestamps, closes):
                    if c is not None:
                        all_pairs[datetime.utcfromtimestamp(ts).date().isoformat()] = c
                break  # this chunk succeeded (even if empty, e.g. pre-inception) — move on
            except Exception:
                continue
        p1 = p2
        time.sleep(0.15)
    return all_pairs


def calc_rsi(closes, period=14):
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        change = closes[i] - closes[i - 1]
        gains.append(max(change, 0))
        losses.append(max(-change, 0))
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


def fetch_dxy():
    """Prefer the long-history index ticker; fall back to UUP scaled the
    same way gex_tracker.py's live fetch already does."""
    for sym, is_uup in [("DX-Y.NYB", False), ("DX=F", False), ("UUP", True)]:
        pairs = yf_fetch_dated(sym)
        if pairs:
            if is_uup:
                return {d: round(v * 3.57, 2) for d, v in pairs.items()}
            return pairs
    return {}


def main():
    print("Fetching long history for every series (this can take a bit)...")
    series = {}
    series["spy"] = yf_fetch_dated("SPY")
    time.sleep(0.3)
    if not series["spy"]:
        print("Could not fetch SPY history, aborting — nothing to backtest against.")
        return
    for name, ticker in [
        ("vix", "%5EVIX"), ("vix9d", "%5EVIX9D"), ("vix3m", "%5EVIX3M"),
        ("gold", "GLD"), ("tlt", "TLT"), ("hyg", "HYG"),
        ("copper", "CPER"), ("oil", "USO"), ("eem", "EEM"), ("skew", "%5ESKEW"),
    ]:
        series[name] = yf_fetch_dated(ticker)
        print(f"  {name}: {len(series[name])} data points"
              f"{' (earliest ' + min(series[name]) + ')' if series[name] else ' — NONE, will degrade gracefully'}")
        time.sleep(0.3)
    series["dxy"] = fetch_dxy()
    print(f"  dxy: {len(series['dxy'])} data points"
          f"{' (earliest ' + min(series['dxy']) + ')' if series['dxy'] else ' — NONE'}")

    dates = sorted(series["spy"].keys())
    spy_closes = [series["spy"][d] for d in dates]
    print(f"\nSPY trading calendar: {len(dates)} days, {dates[0]} to {dates[-1]}")

    rows = []
    for i, d in enumerate(dates):
        if i < 200:
            continue  # need 200 days of SPY history for RSI/warmup before this date means much

        window = spy_closes[max(0, i - 250):i + 1]
        rsi = calc_rsi(window[-15:]) if len(window) >= 15 else None

        vix = series["vix"].get(d)
        vix9d = series["vix9d"].get(d)
        vix3m = series["vix3m"].get(d)
        term_spread = round(vix3m - vix, 2) if (vix3m is not None and vix is not None) else None
        dxy = series["dxy"].get(d)
        gold = series["gold"].get(d)
        tlt = series["tlt"].get(d)
        hyg = series["hyg"].get(d)
        copper = series["copper"].get(d)
        eem = series["eem"].get(d)
        skew = series["skew"].get(d)

        credit_s = score_credit(hyg)
        vol_s = score_volatility(vix, vix9d, term_spread)
        flow_s = score_flow(dxy, gold, tlt)
        growth_s = score_growth(copper, eem)
        skew_s = score_skew(skew, vix)
        composite = compute_composite(credit_s, vol_s, flow_s, growth_s, skew_s)
        flow_regime = get_flow_regime(composite, hyg, dxy, vix)
        # gex=None: no free historical dealer-positioning data exists — see
        # module docstring. STRONG_BUY/BUY_WATCH will never appear here.
        regime_signal = get_regime_signal(composite, hyg, None, rsi, skew, vix)

        forward_returns = {}
        for h in HORIZONS:
            target = i + h
            forward_returns[h] = (
                round((spy_closes[target] - spy_closes[i]) / spy_closes[i] * 100, 2)
                if target < len(spy_closes) and spy_closes[i] else None
            )

        rows.append({
            "date": d, "spy_close": spy_closes[i], "vix": vix, "hyg": hyg,
            "dxy": dxy, "gold": gold, "copper": copper, "eem": eem, "skew": skew,
            "composite_score": composite, "flow_regime": flow_regime,
            "regime_signal": regime_signal,
            "return_5d": forward_returns[5], "return_10d": forward_returns[10],
            "return_20d": forward_returns[20],
        })

    with open(LOG_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"\nWrote {LOG_CSV} — {len(rows)} days computed ({rows[0]['date']} to {rows[-1]['date']})")

    build_summary(rows)


def bucket_for(composite):
    for label, lo, hi in COMPOSITE_BUCKETS:
        if lo <= composite < hi:
            return label
    return "unbucketed"


def stats_for(rows_subset, horizon_key):
    returns = [r[horizon_key] for r in rows_subset if r[horizon_key] is not None]
    if not returns:
        return {"n": 0}
    n = len(returns)
    avg = round(sum(returns) / n, 2)
    hits = sum(1 for x in returns if x > 0)
    return {"n": n, "avg_return_pct": avg, "hit_rate_pct": round(hits / n * 100, 1)}


def build_summary(rows):
    by_bucket = {}
    for label, _, _ in COMPOSITE_BUCKETS:
        subset = [r for r in rows if bucket_for(r["composite_score"]) == label]
        by_bucket[label] = {f"{h}d": stats_for(subset, f"return_{h}d") for h in HORIZONS}

    by_flow_regime = {}
    for regime in sorted(set(r["flow_regime"] for r in rows)):
        subset = [r for r in rows if r["flow_regime"] == regime]
        by_flow_regime[regime] = {f"{h}d": stats_for(subset, f"return_{h}d") for h in HORIZONS}

    crash_analysis = {}
    for name, (start, end) in CRASH_WINDOWS.items():
        subset = [r for r in rows if start <= r["date"] <= end]
        if not subset:
            crash_analysis[name] = {"note": "no data available for this window with current history"}
            continue
        composites = [r["composite_score"] for r in subset]
        defensive_labels = {"recession_fear", "risk_off", "credit_crisis", "mild_risk_off", "cash_hoarding"}
        defensive_signal_labels = {"CAUTION", "DEFENSIVE", "CRISIS"}
        pct_flow_regime_defensive = round(
            sum(1 for r in subset if r["flow_regime"] in defensive_labels) / len(subset) * 100, 1
        )
        pct_regime_signal_defensive = round(
            sum(1 for r in subset if r["regime_signal"] in defensive_signal_labels) / len(subset) * 100, 1
        )
        crash_analysis[name] = {
            "trading_days": len(subset),
            "date_range_actual": f"{subset[0]['date']} to {subset[-1]['date']}",
            "avg_composite_score": round(sum(composites) / len(composites), 2),
            "min_composite_score": min(composites),
            "pct_days_flow_regime_flagged_defensive": pct_flow_regime_defensive,
            "pct_days_regime_signal_flagged_defensive": pct_regime_signal_defensive,
            "note": (
                "Higher pct_days figures = the system correctly recognized stress during "
                "this real crash more often. Lower figures mean it stayed bullish/neutral "
                "through part of a real crash — a genuine miss, not just a caveat."
            ),
        }

    summary = {
        "total_days": len(rows),
        "date_range": f"{rows[0]['date']} to {rows[-1]['date']}",
        "note": (
            "regime_signal here was computed with gex=None (no free historical dealer-"
            "positioning data exists) — STRONG_BUY/BUY_WATCH never appear. flow_regime "
            "doesn't depend on gex and is the more complete signal. Bucket boundaries "
            "match regime_analyzer.py's own documented composite_score ranges."
        ),
        "by_composite_bucket": by_bucket,
        "by_flow_regime": by_flow_regime,
        "crash_window_analysis": crash_analysis,
    }
    with open(SUMMARY_JSON, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(f"Wrote {SUMMARY_JSON}")


if __name__ == "__main__":
    main()
