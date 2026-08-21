"""
market_scanner.py
──────────────────
Daily market-wide opportunity scanner — the "find opportunity anywhere,
not just the Mag 7" step in the roadmap.

Two-stage design, deliberately:

  Stage 1 (cheap, scales to the whole universe):
    - S&P 500 constituent list, fetched free from Wikipedia
    - 1-year price history per ticker (Yahoo) -> RSI-14, 200MA
    - IV + IV percentile for EVERY ticker in ONE request to
      optionstrategist.com (it serves the whole optionable-US-ticker
      universe in a single page — this is why IV can scale to 500
      names for free while GEX/P-C cannot, see stage 2)

  Stage 2 (expensive, deliberately narrow):
    - InsiderFinance's gamma-exposure page is one HTTP request PER
      TICKER. Hitting that 500x/day risks rate-limiting or an outright
      block, and most small/mid-cap names don't have liquid enough
      options markets to have meaningful GEX/P-C data there anyway.
    - So: rank all 500 by a stage-1-only score (RSI + IV percentile),
      then only fetch GEX/P-C for the top TOP_N candidates that
      already look interesting. Same per-run InsiderFinance load as
      scanning ~6x the Mag 7 list, not 70x the whole S&P 500.

Output:
  - market_scan_log.csv   — full history, ALL tickers, one row per
                            ticker per day (technical fields for
                            everyone; GEX/P-C/opportunity_score only
                            populated for the stage-2 subset). This
                            file is what lets RSI/IV percentile
                            rankings improve over time for every name,
                            not just today's top picks. NOT meant to
                            be fed to the Telegram bot directly — it
                            will grow to tens of thousands of rows a
                            year, far too large to hand an LLM on
                            every question.
  - market_scan_top.json  — small daily snapshot: today's date + the
                            ranked top opportunities with scores and
                            reasoning. THIS is what should be added to
                            the bot's data sources — same pattern as
                            intelligence_report.json vs
                            intelligence_log.csv already in this repo.
"""

import csv
import json
import os
import re
import time
from datetime import datetime, date
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

from signal_tiers import classify_and_size

LOG_CSV   = "market_scan_log.csv"
TOP_JSON  = "market_scan_top.json"

