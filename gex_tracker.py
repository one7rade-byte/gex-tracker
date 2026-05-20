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
TICKER = "SPY"
EMAIL_FROM = "one7rade@gmail.com"
EMAIL_TO   = "one7rade@gmail.com"
EMAIL_PASS = os.environ.get("GMAIL_PASS", "")

GEX_URL = "https://www.insiderfinance.io/gamma-exposure/" + TICKER
VIX_URL = "https://query1.finance.yahoo.com/v8/finance/chart/%5EVIX?interval=1d&range=1d"

CSV_HEADERS = ["date","ticker","spot_price","net_gex_b","vix","zero_gamma",
               "call_wall","put_wall","peak_gex_strike","max_pain","pc_ratio","signal"]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


def fetch_vix():
    try:
        r = requests.get(VIX_URL, headers=HEADERS, timeout=10)
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
                    raw = m.group(1).replace(",","").replace("$","").strip()
                    try:
                        return float(raw)
                    except:
                        pass
            return None

        # Net GEX sign detection
        neg = re.search(r"negative net gamma of \$?([\d,\.]+)B", text, re.IGNORECASE)
        pos = re.search(r"positive net gamma of \$?([\d,\.]+)B", text, re.IGNORECASE)
        neg2 = re.search(r"Net GEX\s*\n\s*-\$?([\d,\.]+)B", text, re.IGNORECASE)
        pos2 = re.search(r"Net GEX\s*\n\s*\$?([\d,\.]+)B", text, re.IGNORECASE)

        if neg:
            try: result["net_gex_b"] = -float(neg.group(1).replace(",",""))
            except: pass
        elif pos:
            try: result["net_gex_b"] = float(pos.group(1).replace(",",""))
            except: pass
        elif neg2:
            try: result["net_gex_b"] = -float(neg2.group(1).replace(",",""))
            except: pass
        elif pos2:
            try: result["net_gex_b"] = float(pos2.group(1).replace(",",""))
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
        msg["To"] = EMAIL_TO
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))
        with smtplib.SMTP("smtp.gmail.com", 587) as s:
            s.starttls()
            s.login(EMAIL_FROM, EMAIL_PASS)
            s.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())
        print("Email sent to " + EMAIL_TO)
    except Exception as e:
        print("Email failed: " + str(e))


def main():
    today = date.today().strftime("%Y-%m-%d")
    now = datetime.now().strftime("%I:%M %p")

    print("====================================================")
    print("  GEX Daily Tracker  |  " + today + "  " + now)
    print("====================================================")

    print("\n[1/2] Fetching VIX...")
    vix = fetch_vix()
    print("      VIX = " + str(vix))

    print("\n[2/2] Fetching " + TICKER + " GEX...")
    gex_data = fetch_gex()

    gex_val = gex_data.get("net_gex_b")
    signal  = compute_signal(gex_val, vix)

    row = {
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
        "signal":          signal,
    }

    def f(v): return "$"+str(v) if v is not None else "---"
    def fg(v):
        if v is None: return "---"
        return ("+$" if v >= 0 else "-$") + str(abs(v)) + "B"

    summary = (
        "\n+--------------------------------------------------+\n"
        "|  " + TICKER + " GEX Summary - " + today + "  " + now + "\n"
        "+--------------------------------------------------+\n"
        "|  Spot price      :  " + f(row["spot_price"]) + "\n"
        "|  Net GEX         :  " + fg(gex_val) + "\n"
        "|  VIX             :  " + str(vix) + "\n"
        "|  Zero-gamma      :  " + f(row["zero_gamma"]) + "\n"
        "|  Call wall       :  " + f(row["call_wall"]) + "\n"
        "|  Put wall        :  " + f(row["put_wall"]) + "\n"
        "|  Peak GEX strike :  " + f(row["peak_gex_strike"]) + "\n"
        "|  Max pain        :  " + f(row["max_pain"]) + "\n"
        "|  P/C ratio       :  " + (str(row["pc_ratio"]) if row["pc_ratio"] else "---") + "\n"
        "+--------------------------------------------------+\n"
        "|  Signal: " + signal + "\n"
        "+--------------------------------------------------+\n"
        "\nPaste this into Claude to log it.\n"
    )

    print(summary)
    save_csv(row)
    send_email(TICKER + " GEX " + today + " - " + signal[:15], summary)
    print("Done.")


if __name__ == "__main__":
    main()
