"""
mag7_signals.py
────────────────
Pulls the Signals panel and Gamma Squeeze Screener from InsiderFinance for
each Mag 7 ticker. Unlike GEX/walls/zero-gamma (which are server-rendered
and scrapable via plain requests, see mag7_tracker.py), this section is
populated by client-side JavaScript after the initial page load — a raw
HTTP fetch only ever sees "Loading..." placeholders. This script uses a
headless browser (Playwright) to actually execute that JavaScript and wait
for real content before extracting it.

Heavier and slower than the other daily scripts (~5-15s per ticker just
for browser rendering, vs ~1s for a plain HTTP request), so this runs as
its own workflow rather than being folded into mag7_tracker.py.

Output: mag7_signals_log.csv (one row per ticker per day)

NOTE ON RELIABILITY: this was built without the ability to load the live
page from the dev sandbox (network egress restricted), so the text anchors
below are based on a real captured screenshot/HTML sample but have not
been verified against a live render. The first real run's logs should be
checked carefully — if extraction comes back empty for everything, the
DEBUG_DUMP block will print the raw rendered text so the anchors can be
corrected against what the page actually contains.
"""

import csv
import os
import re
import time
from datetime import date

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

OUTPUT_CSV = "mag7_signals_log.csv"
TICKERS = ["AAPL", "MSFT", "NVDA", "GOOGL", "META", "AMZN", "TSLA"]

CSV_HEADERS = [
    "date", "ticker",
    # Signals panel — up to 3 signals captured as a single pipe-delimited
    # summary string (type, strength, level) rather than separate columns,
    # since the number of signals varies day to day
    "signals_summary",
    # Bullish squeeze
    "bullish_squeeze_label",     # e.g. "possible", "unlikely", "likely", "imminent"
    "bullish_squeeze_score",     # 0-100
    # Bearish squeeze
    "bearish_squeeze_label",
    "bearish_squeeze_score",
]

DEBUG_DUMP = os.environ.get("MAG7_SIGNALS_DEBUG", "0") == "1"


