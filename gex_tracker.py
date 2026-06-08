import csv
import os
import re
import smtplib
from datetime import datetime, date
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

        neg  = re.search(r"negative net gamma of \$?([\d,\.]+)B", text, re.IGNORECASE)
        pos  = re.search(r"positive net gamma of \$?([\d,\.]+)B", text, re.IGNORECASE)
        neg2 = re.search(r"Net GEX\s*\n\s*-\$?([\d,\.]+)B", text, re.IGNORECASE)
        pos2 = re.search(r"Net GEX\s*\n\s*\$?([\d,\.]+)B", text, re.IGNORECASE)

        if neg:
            try: result["net_gex_b"] = -float(neg.group(1).replace(",", ""))
            except: pass
        elif pos:
            try: result["net_gex_b"] = float(pos.group(1).replace(",", ""))
            except: pass
        elif neg2:
            try: result["net_gex_b"] = -float(neg2.group(1).replace(",", ""))
            except: pass
        elif pos2:
            try: result["net_gex_b"] = float(pos2.group(1).replace(",", ""))
            except: pass

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

def compute_signal(gex, vix):
    if gex is None or vix is None:
        return "Unknown - check data"
    if gex < 0 and vix > 19.5:
        return "RED EXIT - neg GEX + VIX elevated"
    if gex < -5 and vix > 18:
        return "RED Watch - GEX deeply neg, VIX rising"
    if gex < 0:
        return "AMBER Caution - neg GEX, watch VIX"
    if gex > 10 and vix < 18:
        return "GREEN Strong hold - GEX high, vol suppressed"
    if gex > 0 and vix < 19:
        return "GREEN Hold - pos GEX, vol controlled"
    return "NEUTRAL - monitor"


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
    exists = os.path.isfile(OUTPUT_CSV)
    with open(OUTPUT_CSV, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_HEADERS, extrasaction="ignore")
        if not exists:
            w.writeheader()
        w.writerow(row)
    print("Saved -> " + OUTPUT_CSV)


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

def main():
    today = date.today().strftime("%Y-%m-%d")
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

    # ── Compute SPY scores ────────────────────────────────────────────────────
    gex_val = spy_data.get("net_gex_b")
    signal  = compute_signal(gex_val, vix)
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
        "|  Term spread :  " + fb(spread) + "  [" + (structure or "---") + "]\n"
        "|  SKEW        :  " + fb(skew) + "\n"
        "+--------------------------------------------------+\n"
        "|  Signal      :  " + signal + "\n"
        "|  Context     :  " + l1_ctx + "\n"
        "+--------------------------------------------------+\n"
    )

    print(summary)
    save_csv(row)

    fear_flag = " 🔴 BUY ZONE" if fear_score >= 8 else (" ⚠️ WATCH" if fear_score >= 6 else "")
    bear_flag = " 🐻 EXIT" if bear_score >= 7 else ""
    div_flag  = " ⚡ DIVERGENCE" if "DIVERGENCE" in divergence or "WARNING" in divergence else ""
    subject   = f"GEX {today} | SPY F{fear_score}/Be{bear_score}/Bu{bull_score} · QQQ F{qqq_fear}/Be{qqq_bear}/Bu{qqq_bull}{fear_flag}{bear_flag}{div_flag}"
    send_email(subject, summary)
    print("Done.")


if __name__ == "__main__":
    main()
