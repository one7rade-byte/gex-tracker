"""
key_levels.py — Daily GEX key support/resistance zones for SPY and QQQ.

WHAT IT DOES
  Pulls every heavy call-gamma and put-gamma strike and turns them into the
  day's key zones:
    - Heavy CALL gamma strikes  -> resistance (dealers sell into rallies there)
    - Heavy PUT  gamma strikes  -> support    (dealers buy into dips there)
  Adjacent heavy strikes are merged into zones (a band, not a single line),
  ranked by total gamma, and tagged with InsiderFinance's named levels
  (call wall, put wall, zero gamma, peak GEX, max pain) when they fall inside.

WHY TWO SOURCES
  InsiderFinance (same page gex_tracker.py already scrapes) only server-renders
  its named levels plus a ~17-strike heatmap within ~1% of spot; the full
  strike ladder loads via JavaScript and can't be scraped with requests.
  So:
    - InsiderFinance -> named levels (call wall, put wall, zero gamma, etc.)
    - CBOE delayed-quotes JSON (free, no key) -> full option chain with
      per-contract gamma + open interest, used to compute GEX at EVERY strike
  The two are cross-checked: CBOE's #1 call/put strike vs InsiderFinance's
  call/put wall is written to the JSON so disagreement is visible, not hidden.

GEX FORMULA (standard dealer-gamma convention, $ per 1% move)
  strike_gex = gamma * open_interest * 100 * spot^2 * 0.01
  calls counted positive, puts negative (dealers assumed short puts/long calls
  hedging convention — the same sign convention InsiderFinance uses, where
  Net GEX = Call GEX + Put GEX).

OUTPUTS
  key_levels.json     — today's zones per ticker (overwritten each run)
  key_levels_log.csv  — every heavy strike, appended daily (idempotent per
                        date+ticker: re-runs replace that day's rows)
"""

import csv
import json
import os
import re
from datetime import datetime, date
from zoneinfo import ZoneInfo

import requests

from gex_tracker import fetch_gex, fetch_yahoo_price, HEADERS

# ── Config ────────────────────────────────────────────────────────────────────

TICKERS          = ["SPY", "QQQ"]
OUTPUT_JSON      = "key_levels.json"
OUTPUT_CSV       = "key_levels_log.csv"
ET               = ZoneInfo("America/New_York")

MAX_DTE          = 30     # only expirations within 30 days — near-term gamma
                          # is what actually drives intraday dealer hedging
STRIKE_RANGE_PCT = 6.0    # ignore strikes more than ±6% from spot
TOP_N_PER_SIDE   = 6      # heaviest call strikes / heaviest put strikes kept
MIN_SHARE_OF_MAX = 0.20   # a strike must carry >=20% of that side's biggest
                          # strike to count as "heavy" (drops filler strikes)
ZONE_MERGE_PCT   = 0.30   # heavy strikes within 0.30% of spot of each other
                          # merge into one zone (SPY ~$2.3, QQQ ~$1.8)

CBOE_URLS = [
    "https://cdn-api.cboe.com/api/global/delayed_quotes/options/{t}.json",
    "https://cdn.cboe.com/api/global/delayed_quotes/options/{t}.json",
]

OCC_RE = re.compile(r"^([A-Z]+)(\d{6})([CP])(\d{8})$")

CSV_HEADERS = [
    "date", "ticker", "spot", "side", "rank", "strike",
    "gex_m", "odte_gex_m", "open_interest", "pct_from_spot", "role",
]


# ── Fetch ─────────────────────────────────────────────────────────────────────

def fetch_cboe_chain(ticker):
    """Returns (options_list, underlying_price_or_None, timestamp_str)."""
    for tmpl in CBOE_URLS:
        url = tmpl.format(t=ticker)
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            if r.status_code != 200:
                print(f"  CBOE {ticker} {url}: HTTP {r.status_code}")
                continue
            payload = r.json()
            data = payload.get("data", {}) or {}
            options = data.get("options") or []
            price = data.get("current_price") or data.get("close")
            print(f"  CBOE {ticker}: {len(options)} contracts, "
                  f"underlying={price}, ts={payload.get('timestamp')}")
            if options:
                return options, (float(price) if price else None), payload.get("timestamp")
        except Exception as e:
            print(f"  CBOE {ticker} {url} failed: {e}")
    return [], None, None