TOP_N_FOR_STAGE2 = 40   # how many stage-1 survivors get the expensive GEX/P-C fetch
TOP_N_IN_REPORT  = 20   # how many make it into the snapshot JSON

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json,text/html,*/*",
    "Accept-Language": "en-US,en;q=0.5",
}

LOG_CSV_HEADERS = [
    "date", "ticker",
    "spot_price", "rsi_14", "ma_200", "above_200ma",
    "rsi_pct", "iv_pct", "pc_pct",
    "iv_current", "pc_ratio",
    "gex_b", "gex_regime", "zero_gamma", "call_wall", "put_wall",
    "opportunity_score", "signal", "signal_detail",
    # Added later — symmetric buy/sell tier + sizing layer (signal_tiers.py),
    # on top of the one-directional opportunity_score above. Older rows
    # logged before this existed will just read blank for these columns.
    "conviction_score", "tier", "size_multiplier",
]


# ── Universe ──────────────────────────────────────────────────────────────────

def fetch_sp500_tickers():
    """Free, no-key S&P 500 constituent list from Wikipedia's sortable table.
    Converts tickers like BRK.B -> BRK-B to match Yahoo's naming convention.

    Wikipedia's constituents table has used id="constituents" for years (it's
    the example pandas.read_html() itself documents), but that's exactly the
    kind of detail a page redesign can quietly break. Try the known id first,
    then fall back to scanning every <table> on the page for one whose header
    row contains "Symbol" — a content-based match that survives an id/class
    rename, only breaking if the column layout itself changes."""
    try:
        url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
        r = requests.get(url, headers=HEADERS, timeout=20)
        soup = BeautifulSoup(r.text, "html.parser")

        table = soup.find("table", {"id": "constituents"})
        if not table:
            print("  'constituents' id not found, falling back to header-text search...")
            for candidate in soup.find_all("table"):
                header_row = candidate.find("tr")
                if header_row and "symbol" in header_row.get_text(strip=True).lower():
                    table = candidate
                    break

        if not table:
            print("  Could not locate S&P 500 table by id or header text")
            return []

        tickers = []
        for row in table.find_all("tr")[1:]:
            cells = row.find_all("td")
            if not cells:
                continue
            symbol = cells[0].get_text(strip=True).replace(".", "-")
            # Sanity check: real tickers are short, all-caps-ish alphanumeric
            if symbol and re.fullmatch(r"[A-Z0-9\-]{1,6}", symbol):
                tickers.append(symbol)

        if len(tickers) < 400:
            print(f"  WARNING: only found {len(tickers)} tickers — expected ~500, "
                  f"table structure may have changed; check output before trusting it")
        return tickers
    except Exception as e:
        print(f"  S&P 500 list fetch failed: {e}")
        return []


# ── Yahoo Finance (per-ticker, but cheap/reliable) ───────────────────────────

def yf_fetch_history(ticker, period="1y"):
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


def calc_rsi(closes, period=14):
    if len(closes) < period + 1:
        return None
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [max(d, 0) for d in deltas[-period:]]
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
    if not series or value is None:
        return None
    valid = [x for x in series if x is not None]
    if not valid:
        return None
    below = sum(1 for x in valid if x <= value)
    return round((below / len(valid)) * 100, 1)


# ── optionstrategist.com — ONE fetch covers every ticker we ask for ─────────

def fetch_optionstrategist_iv(tickers):
    """See mag7_tracker.py for the full history of why this parsing looks
    the way it does (HTML-entity decoding, tag stripping, \\r line endings).
    Kept identical here on purpose rather than importing, so this script
    stays a self-contained, independently runnable file like the other
    scanners in this repo."""
    import html as _html

    url = "https://www.optionstrategist.com/calculators/free-volatility-data"
    result = {}
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        text = _html.unescape(r.text)
        text = re.sub(r"<[^>]+>", "", text)
        text = text.replace("\r\n", "\n").replace("\r", "\n")

        pattern = re.compile(
            r"^([A-Z]+)\s+.*?(\d{6})\s+([\d.]+)\s+(\d+)/\s*(\d+)%ile\s+([\d.]+)\s*$",
            re.MULTILINE,
        )
        wanted = set(tickers)
        for m in pattern.finditer(text):
            symbol, as_of, cur_iv, days, pctile, close = m.groups()
            if symbol in wanted:
                try:
                    result[symbol] = {"iv": float(cur_iv), "iv_pct": int(pctile)}
                except ValueError:
                    continue
        print(f"  optionstrategist.com: matched {len(result)}/{len(wanted)} tickers")
    except Exception as e:
        print(f"  optionstrategist.com fetch failed: {e}")
    return result


# ── InsiderFinance — one request PER ticker, so kept to the stage-2 subset ──

def fetch_insiderfinance_data(ticker):
    result = {
        "gex_b": None, "gex_regime": "unknown", "pc_ratio": None,
        "zero_gamma": None, "call_wall": None, "put_wall": None,
    }
    try:
        url = "https://www.insiderfinance.io/gamma-exposure/" + ticker
        r = requests.get(url, headers=HEADERS, timeout=20)
        soup = BeautifulSoup(r.text, "html.parser")
        text = soup.get_text(separator="\n")

        def find_val(patterns):
            for pat in patterns:
                m = re.search(pat, text, re.IGNORECASE | re.DOTALL)
                if m:
                    raw = m.group(1).replace(",", "").replace("$", "").strip()
                    try:
                        return float(raw)
                    except ValueError:
                        pass
            return None

        def parse_dollar_amount(value_str, unit):
            try:
                v = float(value_str.replace(",", ""))
            except ValueError:
                return None
            return v if unit.upper() == "B" else round(v / 1000, 3)

        tile = re.search(r"Net GEX\s*\n\s*(-?)\$?([\d,\.]+)(M|B)", text, re.IGNORECASE)
        narrative = re.search(r"(positive|negative) net gamma of \$?([\d,\.]+)(M|B)", text, re.IGNORECASE)

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

        result["call_wall"]  = find_val([r"Call Wall[:\s\n]*\$?([\d,\.]+)"])
        result["put_wall"]   = find_val([r"Put Wall[:\s\n]*\$?([\d,\.]+)"])
        result["zero_gamma"] = find_val([r"Zero.Gamma Level[:\s\n]*\$?([\d,\.]+)", r"Zero Gamma[:\s\n]*\$?([\d,\.]+)"])

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


# ── Scoring — same shape as mag7_tracker.py's compute_opportunity_score ─────

def compute_opportunity_score(rsi_pct, iv_pct, pc_pct, gex_regime, above_200ma, rsi_raw):
    score = 0
    detail = []

    if rsi_pct is not None:
        if rsi_pct <= 10:
            score += 3; detail.append(f"RSI extremely oversold (bottom {rsi_pct:.0f}% of own history)")
        elif rsi_pct <= 20:
            score += 2; detail.append(f"RSI very oversold (bottom {rsi_pct:.0f}% of own history)")
        elif rsi_pct <= 35:
            score += 1; detail.append(f"RSI oversold (bottom {rsi_pct:.0f}% of own history)")
    elif rsi_raw is not None:
        if rsi_raw < 30:   score += 3; detail.append(f"RSI absolute oversold ({rsi_raw})")
        elif rsi_raw < 40: score += 2; detail.append(f"RSI weak ({rsi_raw})")
        elif rsi_raw < 50: score += 1; detail.append(f"RSI below midline ({rsi_raw})")

    if iv_pct is not None:
        if iv_pct <= 20:
            score += 2; detail.append(f"Options cheap (IV bottom {iv_pct:.0f}% of own history)")
        elif iv_pct <= 40:
            score += 1; detail.append(f"Options moderately priced (IV {iv_pct:.0f}th pct)")

    if pc_pct is not None:
        if pc_pct >= 80:
            score += 2; detail.append(f"Heavy put buying (P/C top {100-pc_pct:.0f}% of history) — contrarian buy")
        elif pc_pct >= 60:
            score += 1; detail.append(f"Elevated put buying (P/C {pc_pct:.0f}th pct)")

    if gex_regime == "deeply_negative":
        score += 1; detail.append("GEX deeply negative — amplified moves, squeeze potential")
    elif gex_regime == "negative":
        score += 1; detail.append("GEX negative — unstable, watch for stabilization")
    elif gex_regime == "strongly_positive":
        score += 2; detail.append("GEX strongly positive — dealers stabilizing")
    elif gex_regime == "positive":
        score += 1; detail.append("GEX positive — dealers providing support")

    if above_200ma is True:
        score += 1; detail.append("Above 200MA — uptrend intact")
    elif above_200ma is False:
        detail.append("Below 200MA — downtrend, scale in slowly")

    score = min(10, score)
    if score >= 8:   signal = "STRONG BUY — macro dip on intact name"
    elif score >= 6: signal = "BUY — oversold, good loading zone"
    elif score >= 4: signal = "WATCH — setup building, not quite ready"
    elif score >= 2: signal = "NEUTRAL — no edge, wait"
    else:            signal = "AVOID — not oversold or fear is company-specific"

    return score, signal, " | ".join(detail)


# ── History (for percentile ranking) ─────────────────────────────────────────

def load_existing_history(tickers):
    history = {t: {"rsi": [], "iv": []} for t in tickers}
    if not os.path.isfile(LOG_CSV):
        return history
    with open(LOG_CSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            t = row.get("ticker")
            if t not in history:
                continue
            def sf(k):
                try: return float(row[k]) if row.get(k) else None
                except ValueError: return None
            if sf("rsi_14") is not None: history[t]["rsi"].append(sf("rsi_14"))
            if sf("iv_current") is not None: history[t]["iv"].append(sf("iv_current"))
    return history


def save_log_rows(rows):
    """Append today's rows for every ticker, collapsing any stale duplicates
    for (date, ticker) the same way mag7_tracker.py / gex_tracker.py do."""
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


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    today = datetime.now(ZoneInfo("America/New_York")).date().strftime("%Y-%m-%d")
    print(f"Market scan — {today}")

    tickers = fetch_sp500_tickers()
    print(f"Universe: {len(tickers)} tickers")
    if not tickers:
        print("No tickers fetched, aborting.")
        return

    history = load_existing_history(tickers)

    print("Stage 1: fetching IV data for whole universe (one request)...")
    iv_data = fetch_optionstrategist_iv(tickers)

    print("Stage 1: fetching price history + RSI/200MA per ticker...")
    stage1 = {}
    for i, tk in enumerate(tickers):
        closes = yf_fetch_history(tk)
        if not closes:
            continue
        rsi = calc_rsi(closes)
        ma200 = calc_ma(closes, 200)
        spot = closes[-1]
        iv_info = iv_data.get(tk, {})
        iv_cur = iv_info.get("iv")
        iv_pct_precomputed = iv_info.get("iv_pct")  # optionstrategist gives its own 600-day pct

        rsi_pct = compute_percentile(rsi, history[tk]["rsi"])
        stage1[tk] = {
            "spot": spot, "rsi": rsi, "ma200": ma200,
            "above_200ma": spot > ma200 if ma200 else None,
            "rsi_pct": rsi_pct, "iv_current": iv_cur, "iv_pct": iv_pct_precomputed,
        }
        if (i + 1) % 50 == 0:
            print(f"  ...{i+1}/{len(tickers)} processed")
        time.sleep(0.3)

    print(f"Stage 1 complete: {len(stage1)}/{len(tickers)} tickers have usable data")

    # Rank by a stage-1-only proxy score (RSI + IV percentile) to pick
    # who gets the expensive stage-2 GEX/P-C fetch.
    def stage1_rank_key(item):
        tk, d = item
        s = 0
        if d["rsi_pct"] is not None:
            s += max(0, 40 - d["rsi_pct"])   # lower RSI pct = more oversold = higher score
        elif d["rsi"] is not None:
            s += max(0, 50 - d["rsi"])
        if d["iv_pct"] is not None:
            s += max(0, 30 - d["iv_pct"]) * 0.5
        return s

    ranked_stage1 = sorted(stage1.items(), key=stage1_rank_key, reverse=True)
    stage2_candidates = [tk for tk, _ in ranked_stage1[:TOP_N_FOR_STAGE2]]

    print(f"Stage 2: fetching GEX/P-C for top {len(stage2_candidates)} candidates...")
    final_rows = []
    scored = []
    for tk in stage2_candidates:
        d = stage1[tk]
        gex_data = fetch_insiderfinance_data(tk)
        # No accumulated P/C history yet in this new log for percentile —
        # bootstrap with raw thresholds the same way mag7_tracker.py did
        # originally; percentiles will kick in as history accumulates.
        pc_ratio = gex_data.get("pc_ratio")
        pc_pct = None  # left for a future pass once pc history accumulates

        score, signal, detail = compute_opportunity_score(
            d["rsi_pct"], d["iv_pct"], pc_pct, gex_data["gex_regime"], d["above_200ma"], d["rsi"]
        )
        conviction_score, tier, size_multiplier, _tier_note = classify_and_size(
            rsi_raw=d["rsi"], rsi_pct=d["rsi_pct"], iv_pct=d["iv_pct"],
            gex_regime=gex_data["gex_regime"], above_200ma=d["above_200ma"],
        )
        row = {
            "date": today, "ticker": tk,
            "spot_price": d["spot"], "rsi_14": d["rsi"], "ma_200": d["ma200"],
            "above_200ma": d["above_200ma"],
            "rsi_pct": d["rsi_pct"], "iv_pct": d["iv_pct"], "pc_pct": pc_pct,
            "iv_current": d["iv_current"], "pc_ratio": pc_ratio,
            "gex_b": gex_data["gex_b"], "gex_regime": gex_data["gex_regime"],
            "zero_gamma": gex_data["zero_gamma"], "call_wall": gex_data["call_wall"],
            "put_wall": gex_data["put_wall"],
            "opportunity_score": score, "signal": signal, "signal_detail": detail,
            "conviction_score": conviction_score, "tier": tier, "size_multiplier": size_multiplier,
        }
        final_rows.append(row)
        scored.append(row)
        time.sleep(0.5)

    # Everyone else in the universe still gets a technical-only row, so
    # RSI/IV percentile history builds up for the WHOLE universe over
    # time, not just today's top 40.
    for tk, d in stage1.items():
        if tk in stage2_candidates:
            continue
        # No GEX/P-C for these (never fetched — see stage 2 note above), but
        # RSI + IV percentile alone are still enough for a technical-only
        # conviction/tier read, so every S&P 500 name gets a signal, not just
        # today's top 40. Naturally weaker conviction than a stage-2 row
        # (fewer inputs feed it) — that's expected, not a bug.
        conviction_score, tier, size_multiplier, _tier_note = classify_and_size(
            rsi_raw=d["rsi"], rsi_pct=d["rsi_pct"], iv_pct=d["iv_pct"],
            gex_regime=None, above_200ma=d["above_200ma"],
        )
        final_rows.append({
            "date": today, "ticker": tk,
            "spot_price": d["spot"], "rsi_14": d["rsi"], "ma_200": d["ma200"],
            "above_200ma": d["above_200ma"],
            "rsi_pct": d["rsi_pct"], "iv_pct": d["iv_pct"], "pc_pct": None,
            "iv_current": d["iv_current"], "pc_ratio": None,
            "gex_b": None, "gex_regime": "not_scanned", "zero_gamma": None,
            "call_wall": None, "put_wall": None,
            "opportunity_score": None, "signal": "", "signal_detail": "",
            "conviction_score": conviction_score, "tier": tier, "size_multiplier": size_multiplier,
        })

    save_log_rows(final_rows)

    top = sorted(scored, key=lambda r: r["opportunity_score"] or 0, reverse=True)[:TOP_N_IN_REPORT]
    report = {
        "date": today,
        "universe_size": len(tickers),
        "stage2_scanned": len(stage2_candidates),
        "top_opportunities": [
            {
                "ticker": r["ticker"], "score": r["opportunity_score"], "signal": r["signal"],
                "detail": r["signal_detail"], "spot_price": r["spot_price"],
                "rsi_14": r["rsi_14"], "gex_regime": r["gex_regime"],
                "tier": r["tier"], "conviction_score": r["conviction_score"],
                "size_multiplier": r["size_multiplier"],
            }
            for r in top
        ],
    }
    with open(TOP_JSON, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"Wrote {TOP_JSON} — top {len(top)} opportunities out of {len(scored)} scanned")


if __name__ == "__main__":
    main()
