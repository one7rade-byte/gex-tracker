import csv
import json
import os
import re
import smtplib
from datetime import datetime, date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import requests
from bs4 import BeautifulSoup

OUTPUT_CSV = "gex_log.csv"
TICKER     = "SPY"
EMAIL_FROM = "one7rade@gmail.com"
EMAIL_TO   = "one7rade@gmail.com"
EMAIL_PASS = os.environ.get("GMAIL_PASS", "")

GEX_URL = "https://www.insiderfinance.io/gamma-exposure/" + TICKER

# Yahoo Finance chart endpoints
def yf_url(symbol, period="1y", interval="1d"):
    sym = requests.utils.quote(symbol)
    return f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval={interval}&range={period}"

CSV_HEADERS = [
    "date", "ticker", "spot_price", "net_gex_b", "vix",
    "zero_gamma", "call_wall", "put_wall", "peak_gex_strike", "max_pain", "pc_ratio",
    # --- Layer 1 additions ---
    "spy_200ma", "spy_above_200ma", "spy_rsi_14",
    "vix_3m", "vix_term_spread", "vix_term_structure",
    "skew_index",
    # -------------------------
    "signal", "l1_context",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


# ── Existing fetchers ────────────────────────────────────────────────────────

def fetch_vix():
    try:
        r = requests.get(yf_url("%5EVIX", period="1d"), headers=HEADERS, timeout=10)
        data = r.json()
        price = data["chart"]["result"][0]["meta"]["regularMarketPrice"]
        return round(float(price), 2)
    except Exception as e:
        print("VIX fetch failed: " + str(e))
        return None


def fetch_gex():
    result = {}
    try:
        print("Fetching InsiderFinance...")
        r = requests.get(GEX_URL, headers=HEADERS, timeout=20)
        print("Status: " + str(r.status_code))

        soup = BeautifulSoup(r.text, "html.parser")
        text = soup.get_text(separator="\n")

        print("--- PAGE SAMPLE ---")
        print(text[:3000])
        print("--- END SAMPLE ---")

        def find_val(patterns, t):
            for pat in patterns:
                m = re.search(pat, t, re.IGNORECASE | re.DOTALL)
                if m:
                    raw = m.group(1).replace(",", "").replace("$", "").strip()
                    try:
                        return float(raw)
                    except:
                        pass
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

    except Exception as e:
        print("GEX fetch failed: " + str(e))

    return result


# ── Layer 1: new fetchers ────────────────────────────────────────────────────

def fetch_spy_technicals():
    """
    Returns spy_200ma, spy_above_200ma (bool), spy_rsi_14
    Uses ~200 trading days of daily closes from Yahoo Finance.
    """
    result = {"spy_200ma": None, "spy_above_200ma": None, "spy_rsi_14": None}
    try:
        r = requests.get(yf_url("SPY", period="1y", interval="1d"), headers=HEADERS, timeout=15)
        data = r.json()
        closes = data["chart"]["result"][0]["indicators"]["quote"][0]["close"]
        closes = [c for c in closes if c is not None]

        if len(closes) < 15:
            print("Not enough SPY history for technicals")
            return result

        # 200-day MA (use all available; may be < 200 on short history)
        ma_window = min(200, len(closes))
        ma200 = round(sum(closes[-ma_window:]) / ma_window, 2)
        spot  = closes[-1]

        # RSI-14
        deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
        gains  = [max(d, 0) for d in deltas[-14:]]
        losses = [abs(min(d, 0)) for d in deltas[-14:]]
        avg_gain = sum(gains) / 14
        avg_loss = sum(losses) / 14
        if avg_loss == 0:
            rsi = 100.0
        else:
            rs  = avg_gain / avg_loss
            rsi = round(100 - (100 / (1 + rs)), 2)

        result["spy_200ma"]       = ma200
        result["spy_above_200ma"] = spot > ma200
        result["spy_rsi_14"]      = rsi

        print(f"  200MA={ma200}  RSI={rsi}  Above200MA={spot > ma200}")
    except Exception as e:
        print("SPY technicals fetch failed: " + str(e))
    return result


def fetch_vix_term_structure():
    """
    Returns vix_3m, vix_term_spread (VIX3M - VIX), vix_term_structure label.
    Positive spread = contango (calm). Negative = backwardation (stress).
    """
    result = {"vix_3m": None, "vix_term_spread": None, "vix_term_structure": None}
    try:
        r = requests.get(yf_url("%5EVIX3M", period="1d"), headers=HEADERS, timeout=10)
        data = r.json()
        vix3m = data["chart"]["result"][0]["meta"]["regularMarketPrice"]
        vix3m = round(float(vix3m), 2)
        result["vix_3m"] = vix3m
        print(f"  VIX3M={vix3m}")
    except Exception as e:
        print("VIX3M fetch failed: " + str(e))
        return result

    return result  # spread computed in main() once VIX is known


def fetch_skew():
    """
    CBOE SKEW Index. >135 = elevated tail risk, <115 = low tail hedging.
    """
    try:
        r = requests.get(yf_url("%5ESKEW", period="1d"), headers=HEADERS, timeout=10)
        data = r.json()
        skew = data["chart"]["result"][0]["meta"]["regularMarketPrice"]
        skew = round(float(skew), 2)
        print(f"  SKEW={skew}")
        return skew
    except Exception as e:
        print("SKEW fetch failed: " + str(e))
        return None


# ── Signal logic ─────────────────────────────────────────────────────────────

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
    """
    Single plain-English sentence summarising what the Layer 1 data says
    about macro trend and risk backdrop.
    """
    parts = []

    # Trend
    if spy_above_200ma is True:
        parts.append("SPY above 200MA (uptrend intact)")
    elif spy_above_200ma is False:
        parts.append("SPY BELOW 200MA (downtrend warning)")

    # RSI
    if rsi is not None:
        if rsi < 30:
            parts.append(f"RSI oversold ({rsi})")
        elif rsi > 70:
            parts.append(f"RSI overbought ({rsi})")
        else:
            parts.append(f"RSI neutral ({rsi})")

    # VIX term structure
    if term_structure == "backwardation":
        parts.append("VIX in backwardation (stress elevated)")
    elif term_structure == "contango":
        parts.append("VIX in contango (calm)")

    # SKEW
    if skew is not None:
        if skew > 135:
            parts.append(f"SKEW elevated ({skew}) - tail hedging active")
        elif skew < 115:
            parts.append(f"SKEW low ({skew}) - minimal tail hedging")
        else:
            parts.append(f"SKEW normal ({skew})")

    return " | ".join(parts) if parts else "No context data"


# ── CSV helpers ───────────────────────────────────────────────────────────────

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
        msg["From"] = EMAIL_FROM
        msg["To"]   = EMAIL_TO
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

    print("\n[1/5] Fetching VIX...")
    vix = fetch_vix()
    print("      VIX = " + str(vix))

    print("\n[2/5] Fetching " + TICKER + " GEX...")
    gex_data = fetch_gex()

    print("\n[3/5] Fetching SPY technicals (200MA, RSI)...")
    technicals = fetch_spy_technicals()

    print("\n[4/5] Fetching VIX term structure (VIX3M)...")
    term_data = fetch_vix_term_structure()
    vix_3m     = term_data.get("vix_3m")
    if vix is not None and vix_3m is not None:
        spread    = round(vix_3m - vix, 2)
        structure = "contango" if spread > 0 else "backwardation"
    else:
        spread    = None
        structure = None
    print(f"      Term spread (VIX3M-VIX) = {spread}  [{structure}]")

    print("\n[5/5] Fetching SKEW index...")
    skew = fetch_skew()

    # ── Compute signals ───────────────────────────────────────────────────────
    gex_val  = gex_data.get("net_gex_b")
    signal   = compute_signal(gex_val, vix)
    l1_ctx   = compute_l1_context(
        technicals.get("spy_above_200ma"),
        technicals.get("spy_rsi_14"),
        structure,
        skew,
        vix,
    )

    row = {
        # Original fields
        "date":            today,
        "ticker":          TICKER,
        "spot_price":      gex_data.get("spot_price"),
        "net_gex_b":       gex_val,
        "vix":             vix,
        "zero_gamma":      gex_data.get("zero_gamma"),
        "call_wall":       gex_data.get("call_wall"),
        "put_wall":        gex_data.get("put_wall"),
        "peak_gex_strike": gex_data.get("peak_gex_strike"),
        "max_pain":        gex_data.get("max_pain"),
        "pc_ratio":        gex_data.get("pc_ratio"),
        # Layer 1 additions
        "spy_200ma":          technicals.get("spy_200ma"),
        "spy_above_200ma":    technicals.get("spy_above_200ma"),
        "spy_rsi_14":         technicals.get("spy_rsi_14"),
        "vix_3m":             vix_3m,
        "vix_term_spread":    spread,
        "vix_term_structure": structure,
        "skew_index":         skew,
        # Signal fields
        "signal":   signal,
        "l1_context": l1_ctx,
    }

    # ── Email summary ─────────────────────────────────────────────────────────
    def f(v):  return "$" + str(v) if v is not None else "---"
    def fg(v):
        if v is None: return "---"
        return ("+" if v >= 0 else "-") + "$" + str(abs(v)) + "B"
    def fb(v): return str(v) if v is not None else "---"

    summary = (
        "\n+--------------------------------------------------+\n"
        "|  " + TICKER + " GEX Summary - " + today + "  " + now + "\n"
        "+--------------------------------------------------+\n"
        "|  Spot price      :  " + f(row["spot_price"]) + "\n"
        "|  Net GEX         :  " + fg(gex_val) + "\n"
        "|  VIX             :  " + fb(vix) + "\n"
        "|  Zero-gamma      :  " + f(row["zero_gamma"]) + "\n"
        "|  Call wall       :  " + f(row["call_wall"]) + "\n"
        "|  Put wall        :  " + f(row["put_wall"]) + "\n"
        "|  Peak GEX strike :  " + f(row["peak_gex_strike"]) + "\n"
        "|  Max pain        :  " + f(row["max_pain"]) + "\n"
        "|  P/C ratio       :  " + (str(row["pc_ratio"]) if row["pc_ratio"] else "---") + "\n"
        "+--------------------------------------------------+\n"
        "|  LAYER 1 CONTEXT\n"
        "|  200MA           :  " + f(row["spy_200ma"]) + "  (above: " + str(row["spy_above_200ma"]) + ")\n"
        "|  RSI-14          :  " + fb(row["spy_rsi_14"]) + "\n"
        "|  VIX3M           :  " + fb(vix_3m) + "\n"
        "|  Term spread     :  " + fb(spread) + "  [" + (structure or "---") + "]\n"
        "|  SKEW            :  " + fb(skew) + "\n"
        "+--------------------------------------------------+\n"
        "|  Signal  : " + signal + "\n"
        "|  Context : " + l1_ctx + "\n"
        "+--------------------------------------------------+\n"
    )

    print(summary)
    save_csv(row)
    send_email(TICKER + " GEX " + today + " - " + signal[:20], summary)
    print("Done.")


if __name__ == "__main__":
    main()