# ── Compute ───────────────────────────────────────────────────────────────────

def strike_gex_table(options, ticker, spot, today):
    """
    Aggregates per-strike GEX across all expirations within MAX_DTE.
    Returns {strike: {"call": $, "put": $ (negative), "call_oi", "put_oi",
                      "call_0dte": $, "put_0dte": $}}
    """
    table = {}
    lo = spot * (1 - STRIKE_RANGE_PCT / 100)
    hi = spot * (1 + STRIKE_RANGE_PCT / 100)
    scale = 100 * spot * spot * 0.01

    for o in options:
        m = OCC_RE.match(str(o.get("option", "")))
        if not m:
            continue
        root, ymd, cp, strike_raw = m.groups()
        if root != ticker:
            continue          # skip any non-standard roots
        try:
            expiry = datetime.strptime(ymd, "%y%m%d").date()
        except ValueError:
            continue
        dte = (expiry - today).days
        if dte < 0 or dte > MAX_DTE:
            continue
        strike = int(strike_raw) / 1000.0
        if strike < lo or strike > hi:
            continue

        gamma = o.get("gamma") or 0.0
        oi    = o.get("open_interest") or 0.0
        try:
            gex = float(gamma) * float(oi) * scale
        except (TypeError, ValueError):
            continue

        row = table.setdefault(strike, {"call": 0.0, "put": 0.0,
                                        "call_oi": 0.0, "put_oi": 0.0,
                                        "call_0dte": 0.0, "put_0dte": 0.0})
        if cp == "C":
            row["call"] += gex
            row["call_oi"] += float(oi)
            if dte == 0:
                row["call_0dte"] += gex
        else:
            row["put"] -= gex
            row["put_oi"] += float(oi)
            if dte == 0:
                row["put_0dte"] -= gex
    return table


def heavy_strikes(table, side, spot):
    """Top heavy strikes for one side ('call' or 'put'), ranked by |GEX|."""
    rows = [(k, abs(v[side])) for k, v in table.items() if v[side] != 0]
    if not rows:
        return []
    biggest = max(g for _, g in rows)
    rows = [r for r in rows if r[1] >= biggest * MIN_SHARE_OF_MAX]
    rows.sort(key=lambda r: r[1], reverse=True)

    out = []
    for rank, (k, g) in enumerate(rows[:TOP_N_PER_SIDE], start=1):
        v = table[k]
        out.append({
            "rank": rank,
            "strike": k,
            "gex_m": round(v[side] / 1e6, 1),
            "odte_gex_m": round(v[f"{side}_0dte"] / 1e6, 1),
            "open_interest": int(v[f"{side}_oi"]),
            "pct_from_spot": round((k / spot - 1) * 100, 2),
            "role": role_for(k, spot, side),
        })
    return out


def role_for(strike, spot, side):
    """
    Call gamma above spot = resistance; put gamma below spot = support.
    When price has already moved through a heavy strike, it flips role:
    a heavy call strike BELOW spot acts as support, a heavy put strike ABOVE
    spot acts as resistance (classic broken-level flip).
    """
    if side == "call":
        return "resistance" if strike >= spot else "support (flipped call strike)"
    return "support" if strike <= spot else "resistance (flipped put strike)"