def save_row(row):
    """Idempotent write keyed on (date, ticker) — replaces existing row
    instead of appending, same pattern as mag7_tracker.py / gex_tracker.py."""
    rows = []
    if os.path.isfile(OUTPUT_CSV):
        with open(OUTPUT_CSV, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))

    key = (row["date"], row["ticker"])
    replaced = False
    for i, r in enumerate(rows):
        if (r.get("date"), r.get("ticker")) == key:
            rows[i] = row
            replaced = True
            break
    if not replaced:
        rows.append(row)

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_HEADERS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def extract_signals_and_squeeze(page, ticker):
    """
    Waits for the Signals + Gamma Squeeze Screener section to finish
    client-side rendering, then extracts:
      - up to 3 signals (type, strength, trigger level)
      - bullish squeeze label + score
      - bearish squeeze label + score

    Returns a dict matching CSV_HEADERS (minus date/ticker).
    """
    result = {
        "signals_summary": None,
        "bullish_squeeze_label": None,
        "bullish_squeeze_score": None,
        "bearish_squeeze_label": None,
        "bearish_squeeze_score": None,
    }

    # Wait for the squeeze screener heading to appear in the DOM at all
    try:
        page.wait_for_selector("text=Gamma Squeeze Screener", timeout=20000)
    except PWTimeout:
        print(f"  {ticker}: 'Gamma Squeeze Screener' heading never appeared (20s timeout)")
        return result

    # The screener shows "Loading..." placeholders while data streams in.
    # Poll until those are gone (or give up after ~25s) rather than using
    # a single fixed sleep, since render time can vary.
    deadline = time.time() + 25
    while time.time() < deadline:
        body_text = page.inner_text("body")
        if "Loading..." not in body_text:
            break
        time.sleep(1)
    else:
        print(f"  {ticker}: page still showed 'Loading...' after 25s — extracting anyway")

    body_text = page.inner_text("body")

    if DEBUG_DUMP:
        print(f"  --- {ticker} RAW PAGE TEXT (debug dump) ---")
        print(body_text[:6000])
        print(f"  --- END {ticker} DUMP ---")

    # Signals: each one is rendered as a type ("volatility"/"support"),
    # a strength ("STRONG"/"MODERATE"/"WEAK"), a description, then an
    # "@ $price  pct%" trigger line. Capture up to 3.
    signal_pattern = re.compile(
        r"(volatility|support|resistance)\s*\n\s*(STRONG|MODERATE|WEAK)\s*\n([^\n]+)\n\s*@\s*\$?([\d,]+\.\d{2})([+-][\d,\.]+|0\.00)%",
        re.IGNORECASE,
    )
    signals_found = signal_pattern.findall(body_text)[:3]
    if signals_found:
        parts = []
        for sig_type, strength, desc, level, pct in signals_found:
            parts.append(f"{sig_type.upper()}/{strength.upper()} @ ${level} ({pct}%)")
        result["signals_summary"] = " | ".join(parts)

    # Bullish squeeze: "Bullish Squeeze\npossible\nProbability Score35/100"
    bull_match = re.search(
        r"Bullish Squeeze\s*\n\s*(\w+)\s*\nProbability Score\s*(\d+)\s*/\s*100",
        body_text, re.IGNORECASE,
    )
    if bull_match:
        result["bullish_squeeze_label"] = bull_match.group(1).lower()
        result["bullish_squeeze_score"] = int(bull_match.group(2))

    # Bearish squeeze: shown as "Bearish Squeeze\n25/100unlikely" (compact
    # alternate-setup format) based on the captured sample
    bear_match = re.search(
        r"Bearish Squeeze\s*\n\s*(\d+)\s*/\s*100\s*(\w+)",
        body_text, re.IGNORECASE,
    )
    if bear_match:
        result["bearish_squeeze_score"] = int(bear_match.group(1))
        result["bearish_squeeze_label"] = bear_match.group(2).lower()
    else:
        # Fallback: same layout as bullish, in case bearish is also shown
        # as "Bearish Squeeze\nunlikely\nProbability Score 25/100"
        bear_alt = re.search(
            r"Bearish Squeeze\s*\n\s*(\w+)\s*\nProbability Score\s*(\d+)\s*/\s*100",
            body_text, re.IGNORECASE,
        )
        if bear_alt:
            result["bearish_squeeze_label"] = bear_alt.group(1).lower()
            result["bearish_squeeze_score"] = int(bear_alt.group(2))

    return result


def main():
    today = date.today().isoformat()
    print(f"=== Mag 7 Signals + Squeeze Screener — {today} ===")

    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

        for ticker in TICKERS:
            print(f"\n--- {ticker} ---")
            page = context.new_page()
            try:
                url = f"https://www.insiderfinance.io/gamma-exposure/{ticker}"
                page.goto(url, timeout=30000, wait_until="domcontentloaded")
                data = extract_signals_and_squeeze(page, ticker)
                print(f"  Signals: {data['signals_summary']}")
                print(f"  Bullish: {data['bullish_squeeze_label']} "
                      f"({data['bullish_squeeze_score']}/100)")
                print(f"  Bearish: {data['bearish_squeeze_label']} "
                      f"({data['bearish_squeeze_score']}/100)")
            except Exception as e:
                print(f"  FAILED: {e}")
                data = {
                    "signals_summary": None,
                    "bullish_squeeze_label": None,
                    "bullish_squeeze_score": None,
                    "bearish_squeeze_label": None,
                    "bearish_squeeze_score": None,
                }
            finally:
                page.close()

            row = {"date": today, "ticker": ticker}
            row.update(data)
            save_row(row)
            results.append(row)

            # Be polite — real browser load is heavier on their server
            # than a plain HTTP request, so space these out more
            time.sleep(5)

        browser.close()

    print("\n=== Summary ===")
    for r in results:
        print(f"  {r['ticker']}: bullish={r['bullish_squeeze_score']}  "
              f"bearish={r['bearish_squeeze_score']}  "
              f"signals={'yes' if r['signals_summary'] else 'no'}")


if __name__ == "__main__":
    main()
