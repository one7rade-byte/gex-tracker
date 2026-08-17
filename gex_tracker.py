import csv
import os
import re
import smtplib
from datetime import datetime, date
from zoneinfo import ZoneInfo
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import requests
from bs4 import BeautifulSoup

OUTPUT_CSV = "gex_log.csv"
TICKERS    = ["SPY", "QQQ"]   # both tracked daily
EMAIL_FROM = "one7rade@gmail.com"
EMAIL_TO   = "one7rade@gmail.com"
EMAIL_PASS = os.environ.get("GMAIL_PASS", "")

def gex_url(ticker):
    return "https://www.insiderfinance.io/gamma-exposure/" + ticker

def yf_url(symbol, period="1y", interval="1d"):
    sym = requests.utils.quote(symbol)
    return f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval={interval}&range={period}"

CSV_HEADERS = [
    "date", "ticker", "spot_price", "net_gex_b", "vix",
    "zero_gamma", "call_wall", "put_wall", "peak_gex_strike", "max_pain", "pc_ratio",
    "spy_200ma", "spy_above_200ma", "spy_rsi_14",
    "vix_3m", "vix_term_spread", "vix_term_structure",
    "skew_index",
    "fear_score", "bull_score", "bear_score", "score_label",
    # QQQ divergence columns (only populated on SPY rows)
    "qqq_spot", "qqq_gex_b", "qqq_fear_score", "qqq_bear_score", "qqq_bull_score",
    "qqq_divergence",   # SPY_bull + QQQ_bear = bearish divergence warning
    "signal", "l1_context",
    # Macro context — added Aug 2026
    "yield_10y",    # 10-year Treasury yield (^TNX) — key macro input
    "vix9d",        # 9-day VIX (^VIX9D) — near-term fear gauge
    "vix9d_vix_ratio",  # VIX9D/VIX30 ratio >1.10 = near-term capitulation signal
    # Cross-asset flow tracking — added Aug 2026
    # Goal: track where money is flowing to identify crash vs panic vs rotation
    "gold",         # GLD ETF price — safe haven demand
    "dxy",          # US Dollar Index (^DXY) — cash hoarding signal
    "tlt",          # TLT 20Y Treasury ETF — bond market stress
    "hyg",          # HYG High Yield Bond ETF — credit stress indicator
    "copper",       # CPER copper ETF — global economic health (Dr. Copper)
    "oil",          # USO oil ETF — inflation/demand signal
    "eem",          # EEM Emerging Markets ETF — global risk appetite
    "xlre",         # XLRE Real Estate ETF — rate sensitivity
    "flow_regime",  # computed: cash_hoard|inflation|recession|credit_crisis|risk_on|rotation
    "flow_score",   # -5 to +5: negative=risk-off, positive=risk-on
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


# ── Fetchers ──────────────────────────────────────────────────────────────────

def fetch_yahoo_price(encoded_symbol, label="symbol"):
    """
    Robust Yahoo Finance price fetcher.
    Tries v8 chart on query1, then query2, then v7 quote endpoint.
    Returns float price or None.
    """
    # v8 chart endpoint — try both query1 and query2
    for base in ["query1", "query2"]:
        try:
            url = f"https://{base}.finance.yahoo.com/v8/finance/chart/{encoded_symbol}?interval=1d&range=1d"
            r = requests.get(url, headers=HEADERS, timeout=10)
            data = r.json()
            result = data.get("chart", {}).get("result")
            if not result:
                print(f"  {label} v8 {base}: empty result")
                continue
            price = result[0]["meta"]["regularMarketPrice"]
            if price is not None:
                return round(float(price), 2)
        except Exception as e:
            print(f"  {label} v8 {base} failed: {e}")

    # v7 quote endpoint as final fallback
    try:
        url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={encoded_symbol}"
        r = requests.get(url, headers=HEADERS, timeout=10)
        data = r.json()
        results = data.get("quoteResponse", {}).get("result", [])
        if results:
            price = results[0].get("regularMarketPrice")
            if price is not None:
                return round(float(price), 2)
    except Exception as e:
        print(f"  {label} v7 fallback failed: {e}")

    print(f"  {label}: all endpoints failed")
    return None

def fetch_vix():
    vix = fetch_yahoo_price("%5EVIX", "VIX")
    if vix is None:
        print("VIX fetch failed on all endpoints")
    return vix


def fetch_gex(ticker):
    result = {}
    try:
        print(f"Fetching InsiderFinance GEX for {ticker}...")
        r = requests.get(gex_url(ticker), headers=HEADERS, timeout=20)
        print("Status: " + str(r.status_code))
        soup = BeautifulSoup(r.text, "html.parser")
        text = soup.get_text(separator="\n")

        if ticker == "SPY":
            print("--- PAGE SAMPLE ---")
            print(text[:3000])
            print("--- END SAMPLE ---")

        def find_val(patterns, t):
            for pat in patterns:
                m = re.search(pat, t, re.IGNORECASE | re.DOTALL)
                if m:
                    raw = m.group(1).replace(",", "").replace("$", "").strip()
                    try: return float(raw)
                    except: pass
            return None

        def parse_dollar_amount(value_str, unit):
            """Converts a numeric string + 'M'/'B' unit into a value in $B units."""
            try:
                v = float(value_str.replace(",", ""))
            except ValueError:
                return None
            return v / 1000.0 if unit.upper() == "M" else v

        # GEX — primary tile or narrative sentence, units may be M or B.
        # InsiderFinance prints whichever unit fits the number — SPY is large
        # enough to usually show $B, but QQQ (and individual stocks) often
        # report in $M. A regex that only matched a trailing "B" silently
        # produced no value at all on any day the reading printed in millions
        # — this was the root cause of QQQ GEX being blank for weeks while
        # SPY (consistently large enough for $B) kept working.
        tile = re.search(r"Net GEX\s*\n\s*(-?)\$?([\d,\.]+)(M|B)", text, re.IGNORECASE)
        narrative = re.search(
            r"(positive|negative) net gamma of \$?([\d,\.]+)(M|B)", text, re.IGNORECASE
        )

        gex = None
        if tile:
            sign, amount, unit = tile.groups()
            gex = parse_dollar_amount(amount, unit)
            if gex is not None and sign == "-":
                gex = -gex
        elif narrative:
            direction, amount, unit = narrative.groups()
            gex = parse_dollar_amount(amount, unit)
            if gex is not None and direction.lower() == "negative":
                gex = -gex

        if gex is not None:
            result["net_gex_b"] = gex

        result["spot_price"]      = find_val([r"Spot Price[:\s\n]*\$?([\d,\.]+)", r"currently trading at \$?([\d,\.]+)"], text)
        result["call_wall"]       = find_val([r"Call Wall[:\s\n]*\$?([\d,\.]+)"], text)
        result["put_wall"]        = find_val([r"Put Wall[:\s\n]*\$?([\d,\.]+)"], text)
        result["zero_gamma"]      = find_val([r"Zero.Gamma Level[:\s\n]*\$?([\d,\.]+)", r"Zero Gamma[:\s\n]*\$?([\d,\.]+)"], text)
        result["peak_gex_strike"] = find_val([r"Peak GEX Strike[:\s\n]*\$?([\d,\.]+)"], text)
        result["max_pain"]        = find_val([r"Max Pain[:\s\n]*\$?([\d,\.]+)"], text)

        pc = re.search(r"Put.Call Ratio[:\s]*([\d\.]+)", text, re.IGNORECASE)
        if pc:
            try: result["pc_ratio"] = float(pc.group(1))
            except: pass

        print(f"  {ticker} GEX={result.get('net_gex_b')}  spot={result.get('spot_price')}")
    except Exception as e:
        print(f"GEX fetch failed for {ticker}: " + str(e))
    return result


def fetch_spy_technicals():
    result = {"spy_200ma": None, "spy_above_200ma": None, "spy_rsi_14": None}
    try:
        r = requests.get(yf_url("SPY", period="1y", interval="1d"), headers=HEADERS, timeout=15)
        data = r.json()
        closes = data["chart"]["result"][0]["indicators"]["quote"][0]["close"]
        closes = [c for c in closes if c is not None]
        if len(closes) < 15:
            return result
        ma_window = min(200, len(closes))
        ma200 = round(sum(closes[-ma_window:]) / ma_window, 2)
        spot  = closes[-1]
        deltas   = [closes[i] - closes[i-1] for i in range(1, len(closes))]
        gains    = [max(d, 0) for d in deltas[-14:]]
        losses   = [abs(min(d, 0)) for d in deltas[-14:]]
        avg_gain = sum(gains) / 14
        avg_loss = sum(losses) / 14
        rsi = 100.0 if avg_loss == 0 else round(100 - (100 / (1 + avg_gain / avg_loss)), 2)
        result["spy_200ma"]       = ma200
        result["spy_above_200ma"] = spot > ma200
        result["spy_rsi_14"]      = rsi
        print(f"  200MA={ma200}  RSI={rsi}  Above200MA={spot > ma200}")
    except Exception as e:
        print("SPY technicals fetch failed: " + str(e))
    return result



def fetch_vix_term_structure():
    result = {"vix_3m": None}
    vix3m = fetch_yahoo_price("%5EVIX3M", "VIX3M")
    if vix3m is not None:
        result["vix_3m"] = vix3m
        print(f"  VIX3M={vix3m}")
    return result


def fetch_skew():
    skew = fetch_yahoo_price("%5ESKEW", "SKEW")
    if skew is not None:
        print(f"  SKEW={skew}")
    return skew


# ── Confluence scoring ────────────────────────────────────────────────────────

def compute_scores(gex, vix, rsi, term_structure, skew, above_200ma):
    fear = 0
    bull = 0
    bear = 0

    if gex is not None:
        if gex < -10:   fear += 3
        elif gex < -5:  fear += 2
        elif gex < 0:   fear += 1
        if gex > 10:    bull += 3
        elif gex > 5:   bull += 2
        elif gex > 0:   bull += 1
        if gex < -10:   bear += 3
        elif gex < -5:  bear += 2
        elif gex < -2:  bear += 1

    if vix is not None:
        if vix > 28:    fear += 2
        elif vix > 22:  fear += 1
        if vix < 15:    bull += 2
        elif vix < 18:  bull += 1
        if vix > 25:    bear += 2
        elif vix > 20:  bear += 1

    if term_structure == "backwardation":
        fear += 1
        bear += 1
    elif term_structure == "contango":
        bull += 1

    if skew is not None:
        if skew > 145:
            fear += 2; bear += 2
        elif skew > 135:
            fear += 1; bear += 1
        if skew < 115:
            bull += 1

    if rsi is not None:
        if rsi < 30:             fear += 1
        if rsi > 55 and rsi <= 70: bull += 2
        elif rsi > 45:           bull += 1
        if rsi > 75:    bear += 2
        elif rsi > 70:  bear += 1
        if 30 < rsi < 45: bear += 1

    if above_200ma is False:
        fear += 1; bear += 1
    elif above_200ma is True:
        bull += 1

    fear = min(10, fear)
    bull = min(10, bull)
    bear = min(10, bear)

    if fear >= 8:       label = "HIGH CONVICTION BUY ZONE"
    elif fear >= 6:     label = "Fear building — watch for entry"
    elif fear >= 4:     label = "Moderate fear — monitor"
    elif bear >= 7:     label = "BEAR SIGNAL — reduce / exit"
    elif bear >= 5:     label = "Bear building — caution"
    elif bull >= 8:     label = "Strong bull regime — hold"
    elif bull >= 6:     label = "Positive regime — hold"
    elif bull >= 4:     label = "Mild bull — neutral"
    else:               label = "Mixed — no edge"

    return fear, bull, bear, label


def compute_qqq_scores(qqq_gex, vix):
    """
    Simplified scoring for QQQ — uses only GEX and VIX (no RSI/SKEW/200MA for QQQ).
    Returns (fear, bull, bear).
    """
    fear = 0; bull = 0; bear = 0
    if qqq_gex is not None:
        if qqq_gex < -5:  fear += 2; bear += 2
        elif qqq_gex < 0: fear += 1; bear += 1
        if qqq_gex > 5:   bull += 2
        elif qqq_gex > 0: bull += 1
    if vix is not None:
        if vix > 25:    fear += 2; bear += 2
        elif vix > 20:  fear += 1; bear += 1
        if vix < 15:    bull += 2
        elif vix < 18:  bull += 1
    return min(10, fear), min(10, bull), min(10, bear)


def compute_divergence(spy_bull, spy_bear, qqq_bear, qqq_bull):
    """
    Detect divergences between SPY and QQQ GEX regimes.
    These are the most actionable signals — market appears calm but tech is breaking.
    """
    if spy_bull >= 6 and qqq_bear >= 5:
        return "BEARISH DIVERGENCE — SPY positive but QQQ GEX bearish. Tech leading lower. Watch for SPY to follow."
    if spy_bear >= 5 and qqq_bull >= 6:
        return "BULLISH DIVERGENCE — SPY bearish but QQQ GEX turning positive. Tech stabilizing. Watch for recovery."
    if qqq_bear >= 6 and spy_bear < 4:
        return "QQQ WARNING — QQQ bear score elevated before SPY. Early warning signal. Monitor SPY GEX closely."
    if qqq_bull >= 7 and spy_bull >= 7:
        return "ALIGNED BULL — Both SPY and QQQ GEX strongly positive. High conviction hold."
    if qqq_bear >= 5 and spy_bear >= 5:
        return "ALIGNED BEAR — Both SPY and QQQ GEX bearish. Confirmed broad market stress."
    return "Aligned — no divergence"


# ── Signal + context ──────────────────────────────────────────────────────────

def compute_signal(gex, vix, rsi=None, term_structure=None, neg_day_streak=0):
    """
    Refined signal logic — v2 (Aug 2026)
    Key finding from 95-day backtest:
      - RSI is the critical separator between BUY and EXIT
      - RSI < 50 + deep neg GEX = buy zone (avg +4-6% 5-day return)
      - RSI > 70 + neg GEX = overbought pullback, NOT an exit
      - "RED Watch" was actually best signal (79% win rate, +3% avg)
      - True EXIT is very rare: needs backwardation OR GEX < -15B + VIX > 21
    """
    if gex is None or vix is None:
        return "Unknown - check data"

    rsi_val = rsi if rsi is not None else 50  # default neutral if missing

    # ── STRONG BUY: deep neg GEX + oversold RSI + elevated VIX ──────────────
    # Backtest: Jun 10 (+4.2%), Jul 29 (+6.3%), Jul 23-28 cluster (+4-5%)
    if gex < -10 and rsi_val < 50 and vix > 18 and neg_day_streak >= 3:
        return "STRONG BUY - deep neg GEX + oversold + fear elevated"

    # ── BUY WATCH: neg GEX + RSI not overbought + multi-day setup ────────────
    # Backtest: 79% win rate, +3% avg 5-day return — best signal in dataset
    if gex < -5 and rsi_val < 57 and vix > 17:
        return "BUY WATCH - neg GEX + RSI neutral + vol elevated"

    # ── TRUE EXIT: very specific conditions (backwardation OR extreme GEX+VIX) ─
    # Only 1 genuine exit in 95-day dataset (Jun 5: -1.5%)
    # Requires VIX backwardation OR (GEX < -15B AND VIX > 21)
    if gex < -5 and vix > 21 and (term_structure == "backwardation" or (gex < -15 and vix > 20.5)):
        if rsi_val < 65:  # not overbought — real fear, not just pullback
            return "RED EXIT - confirmed stress: deep neg GEX + VIX spike"

    # ── OVERBOUGHT CAUTION: neg GEX but RSI elevated ─────────────────────────
    # Apr 21-23: RSI 86-90, market just needed to cool — NOT a real exit
    # These averaged +1.7% over 5 days — do NOT exit long-term positions
    if gex < 0 and rsi_val > 70:
        return "AMBER Caution - overbought pullback, tighten stops only"

    # ── STANDARD CAUTION: mild neg GEX, RSI neutral ───────────────────────────
    if gex < 0 and vix < 19:
        return "AMBER Caution - neg GEX, watch VIX"

    # ── STRONG HOLD: max positive GEX, vol crushed ────────────────────────────
    if gex > 10 and vix < 18:
        return "GREEN Strong hold - GEX high, vol suppressed"

    # ── HOLD: standard positive regime ────────────────────────────────────────
    if gex > 0 and vix < 19:
        return "GREEN Hold - pos GEX, vol controlled"

    return "NEUTRAL - monitor"


def compute_yield_context(yield_10y, vix9d_val, vix9d_ratio):
    """Add 10Y yield and VIX9D context to signal narrative."""
    parts = []
    if yield_10y is not None:
        if yield_10y > 4.5:
            parts.append(f"10Y yield {yield_10y:.2f}% — elevated, headwind for growth stocks")
        elif yield_10y < 3.8:
            parts.append(f"10Y yield {yield_10y:.2f}% — falling, tailwind for equities")
        else:
            parts.append(f"10Y yield {yield_10y:.2f}% — neutral range")
    if vix9d_ratio is not None:
        if vix9d_ratio > 1.15:
            parts.append(f"VIX9D/VIX ratio {vix9d_ratio:.2f} — near-term fear spike, short-term entry signal")
        elif vix9d_ratio > 1.05:
            parts.append(f"VIX9D/VIX ratio {vix9d_ratio:.2f} — near-term fear building")
        else:
            parts.append(f"VIX9D/VIX ratio {vix9d_ratio:.2f} — term structure calm")
    return " | ".join(parts) if parts else ""

def compute_l1_context(spy_above_200ma, rsi, term_structure, skew, vix):
    parts = []
    if spy_above_200ma is True:
        parts.append("SPY above 200MA (uptrend intact)")
    elif spy_above_200ma is False:
        parts.append("SPY BELOW 200MA (downtrend warning)")
    if rsi is not None:
        if rsi < 30:   parts.append(f"RSI oversold ({rsi})")
        elif rsi > 70: parts.append(f"RSI overbought ({rsi})")
        else:          parts.append(f"RSI neutral ({rsi})")
    if term_structure == "backwardation":
        parts.append("VIX in backwardation (stress elevated)")
    elif term_structure == "contango":
        parts.append("VIX in contango (calm)")
    if skew is not None:
        if skew > 135:   parts.append(f"SKEW elevated ({skew}) - tail hedging active")
        elif skew < 115: parts.append(f"SKEW low ({skew}) - minimal tail hedging")
        else:            parts.append(f"SKEW normal ({skew})")
    return " | ".join(parts) if parts else "No context data"


# ── CSV + email ───────────────────────────────────────────────────────────────

def save_csv(row):
    """
    Idempotent write: collapses to exactly one row per date, replacing it
    with fresh data on every run. Makes re-running the same day (manual
    re-trigger, retry, accidental double dispatch) safe.

    NOTE: this previously used a list comprehension that replaced every
    row matching today's date with the new row — correct when at most one
    match existed, but if duplicates ever accumulated (e.g. from an
    interrupted write, or before this function existed), it would stamp
    the same new row onto every duplicate instead of collapsing them,
    making the problem worse rather than fixing it. This version always
    keeps exactly one row per date regardless of how many already exist.
    """
    today = row.get("date")
    existing_rows = []
    if os.path.isfile(OUTPUT_CSV):
        with open(OUTPUT_CSV, newline="", encoding="utf-8") as f:
            existing_rows = list(csv.DictReader(f))

    # Keep all rows that are NOT today's date, then append exactly one
    # fresh row for today — this guarantees no duplicates regardless of
    # how many stale matches were already present
    other_rows = [r for r in existing_rows if r.get("date") != today]
    had_duplicates = len(existing_rows) - len(other_rows) > 1

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_HEADERS, extrasaction="ignore")
        w.writeheader()
        w.writerows(other_rows)
        w.writerow(row)

    if had_duplicates:
        print(f"  WARNING: found multiple stale duplicate rows for {today} — collapsed to one")
    else:
        print(f"Saved row for {today} -> {OUTPUT_CSV}")