def build_zones(strikes, spot, if_levels):
    """Merges heavy strikes (both sides) within ZONE_MERGE_PCT into zones."""
    gap = spot * ZONE_MERGE_PCT / 100
    pts = sorted(strikes, key=lambda s: s["strike"])

    groups = []
    if pts:
        cur = [pts[0]]
        for s in pts[1:]:
            if s["strike"] - cur[-1]["strike"] <= gap:
                cur.append(s)
            else:
                groups.append(cur)
                cur = [s]
        groups.append(cur)

    named = {k: v for k, v in (if_levels or {}).items() if v is not None}
    zones = []
    for g in groups:
        low, high = g[0]["strike"], g[-1]["strike"]
        call_m = sum(s["gex_m"] for s in g if s["side"] == "call")
        put_m  = sum(s["gex_m"] for s in g if s["side"] == "put")
        # A zone's role follows where it sits vs spot. Straddling = pivot.
        if high < spot:
            role = "support"
        elif low > spot:
            role = "resistance"
        else:
            role = "pivot (price inside zone)"
        tags = [name for name, lvl in named.items()
                if low - gap / 2 <= lvl <= high + gap / 2]
        zones.append({
            "low": low,
            "high": high,
            "mid_pct_from_spot": round(((low + high) / 2 / spot - 1) * 100, 2),
            "role": role,
            "call_gex_m": round(call_m, 1),
            "put_gex_m": round(put_m, 1),
            "total_abs_gex_m": round(abs(call_m) + abs(put_m), 1),
            "strikes": [s["strike"] for s in g],
            "insiderfinance_tags": tags,
        })
    # InsiderFinance's walls are OI-based, so they can differ from the heaviest
    # GAMMA strikes. Never let a named wall silently drop out of the zones
    # (this also keeps the walls as a fallback if the CBOE fetch fails).
    tagged = {t for z in zones for t in z["insiderfinance_tags"]}
    for name in ("call_wall", "put_wall"):
        lvl = named.get(name)
        if lvl is None or name in tagged:
            continue
        zones.append({
            "low": lvl, "high": lvl,
            "mid_pct_from_spot": round((lvl / spot - 1) * 100, 2),
            "role": ("resistance" if lvl > spot else
                     "support" if lvl < spot else "pivot (price inside zone)"),
            "call_gex_m": 0.0, "put_gex_m": 0.0, "total_abs_gex_m": 0.0,
            "strikes": [lvl],
            "insiderfinance_tags": [name, "insiderfinance_only (not a top gamma strike)"],
        })
    # Strongest first within each role is most useful to read
    zones.sort(key=lambda z: z["total_abs_gex_m"], reverse=True)
    for i, z in enumerate(zones, start=1):
        z["strength_rank"] = i
    return zones


# ── Per-ticker pipeline ───────────────────────────────────────────────────────

def analyze_ticker(ticker, today, if_data=None, cboe=None):
    """if_data / cboe can be injected for testing; otherwise fetched live."""
    if if_data is None:
        if_data = fetch_gex(ticker)
    if cboe is None:
        cboe = fetch_cboe_chain(ticker)
    options, cboe_price, cboe_ts = cboe

    spot = if_data.get("spot_price") or cboe_price
    if spot is None:
        spot = fetch_yahoo_price(ticker, ticker)
    if spot is None:
        print(f"  {ticker}: no spot price from any source — skipping")
        return None

    if_levels = {
        "call_wall":       if_data.get("call_wall"),
        "put_wall":        if_data.get("put_wall"),
        "zero_gamma":      if_data.get("zero_gamma"),
        "peak_gex_strike": if_data.get("peak_gex_strike"),
        "max_pain":        if_data.get("max_pain"),
    }

    table = strike_gex_table(options, ticker, spot, today)
    calls = heavy_strikes(table, "call", spot)
    puts  = heavy_strikes(table, "put", spot)
    for s in calls: s["side"] = "call"
    for s in puts:  s["side"] = "put"

    zones = build_zones(calls + puts, spot, if_levels)
    resistance = sorted([z for z in zones if z["role"] == "resistance"], key=lambda z: z["low"])
    support    = sorted([z for z in zones if z["role"] == "support"], key=lambda z: z["high"], reverse=True)
    pivots     = [z for z in zones if z["role"].startswith("pivot")]

    # Cross-check: does the full-chain #1 strike agree with InsiderFinance?
    def agree(top, wall):
        if not top or wall is None:
            return None
        return abs(top[0]["strike"] - wall) <= spot * ZONE_MERGE_PCT / 100
    cross_check = {
        "cboe_top_call_strike": calls[0]["strike"] if calls else None,
        "insiderfinance_call_wall": if_levels["call_wall"],
        "call_wall_agrees": agree(calls, if_levels["call_wall"]),
        "cboe_top_put_strike": puts[0]["strike"] if puts else None,
        "insiderfinance_put_wall": if_levels["put_wall"],
        "put_wall_agrees": agree(puts, if_levels["put_wall"]),
        "note": ("Disagreement is normal-ish: CBOE here is limited to "
                 f"expirations within {MAX_DTE} days, InsiderFinance uses its "
                 "own expiration set. Large persistent gaps are worth a look."),
    }

    zg = if_levels["zero_gamma"]
    regime = None
    if zg is not None:
        regime = ("above zero gamma — positive-gamma regime: dealers dampen "
                  "moves, zones tend to hold / pin"
                  if spot >= zg else
                  "below zero gamma — negative-gamma regime: dealers amplify "
                  "moves, zones more likely to break and run")

    print(f"  {ticker}: spot={spot}  {len(calls)} heavy call / {len(puts)} heavy put strikes, "
          f"{len(zones)} zones")
    return {
        "ticker": ticker,
        "spot": spot,
        "cboe_data_timestamp": cboe_ts,
        "contracts_used": len(options),
        "gamma_regime": regime,
        "insiderfinance_levels": if_levels,
        "resistance_zones": resistance,
        "support_zones": support,
        "pivot_zones": pivots,
        "heavy_call_strikes": calls,
        "heavy_put_strikes": puts,
        "cross_check": cross_check,
        "data_ok": bool(options),
    }


