"""
mag7_tracker.py
───────────────
Daily Mag 7 opportunity scanner for VOO/VGT long-term loading zones.

Fetches for AAPL, MSFT, NVDA, GOOGL, META, AMZN, TSLA:
  - 1 year price history → RSI-14, 200MA, RSI percentile vs own history
  - Options chain → P/C ratio, IV (implied volatility), P/C percentile, IV percentile
  - GEX from InsiderFinance → regime + GEX percentile

Scores each name 0-10 based on percentile ranks vs its OWN history.
High score = macro dip on a fundamentally intact name = loading opportunity.

Output: mag7_log.csv (one row per ticker per day)
"""

import csv
import os
import re
import time
from datetime import datetime, date
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

OUTPUT_CSV = "mag7_log.csv"
TICKERS = ["AAPL", "MSFT", "NVDA", "GOOGL", "META", "AMZN", "TSLA"]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json,text/html,*/*",
    "Accept-Language": "en-US,en;q=0.5",
}

CSV_HEADERS = [
    "date", "ticker",
    # Price / technicals
    "spot_price", "rsi_14", "ma_200", "above_200ma",
    # Percentiles vs own 1-year history
    "rsi_pct",        # low = oversold vs own history
    "iv_pct",         # low = cheap options (good entry)
    "pc_pct",         # high = elevated put buying (fear in this name)
    # Options data
    "iv_current",     # current 30-day IV estimate
    "pc_ratio",       # put/call volume ratio
    # GEX — full parity with SPY/QQQ fields in gex_tracker.py
    "gex_b",          # net GEX in $B
    "gex_regime",     # positive / negative / deeply_negative
    "zero_gamma",     # price level where net gamma flips sign
    "call_wall",      # strike with heaviest call gamma (resistance)
    "put_wall",       # strike with heaviest put gamma (support)
    # Composite score
    "opportunity_score",   # 0-10, higher = better loading opportunity
    "signal",              # plain English
    "signal_detail",       # what drove the score
]


# ── Yahoo Finance helpers ─────────────────────────────────────────────────────

def yf_fetch_history(ticker, period="1y"):
    """Returns list of daily closes, most recent last."""
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
        except Exception as e:
            print(f"  {ticker} history {base} failed: {e}")
    return []


def yf_fetch_options(ticker):
    """
    Fetches nearest expiry options chain.
    Returns (pc_ratio, avg_iv) or (None, None).
    P/C ratio = total put volume / total call volume.
    IV = average implied volatility of near-ATM options.
    """
    for base in ["query1", "query2"]:
        try:
            url = f"https://{base}.finance.yahoo.com/v7/finance/options/{ticker}"
            r = requests.get(url, headers=HEADERS, timeout=15)
            data = r.json()
            result = data.get("optionChain", {}).get("result", [])
            if not result:
                continue

            opts = result[0].get("options", [])
            if not opts:
                continue

            calls = opts[0].get("calls", [])
            puts  = opts[0].get("puts", [])

            # P/C ratio from volume
            call_vol = sum(c.get("volume", 0) or 0 for c in calls)
            put_vol  = sum(p.get("volume", 0) or 0 for p in puts)
            pc_ratio = round(put_vol / call_vol, 3) if call_vol > 0 else None

            # IV — average of near-ATM options (middle 20% by strike)
            spot = result[0].get("quote", {}).get("regularMarketPrice", 0)
            all_opts = calls + puts
            if spot:
                near_atm = [o for o in all_opts
                            if o.get("strike") and abs(o["strike"] - spot) / spot < 0.05
                            and o.get("impliedVolatility") is not None]
                if near_atm:
                    avg_iv = round(sum(o["impliedVolatility"] for o in near_atm) / len(near_atm) * 100, 1)
                else:
                    ivs = [o["impliedVolatility"] for o in all_opts if o.get("impliedVolatility")]
                    avg_iv = round(sum(ivs) / len(ivs) * 100, 1) if ivs else None
            else:
                avg_iv = None

            return pc_ratio, avg_iv

        except Exception as e:
            print(f"  {ticker} options {base} failed: {e}")

    return None, None


def yf_fetch_iv_history(ticker):
    """
    Proxy for IV history: use daily High-Low range as % of close.
    This gives a normalized volatility measure that can be percentile-ranked.
    True IV history requires paid data; this is a good free proxy.
    """
    for base in ["query1", "query2"]:
        try:
            url = f"https://{base}.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=1y"
            r = requests.get(url, headers=HEADERS, timeout=15)
            data = r.json()
            result = data.get("chart", {}).get("result")
            if not result:
                continue
            q = result[0]["indicators"]["quote"][0]
            highs  = q.get("high", [])
            lows   = q.get("low", [])
            closes = q.get("close", [])
            hist_vol = []
            for h, l, c in zip(highs, lows, closes):
                if h and l and c and c > 0:
                    hist_vol.append(round((h - l) / c * 100, 3))
            return hist_vol
        except Exception as e:
            print(f"  {ticker} IV proxy {base} failed: {e}")
    return []


def yf_fetch_pc_history(ticker):
    """
    Fetch historical P/C ratios.
    Yahoo Finance doesn't serve historical P/C directly, so we use
    put/call open interest from the options chain across multiple expiries
    as a proxy for structural sentiment.
    """
    for base in ["query1", "query2"]:
        try:
            url = f"https://{base}.finance.yahoo.com/v7/finance/options/{ticker}"
            r = requests.get(url, headers=HEADERS, timeout=15)
            data = r.json()
            result = data.get("optionChain", {}).get("result", [])
            if not result:
                continue

            # Use OI-based P/C across all expiries as structural positioning
            all_expiry_dates = result[0].get("expirationDates", [])
            pc_vals = []

            # Sample up to 4 near-term expiries
            for exp in all_expiry_dates[:4]:
                try:
                    exp_url = f"https://{base}.finance.yahoo.com/v7/finance/options/{ticker}?date={exp}"
                    er = requests.get(exp_url, headers=HEADERS, timeout=10)
                    edata = er.json()
                    eresult = edata.get("optionChain", {}).get("result", [])
                    if not eresult:
                        continue
                    eopts = eresult[0].get("options", [])
                    if not eopts:
                        continue
                    calls_oi = sum(c.get("openInterest", 0) or 0 for c in eopts[0].get("calls", []))
                    puts_oi  = sum(p.get("openInterest", 0) or 0 for p in eopts[0].get("puts", []))
                    if calls_oi > 0:
                        pc_vals.append(puts_oi / calls_oi)
                except:
                    pass

            return pc_vals  # list of P/C OI ratios across expiries

        except Exception as e:
            print(f"  {ticker} P/C history {base} failed: {e}")
    return []


# ── InsiderFinance GEX + P/C ────────────────────────────────────────────────

def _parse_dollar_amount(value_str, unit):
    """Converts a '$665.1' + 'M' or 'B' pair into a value in $B units."""
    try:
        v = float(value_str.replace(",", ""))
    except ValueError:
        return None
    if unit.upper() == "M":
        return v / 1000.0   # millions -> billions
    return v                # already billions


def fetch_insiderfinance_data(ticker):
    """
    Single fetch of the InsiderFinance GEX page, parsing GEX, P/C ratio,
    zero gamma, call wall, and put wall from the same response — full
    parity with the fields already pulled for SPY/QQQ in gex_tracker.py.

    Combined into one function (rather than separate fetches of the same
    URL per field) to minimize request load on InsiderFinance across 7
    tickers.

    Returns a dict with keys: gex_b, gex_regime, pc_ratio, zero_gamma,
    call_wall, put_wall, spot_price. Any value may be None if not found.
    """
    result = {
        "gex_b": None, "gex_regime": "unknown", "pc_ratio": None,
        "zero_gamma": None, "call_wall": None, "put_wall": None,
        "spot_price": None,
    }
    try:
        url = "https://www.insiderfinance.io/gamma-exposure/" + ticker
        r = requests.get(url, headers=HEADERS, timeout=20)
        soup = BeautifulSoup(r.text, "html.parser")
        text = soup.get_text(separator="\n")

        def find_val(patterns, t):
            for pat in patterns:
                m = re.search(pat, t, re.IGNORECASE | re.DOTALL)
                if m:
                    raw = m.group(1).replace(",", "").replace("$", "").strip()
                    try:
                        return float(raw)
                    except ValueError:
                        pass
            return None

        # GEX — primary tile or narrative sentence, units may be M or B
        # (InsiderFinance prints whichever unit fits the number — mega-cap
        # names often show $B, mid-sized readings frequently show $M; a
        # regex that only matched a trailing "B" silently produced
        # "unknown" for any name whose GEX happened to print in millions)
        tile = re.search(r"Net GEX\s*\n\s*(-?)\$?([\d,\.]+)(M|B)", text, re.IGNORECASE)
        narrative = re.search(
            r"(positive|negative) net gamma of \$?([\d,\.]+)(M|B)", text, re.IGNORECASE
        )

        gex = None
        if tile:
            sign, amount, unit = tile.groups()
            gex = _parse_dollar_amount(amount, unit)
            if gex is not None and sign == "-":
                gex = -gex
        elif narrative:
            direction, amount, unit = narrative.groups()
            gex = _parse_dollar_amount(amount, unit)
            if gex is not None and direction.lower() == "negative":
                gex = -gex

        result["gex_b"] = gex
        if gex is None:
            result["gex_regime"] = "unknown"
        elif gex < -3:
            result["gex_regime"] = "deeply_negative"
        elif gex < 0:
            result["gex_regime"] = "negative"
        elif gex > 3:
            result["gex_regime"] = "strongly_positive"
        else:
            result["gex_regime"] = "positive"

        # Spot price, walls, zero gamma — same field patterns proven
        # working for SPY/QQQ in gex_tracker.py
        result["spot_price"] = find_val(
            [r"Spot Price[:\s\n]*\$?([\d,\.]+)", r"currently trading at \$?([\d,\.]+)"], text
        )
        result["call_wall"]  = find_val([r"Call Wall[:\s\n]*\$?([\d,\.]+)"], text)
        result["put_wall"]   = find_val([r"Put Wall[:\s\n]*\$?([\d,\.]+)"], text)
        result["zero_gamma"] = find_val(
            [r"Zero.Gamma Level[:\s\n]*\$?([\d,\.]+)", r"Zero Gamma[:\s\n]*\$?([\d,\.]+)"], text
        )

        # P/C ratio — plain text on the same page, no Yahoo auth wall.
        # Pattern uses "." instead of "/" between Put and Call to also
        # match "Put-Call Ratio" / "Put Call Ratio" phrasing variants.
        pc_match = re.search(r"Put.Call Ratio[:\s]*([\d\.]+)", text, re.IGNORECASE)
        if pc_match:
            try:
                result["pc_ratio"] = round(float(pc_match.group(1)), 3)
            except ValueError:
                pass

        return result

    except Exception as e:
        print(f"  {ticker} InsiderFinance fetch failed: {e}")
        return result


# ── Technical calculations ────────────────────────────────────────────────────

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


def calc_ma(closes, window=200):
    w = min(window, len(closes))
    return round(sum(closes[-w:]) / w, 2)


def compute_percentile(value, series):
    """
    What percentile is value in series?
    0 = lowest ever seen, 100 = highest ever seen.
    For RSI: low percentile = very oversold vs own history.
    For IV: low percentile = unusually cheap options.
    For P/C: high percentile = unusually elevated fear/hedging.
    """
    if not series or value is None:
        return None
    valid = [x for x in series if x is not None]
    if not valid:
        return None
    below = sum(1 for x in valid if x <= value)
    return round((below / len(valid)) * 100, 1)


# ── Opportunity scoring ───────────────────────────────────────────────────────

def compute_opportunity_score(rsi_pct, iv_pct, pc_pct, gex_regime, above_200ma, rsi_raw):
    """
    Composite score 0-10. Higher = better loading opportunity.
    Based entirely on percentile ranks vs the stock's own history.

    Points:
      RSI percentile (oversold vs own history): 0-3 pts
      IV percentile (cheap options): 0-2 pts
      P/C percentile (elevated fear in this name): 0-2 pts
      GEX regime: 0-2 pts
      200MA position: 0-1 pt
    """
    score = 0
    detail = []

    # RSI — lower percentile = more oversold = more points
    if rsi_pct is not None:
        if rsi_pct <= 10:
            score += 3
            detail.append(f"RSI extremely oversold (bottom {rsi_pct:.0f}% of own history)")
        elif rsi_pct <= 20:
            score += 2
            detail.append(f"RSI very oversold (bottom {rsi_pct:.0f}% of own history)")
        elif rsi_pct <= 35:
            score += 1
            detail.append(f"RSI oversold (bottom {rsi_pct:.0f}% of own history)")
    elif rsi_raw is not None:
        # Fallback to absolute RSI if no percentile history
        if rsi_raw < 30:   score += 3; detail.append(f"RSI absolute oversold ({rsi_raw})")
        elif rsi_raw < 40: score += 2; detail.append(f"RSI weak ({rsi_raw})")
        elif rsi_raw < 50: score += 1; detail.append(f"RSI below midline ({rsi_raw})")

    # IV — lower percentile = cheaper options = better entry cost
    if iv_pct is not None:
        if iv_pct <= 20:
            score += 2
            detail.append(f"Options cheap (IV bottom {iv_pct:.0f}% of own history) — good entry cost")
        elif iv_pct <= 40:
            score += 1
            detail.append(f"Options moderately priced (IV {iv_pct:.0f}th pct)")
        elif iv_pct >= 80:
            detail.append(f"Options expensive (IV top {100-iv_pct:.0f}% of history) — fear priced in, wait")

    # P/C ratio — higher percentile = more put buying = fear in this name
    # BUT: high P/C from macro fear (while RSI very low) = contrarian buy signal
    # High P/C from company-specific fear = avoid
    if pc_pct is not None:
        if pc_pct >= 80:
            score += 2
            detail.append(f"Heavy put buying (P/C top {100-pc_pct:.0f}% of history) — extreme fear, contrarian buy")
        elif pc_pct >= 60:
            score += 1
            detail.append(f"Elevated put buying (P/C {pc_pct:.0f}th pct)")

    # GEX regime
    if gex_regime == "deeply_negative":
        score += 1
        detail.append("GEX deeply negative — moves amplified, dip can extend but squeeze potential high")
    elif gex_regime == "negative":
        score += 1
        detail.append("GEX negative — unstable, watch for stabilization")
    elif gex_regime == "strongly_positive":
        score += 2
        detail.append("GEX strongly positive — dealers stabilizing, dip buyers have tailwind")
    elif gex_regime == "positive":
        score += 1
        detail.append("GEX positive — dealers providing support")

    # 200MA
    if above_200ma is True:
        score += 1
        detail.append("Above 200MA — uptrend intact, dip is buyable")
    elif above_200ma is False:
        detail.append("Below 200MA — downtrend, scale in slowly")

    score = min(10, score)

    # Signal label
    if score >= 8:
        signal = "STRONG BUY — macro dip on intact name"
    elif score >= 6:
        signal = "BUY — oversold, good loading zone"
    elif score >= 4:
        signal = "WATCH — setup building, not quite ready"
    elif score >= 2:
        signal = "NEUTRAL — no edge, wait"
    else:
        signal = "AVOID — not oversold or fear is company-specific"

    return score, signal, " | ".join(detail)


# ── CSV helpers ───────────────────────────────────────────────────────────────

def load_existing_history():
    """Load existing mag7_log.csv to build percentile history."""
    history = {t: {"rsi": [], "iv": [], "pc": [], "gex": []} for t in TICKERS}
    if not os.path.isfile(OUTPUT_CSV):
        return history
    try:
        with open(OUTPUT_CSV, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                t = row.get("ticker")
                if t not in history:
                    continue
                def sf(k):
                    try: return float(row[k]) if row.get(k) else None
                    except: return None
                rsi = sf("rsi_14")
                iv  = sf("iv_current")
                pc  = sf("pc_ratio")
                gex = sf("gex_b")
                if rsi: history[t]["rsi"].append(rsi)
                if iv:  history[t]["iv"].append(iv)
                if pc:  history[t]["pc"].append(pc)
                if gex: history[t]["gex"].append(gex)
    except Exception as e:
        print(f"Could not load history: {e}")
    return history


def save_row(row):
    """
    Idempotent write keyed on (date, ticker): if this ticker already has a
    row for today, replace it in place instead of appending a duplicate.
    Makes re-running the same day (manual re-trigger, retry, accidental
    double dispatch) safe.
    """
    today  = row.get("date")
    ticker = row.get("ticker")
    existing_rows = []
    if os.path.isfile(OUTPUT_CSV):
        with open(OUTPUT_CSV, newline="", encoding="utf-8") as f:
            existing_rows = list(csv.DictReader(f))

    already_present = any(r.get("date") == today and r.get("ticker") == ticker for r in existing_rows)

    if already_present:
        existing_rows = [row if (r.get("date") == today and r.get("ticker") == ticker) else r
                          for r in existing_rows]
        with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=CSV_HEADERS, extrasaction="ignore")
            w.writeheader()
            w.writerows(existing_rows)
        print(f"  Updated existing row for {ticker} on {today} (re-run detected, no duplicate created)")
    else:
        exists = os.path.isfile(OUTPUT_CSV)
        with open(OUTPUT_CSV, "a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=CSV_HEADERS, extrasaction="ignore")
            if not exists:
                w.writeheader()
            w.writerow(row)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    today = datetime.now(ZoneInfo("America/New_York")).date().strftime("%Y-%m-%d")
    now   = datetime.now().strftime("%I:%M %p")

    print("=" * 60)
    print(f"  Mag 7 Opportunity Scanner  |  {today}  {now}")
    print("=" * 60)

    # Load existing history for percentile calculations
    print("\nLoading historical data for percentile calculations...")
    history = load_existing_history()
    for t in TICKERS:
        print(f"  {t}: {len(history[t]['rsi'])} RSI data points in history")

    results = []

    for ticker in TICKERS:
        print(f"\n{'─'*50}")
        print(f"  Processing {ticker}...")

        # 1. Price history + technicals
        print(f"  Fetching {ticker} price history...")
        closes = yf_fetch_history(ticker, period="1y")
        if not closes:
            print(f"  WARNING: No price data for {ticker}, skipping")
            continue

        spot   = closes[-1]
        rsi    = calc_rsi(closes)
        ma200  = calc_ma(closes, 200)
        above_200 = spot > ma200 if ma200 else None

        print(f"  Spot=${spot:.2f}  RSI={rsi}  200MA={ma200}  Above={above_200}")

        # 2. Options chain — Yahoo for IV (P/C used only as fallback, since
        # Yahoo's options endpoint requires a crumb/cookie handshake that
        # frequently fails; InsiderFinance serves P/C unauthenticated below)
        print(f"  Fetching {ticker} options chain (Yahoo, IV + P/C fallback)...")
        pc_ratio_yahoo, iv_current = yf_fetch_options(ticker)

        # 3. GEX + walls + zero gamma + P/C from InsiderFinance — single
        # combined fetch of the same page (avoids requesting the URL
        # multiple times), full parity with the SPY/QQQ fields
        print(f"  Fetching {ticker} GEX + walls + P/C (InsiderFinance)...")
        if_data    = fetch_insiderfinance_data(ticker)
        gex_b      = if_data["gex_b"]
        gex_regime = if_data["gex_regime"]
        zero_gamma = if_data["zero_gamma"]
        call_wall  = if_data["call_wall"]
        put_wall   = if_data["put_wall"]
        pc_ratio_if = if_data["pc_ratio"]

        # Prefer InsiderFinance's P/C (unauthenticated, reliable) over Yahoo's
        # (frequently blocked by crumb requirement) when both are available
        pc_ratio = pc_ratio_if if pc_ratio_if is not None else pc_ratio_yahoo

        print(f"  P/C={pc_ratio} (source={'InsiderFinance' if pc_ratio_if is not None else 'Yahoo' if pc_ratio_yahoo is not None else 'none'})  IV={iv_current}%")
        print(f"  GEX={gex_b}  Regime={gex_regime}  ZeroGamma={zero_gamma}  CallWall={call_wall}  PutWall={put_wall}")

        # 4. Compute percentiles vs own history
        hist_rsi = history[ticker]["rsi"] + ([rsi] if rsi else [])
        hist_iv  = history[ticker]["iv"]  + ([iv_current] if iv_current else [])
        hist_pc  = history[ticker]["pc"]  + ([pc_ratio] if pc_ratio else [])

        # Need at least 20 data points for meaningful percentiles
        # Fall back to IV proxy from daily price range if < 20 options data points
        if len(hist_iv) < 20:
            print(f"  Building IV proxy from price range history...")
            iv_proxy = yf_fetch_iv_history(ticker)
            if iv_proxy and iv_current:
                # Convert current IV to comparable proxy scale
                avg_proxy = sum(iv_proxy) / len(iv_proxy) if iv_proxy else None
                if avg_proxy:
                    # Scale current IV to proxy range
                    iv_scaled = iv_current / 100 * avg_proxy * 10
                    hist_iv = iv_proxy
                    iv_current_scaled = iv_scaled
                else:
                    iv_current_scaled = iv_current
            else:
                iv_current_scaled = iv_current
        else:
            iv_current_scaled = iv_current

        rsi_pct = compute_percentile(rsi, hist_rsi) if len(hist_rsi) >= 5 else None
        iv_pct  = compute_percentile(iv_current_scaled, hist_iv) if len(hist_iv) >= 5 else None
        pc_pct  = compute_percentile(pc_ratio, hist_pc) if len(hist_pc) >= 5 else None

        print(f"  Percentiles: RSI={rsi_pct}  IV={iv_pct}  PC={pc_pct}")

        # 5. Compute opportunity score
        score, signal, detail = compute_opportunity_score(
            rsi_pct, iv_pct, pc_pct, gex_regime, above_200, rsi
        )
        print(f"  Score={score}/10  Signal={signal}")

        row = {
            "date":              today,
            "ticker":            ticker,
            "spot_price":        round(spot, 2),
            "rsi_14":            rsi,
            "ma_200":            ma200,
            "above_200ma":       above_200,
            "rsi_pct":           rsi_pct,
            "iv_pct":            iv_pct,
            "pc_pct":            pc_pct,
            "iv_current":        iv_current,
            "pc_ratio":          pc_ratio,
            "gex_b":             gex_b,
            "gex_regime":        gex_regime,
            "zero_gamma":        zero_gamma,
            "call_wall":         call_wall,
            "put_wall":          put_wall,
            "opportunity_score": score,
            "signal":            signal,
            "signal_detail":     detail,
        }

        save_row(row)
        results.append(row)

        # Rate limit — be polite to InsiderFinance
        time.sleep(3)

    # Summary
    print(f"\n{'='*60}")
    print(f"  MAG 7 SUMMARY — {today}")
    print(f"{'='*60}")
    results.sort(key=lambda x: x["opportunity_score"], reverse=True)
    for r in results:
        bar = "█" * int(r["opportunity_score"]) + "░" * (10 - int(r["opportunity_score"]))
        print(f"  {r['ticker']:6} [{bar}] {r['opportunity_score']}/10  {r['signal']}")
        if r["signal_detail"]:
            for part in r["signal_detail"].split(" | ")[:2]:
                print(f"         → {part}")

    print(f"\nSaved to {OUTPUT_CSV}")
    print("Done.")


if __name__ == "__main__":
    main()