def send_email(subject, body):
    if not EMAIL_PASS:
        print("No email password set - skipping email")
        return
    try:
        msg = MIMEMultipart()
        msg["From"]    = EMAIL_FROM
        msg["To"]      = EMAIL_TO
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))
        with smtplib.SMTP("smtp.gmail.com", 587) as s:
            s.starttls()
            s.login(EMAIL_FROM, EMAIL_PASS)
            s.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())
        print("Email sent to " + EMAIL_TO)
    except Exception as e:
        print("Email failed: " + str(e))


# ── Main ──────────────────────────────────────────────────────────────────────


def compute_flow_regime(spy, gold, dxy, tlt, hyg, vix, copper, eem):
    """
    Determine where money is flowing based on cross-asset behavior.
    
    Key patterns:
    - Cash hoarding:   stocks↓ gold↓ dxy↑ tlt↑  → temporary panic, buy opportunity
    - Inflation fear:  stocks↓ gold↑ dxy↓ tlt↓  → real asset rotation
    - Recession fear:  stocks↓ gold↑ dxy↑ tlt↑  → flight to safety, wait
    - Credit crisis:   stocks↓ gold↓ dxy↑↑ tlt↓ → systemic (2008/COVID), be careful
    - Risk on:         stocks↑ gold flat dxy↓    → bull regime
    - Rotation:        stocks↓ gold↑ eem↓        → sector rotation
    
    Returns (regime_label, flow_score)
    flow_score: -5 (max risk-off) to +5 (max risk-on)
    """
    if not all([spy, gold, dxy, tlt, hyg, vix]):
        return "unknown", 0

    score = 0
    signals = []

    # VIX regime
    if vix < 15:
        score += 2
        signals.append("vix_low")
    elif vix < 20:
        score += 1
        signals.append("vix_calm")
    elif vix > 25:
        score -= 2
        signals.append("vix_elevated")
    elif vix > 20:
        score -= 1
        signals.append("vix_rising")

    # Credit stress — HYG is the key early warning
    if hyg and hyg > 78:
        score += 1
        signals.append("credit_healthy")
    elif hyg and hyg < 74:
        score -= 2
        signals.append("credit_stress")
    elif hyg and hyg < 70:
        score -= 3
        signals.append("credit_crisis")

    # Copper — global growth proxy
    if copper and copper > 22:
        score += 1
        signals.append("copper_strong")
    elif copper and copper < 18:
        score -= 1
        signals.append("copper_weak")

    # Emerging markets — global risk appetite
    if eem and eem > 42:
        score += 1
        signals.append("global_risk_on")
    elif eem and eem < 36:
        score -= 1
        signals.append("global_risk_off")

    # Determine regime from pattern
    # Get today's previous close for comparison (use score as proxy)
    if score >= 3:
        regime = "risk_on"
    elif score >= 1:
        regime = "mild_risk_on"
    elif score == 0:
        regime = "neutral"
    elif score >= -1:
        # Check gold vs DXY for cash hoard vs inflation
        if dxy and gold and dxy > 104 and gold < 220:
            regime = "cash_hoarding"  # panic sell — buy opportunity
        elif gold and gold > 240:
            regime = "inflation_rotation"
        else:
            regime = "mild_risk_off"
    elif score >= -3:
        if dxy and dxy > 107:
            regime = "cash_hoarding"  # stronger panic
        else:
            regime = "recession_fear"
    else:
        if hyg and hyg < 70:
            regime = "credit_crisis"  # most dangerous — 2008/COVID pattern
        else:
            regime = "risk_off"

    return regime, max(-5, min(5, score))