# ── Persist ───────────────────────────────────────────────────────────────────

def save_csv(results, today_str):
    rows = []
    if os.path.exists(OUTPUT_CSV):
        with open(OUTPUT_CSV, newline="") as f:
            rows = list(csv.DictReader(f))
    tickers_today = {r["ticker"] for r in results}
    # Idempotent: drop ALL of today's rows for these tickers before appending
    rows = [r for r in rows if not (r["date"] == today_str and r["ticker"] in tickers_today)]
    for res in results:
        for s in res["heavy_call_strikes"] + res["heavy_put_strikes"]:
            rows.append({
                "date": today_str, "ticker": res["ticker"], "spot": res["spot"],
                "side": s["side"], "rank": s["rank"], "strike": s["strike"],
                "gex_m": s["gex_m"], "odte_gex_m": s["odte_gex_m"],
                "open_interest": s["open_interest"],
                "pct_from_spot": s["pct_from_spot"], "role": s["role"],
            })
    with open(OUTPUT_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_HEADERS)
        w.writeheader()
        w.writerows(rows)


def summary_line(res):
    def fmt(z):
        band = f"{z['low']:g}" if z["low"] == z["high"] else f"{z['low']:g}-{z['high']:g}"
        tag = f" [{', '.join(z['insiderfinance_tags'])}]" if z["insiderfinance_tags"] else ""
        return band + tag
    r = ", ".join(fmt(z) for z in res["resistance_zones"]) or "none"
    s = ", ".join(fmt(z) for z in res["support_zones"]) or "none"
    return f"{res['ticker']} @ {res['spot']}: resistance {r} | support {s}"


def main():
    now = datetime.now(ET)
    today = now.date()
    today_str = today.isoformat()
    print(f"Key levels run {now.isoformat()}")

    results = []
    for t in TICKERS:
        res = analyze_ticker(t, today)
        if res:
            results.append(res)

    if not results:
        raise SystemExit("No tickers produced results — not overwriting outputs.")

    out = {
        "date": today_str,
        "generated_at": now.isoformat(),
        "method": (f"Per-strike GEX from CBOE delayed chain (expirations <= {MAX_DTE}d, "
                   f"strikes within ±{STRIKE_RANGE_PCT}% of spot), heaviest "
                   f"{TOP_N_PER_SIDE} call and put strikes, merged into zones; "
                   "named levels from InsiderFinance."),
        "how_to_read": ("Resistance = heavy call gamma above spot; support = heavy "
                        "put gamma below spot. Zones hold best above zero gamma "
                        "(positive-gamma regime) and break more easily below it."),
        "tickers": {r["ticker"]: r for r in results},
        "summary": [summary_line(r) for r in results],
    }
    with open(OUTPUT_JSON, "w") as f:
        json.dump(out, f, indent=2)
    save_csv(results, today_str)

    for line in out["summary"]:
        print(line)


if __name__ == "__main__":
    main()