def main():
    today = datetime.now(ZoneInfo("America/New_York")).date().strftime("%Y-%m-%d")
    now   = datetime.now().strftime("%I:%M %p")

    print("====================================================")
    print("  GEX Daily Tracker  |  " + today + "  " + now)
    print("====================================================")

    print("\n[1/6] Fetching VIX...")
    vix = fetch_vix()
    print("      VIX = " + str(vix))

    print("\n[2/6] Fetching SPY GEX...")
    spy_data = fetch_gex("SPY")

    print("\n[3/6] Fetching QQQ GEX...")
    qqq_data = fetch_gex("QQQ")

    print("\n[4/6] Fetching SPY technicals (200MA, RSI)...")
    technicals = fetch_spy_technicals()

    print("\n[5/6] Fetching VIX term structure + SKEW...")
    term_data = fetch_vix_term_structure()
    vix_3m    = term_data.get("vix_3m")
    if vix is not None and vix_3m is not None:
        spread    = round(vix_3m - vix, 2)
        structure = "contango" if spread > 0 else "backwardation"
    else:
        spread = None; structure = None
    print(f"      Term spread = {spread}  [{structure}]")

    print("\n[6/6] Fetching SKEW...")
    skew = fetch_skew()

    print("\n[7/8] Fetching 10Y yield + VIX9D...")
    yield_10y = fetch_yahoo_price("%5ETNX", "10Y Yield")
    vix9d_val = fetch_yahoo_price("%5EVIX9D", "VIX9D")
    vix9d_ratio = None
    if vix9d_val is not None and vix is not None and vix > 0:
        vix9d_ratio = round(vix9d_val / vix, 3)
    print(f"      10Y Yield = {yield_10y}  VIX9D = {vix9d_val}  Ratio = {vix9d_ratio}")

    print("\n[8/8] Fetching cross-asset flow data...")
    try:
        gold  = fetch_yahoo_price("GLD",  "Gold/GLD")
        # DXY — try multiple Yahoo symbols for Dollar Index
        dxy = None
        for dxy_sym in ["DX=F", "DX-Y.NYB", "%5EDXY"]:
            dxy = fetch_yahoo_price(dxy_sym, f"DXY({dxy_sym})")
            if dxy is not None:
                break
        tlt   = fetch_yahoo_price("TLT",  "TLT Bonds")
        hyg   = fetch_yahoo_price("HYG",  "HYG Credit")
        copper= fetch_yahoo_price("CPER", "Copper/CPER")
        oil   = fetch_yahoo_price("USO",  "Oil/USO")
        eem   = fetch_yahoo_price("EEM",  "EEM Emerging")
        xlre  = fetch_yahoo_price("XLRE", "XLRE Real Estate")
        print(f"      GLD={gold} DXY={dxy} TLT={tlt} HYG={hyg}")
        print(f"      Copper={copper} Oil={oil} EEM={eem} XLRE={xlre}")
    except Exception as e:
        print(f"      Cross-asset fetch error: {e}")
        gold=dxy=tlt=hyg=copper=oil=eem=xlre=None

    # Compute flow regime — where is money going?
    try:
        spy_price = spy_data.get("spot_price")
        try:
            spy_price = float(spy_price) if spy_price else None
        except:
            spy_price = None
        flow_regime, flow_score = compute_flow_regime(
            spy=spy_price, gold=gold, dxy=dxy, tlt=tlt, hyg=hyg,
            vix=vix, copper=copper, eem=eem
        )
        print(f"      Flow regime: {flow_regime}  Score: {flow_score}")
    except Exception as e:
        print(f"      Flow regime error: {e}")
        flow_regime = "unknown"
        flow_score = 0

    # ── Compute SPY scores ────────────────────────────────────────────────────
    gex_val = spy_data.get("net_gex_b")
    # Count consecutive negative GEX days from CSV history
    neg_streak = 0
    try:
        if os.path.exists(OUTPUT_CSV):
            import csv as _csv
            with open(OUTPUT_CSV, newline="", encoding="utf-8") as _f:
                rows_hist = list(_csv.DictReader(_f))
            spy_rows = [r for r in rows_hist if r.get("ticker") == "SPY"]
            for _r in reversed(spy_rows):
                try:
                    _g = float(_r.get("net_gex_b", 0) or 0)
                    if _g < 0:
                        neg_streak += 1
                    else:
                        break
                except:
                    break
    except:
        pass

    signal  = compute_signal(
        gex_val, vix,
        rsi=technicals.get("spy_rsi_14"),
        term_structure=structure,
        neg_day_streak=neg_streak,
    )
    l1_ctx  = compute_l1_context(
        technicals.get("spy_above_200ma"),
        technicals.get("spy_rsi_14"),
        structure, skew, vix,
    )
    print("\n[+] Computing SPY confluence scores...")
    fear_score, bull_score, bear_score, score_label = compute_scores(
        gex=gex_val, vix=vix, rsi=technicals.get("spy_rsi_14"),
        term_structure=structure, skew=skew,
        above_200ma=technicals.get("spy_above_200ma"),
    )

    # ── Compute QQQ scores ────────────────────────────────────────────────────
    qqq_gex = qqq_data.get("net_gex_b")
    qqq_spot = qqq_data.get("spot_price")
    print("\n[+] Computing QQQ confluence scores...")
    qqq_fear, qqq_bull, qqq_bear = compute_qqq_scores(qqq_gex, vix)
    print(f"  QQQ GEX={qqq_gex}  fear={qqq_fear}  bull={qqq_bull}  bear={qqq_bear}")

    # ── Divergence signal ─────────────────────────────────────────────────────
    divergence = compute_divergence(bull_score, bear_score, qqq_bear, qqq_bull)
    print(f"  Divergence: {divergence}")

    row = {
        "date":            today,
        "ticker":          "SPY",
        "spot_price":      spy_data.get("spot_price"),
        "net_gex_b":       gex_val,
        "vix":             vix,
        "zero_gamma":      spy_data.get("zero_gamma"),
        "call_wall":       spy_data.get("call_wall"),
        "put_wall":        spy_data.get("put_wall"),
        "peak_gex_strike": spy_data.get("peak_gex_strike"),
        "max_pain":        spy_data.get("max_pain"),
        "pc_ratio":        spy_data.get("pc_ratio"),
        "spy_200ma":          technicals.get("spy_200ma"),
        "spy_above_200ma":    technicals.get("spy_above_200ma"),
        "spy_rsi_14":         technicals.get("spy_rsi_14"),
        "vix_3m":             vix_3m,
        "vix_term_spread":    spread,
        "vix_term_structure": structure,
        "skew_index":         skew,
        "fear_score":         fear_score,
        "bull_score":         bull_score,
        "bear_score":         bear_score,
        "score_label":        score_label,
        "qqq_spot":           qqq_spot,
        "qqq_gex_b":          qqq_gex,
        "qqq_fear_score":     qqq_fear,
        "qqq_bear_score":     qqq_bear,
        "qqq_bull_score":     qqq_bull,
        "qqq_divergence":     divergence,
        "yield_10y":          yield_10y,
        "vix9d":              vix9d_val,
        "vix9d_vix_ratio":    vix9d_ratio,
        "gold":               gold,
        "dxy":                dxy,
        "tlt":                tlt,
        "hyg":                hyg,
        "copper":             copper,
        "oil":                oil,
        "eem":                eem,
        "xlre":               xlre,
        "flow_regime":        flow_regime,
        "flow_score":         flow_score,
        "signal":             signal,
        "l1_context":         l1_ctx,
    }

    # ── Email ─────────────────────────────────────────────────────────────────
    def f(v):  return "$" + str(v) if v is not None else "---"
    def fg(v):
        if v is None: return "---"
        return ("+" if v >= 0 else "-") + "$" + str(abs(v)) + "B"
    def fb(v): return str(v) if v is not None else "---"
    def score_bar(s, w=10): return "|"*int(s) + "."*(w-int(s)) + f"  {s}/10"

    summary = (
        "\n+--------------------------------------------------+\n"
        "|  GEX Daily — " + today + "  " + now + "\n"
        "+--------------------------------------------------+\n"
        "|  SPY CONFLUENCE SCORES\n"
        "|  Fear : " + score_bar(fear_score) + "\n"
        "|  Bear : " + score_bar(bear_score) + "\n"
        "|  Bull : " + score_bar(bull_score) + "\n"
        "|  Label: " + score_label + "\n"
        "+--------------------------------------------------+\n"
        "|  QQQ GEX LAYER\n"
        "|  QQQ spot    :  " + f(qqq_spot) + "\n"
        "|  QQQ GEX     :  " + fg(qqq_gex) + "\n"
        "|  QQQ Fear    :  " + score_bar(qqq_fear) + "\n"
        "|  QQQ Bear    :  " + score_bar(qqq_bear) + "\n"
        "|  QQQ Bull    :  " + score_bar(qqq_bull) + "\n"
        "|  Divergence  :  " + divergence + "\n"
        "+--------------------------------------------------+\n"
        "|  SPY DATA\n"
        "|  Spot price  :  " + f(row["spot_price"]) + "\n"
        "|  Net GEX     :  " + fg(gex_val) + "\n"
        "|  VIX         :  " + fb(vix) + "\n"
        "|  Zero-gamma  :  " + f(row["zero_gamma"]) + "\n"
        "|  Call wall   :  " + f(row["call_wall"]) + "\n"
        "|  Put wall    :  " + f(row["put_wall"]) + "\n"
        "+--------------------------------------------------+\n"
        "|  LAYER 1\n"
        "|  200MA       :  " + f(row["spy_200ma"]) + "  (above: " + str(row["spy_above_200ma"]) + ")\n"
        "|  RSI-14      :  " + fb(row["spy_rsi_14"]) + "\n"
        "|  VIX3M       :  " + fb(vix_3m) + "\n"
        "|  VIX9D       :  " + fb(vix9d_val) + ("  (ratio " + str(vix9d_ratio) + ("  ⚠️ near-term spike" if vix9d_ratio and vix9d_ratio > 1.10 else "") + ")" if vix9d_ratio else "") + "\n"
        "|  10Y Yield   :  " + fb(yield_10y) + ("%" if yield_10y else "") + "\n"
        "|--------------------------------------------------" + "\n"
        "|  CROSS-ASSET FLOW" + "\n"
        "|  Flow regime :  " + str(flow_regime) + "\n"
        "|  Flow score  :  " + str(flow_score) + "/5\n"
        "|  Gold (GLD)  :  " + fb(gold) + "\n"
        "|  USD (DXY)   :  " + fb(dxy) + "\n"
        "|  Bonds (TLT) :  " + fb(tlt) + "\n"
        "|  Credit (HYG):  " + fb(hyg) + "\n"
        "|  Copper      :  " + fb(copper) + "\n"
        "|  Oil (USO)   :  " + fb(oil) + "\n"
        "|  EM (EEM)    :  " + fb(eem) + "\n"
        "|  Real Est    :  " + fb(xlre) + "\n"
        "|  Term spread :  " + fb(spread) + "  [" + (structure or "---") + "]\n"
        "|  SKEW        :  " + fb(skew) + "\n"
        "+--------------------------------------------------+\n"
        "|  Signal      :  " + signal + "\n"
        "|  Context     :  " + l1_ctx + "\n"
        "+--------------------------------------------------+\n"
    )

    print(summary)
    save_csv(row)

    # Signal-driven email subject flags
    if "STRONG BUY" in signal:
        fear_flag = " 🟢 STRONG BUY"
    elif "BUY WATCH" in signal:
        fear_flag = " 🟡 BUY WATCH"
    elif fear_score >= 8:
        fear_flag = " 🔴 BUY ZONE"
    elif fear_score >= 6:
        fear_flag = " ⚠️ WATCH"
    else:
        fear_flag = ""
    if "RED EXIT" in signal:
        bear_flag = " 🔴 EXIT"
    elif bear_score >= 7:
        bear_flag = " 🐻 EXIT"
    else:
        bear_flag = ""
    div_flag  = " ⚡ DIVERGENCE" if "DIVERGENCE" in divergence or "WARNING" in divergence else ""
    subject   = f"GEX {today} | SPY F{fear_score}/Be{bear_score}/Bu{bull_score} · QQQ F{qqq_fear}/Be{qqq_bear}/Bu{qqq_bull}{fear_flag}{bear_flag}{div_flag}"
    send_email(subject, summary)
    print("Done.")


if __name__ == "__main__":
    main()
