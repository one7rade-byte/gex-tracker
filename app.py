import os
import re
import time
import threading
from datetime import datetime
from zoneinfo import ZoneInfo
from flask import Flask, request
import requests

app = Flask(__name__)

TELEGRAM_TOKEN   = os.environ["TELEGRAM_TOKEN"]
GEMINI_API_KEY   = os.environ["GEMINI_API_KEY"]

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
GEMINI_URL   = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent"

RAW_BASE = "https://raw.githubusercontent.com/one7rade-byte/gex-tracker/main"
DATA_SOURCES = {
    "SPY/QQQ daily GEX + VIX + macro log (gex_log.csv, ~5yr history)": f"{RAW_BASE}/gex_log.csv",
    "Regime signal log (regime_log.csv)": f"{RAW_BASE}/regime_log.csv",
    "Mag 7 opportunity scanner + squeeze signals (mag7_signals_log.csv)": f"{RAW_BASE}/mag7_signals_log.csv",
    "Latest daily intelligence report (intelligence_report.json)": f"{RAW_BASE}/intelligence_report.json",
}

NEWS_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/json,*/*",
}

TICKER_STOPWORDS = {
    "I","A","ON","IF","OR","AND","THE","FOR","ARE","IS","BE","TO","OF","IN",
    "GEX","VIX","RSI","SKEW","CEO","CFO","IPO","ETF","FED","GDP","CPI","AI",
    "US","USA","UK","EU","OK","MA","MACD","ATH","YTD","EPS","PE","ER","Q1",
    "Q2","Q3","Q4","LOL","OMG","WTF","FYI","ASAP","DM","AM","PM","FOMC",
}

def extract_tickers(text):
    candidates = set(re.findall(r'\b[A-Z]{1,5}\b', text))
    return [t for t in candidates if t not in TICKER_STOPWORDS][:3]

def parse_rss_items(xml_text, max_items):
    headlines = []
    for item in re.findall(r'<item>(.*?)</item>', xml_text, re.DOTALL)[:max_items]:
        title = re.search(r'<title><!\[CDATA\[(.*?)\]\]></title>', item) or re.search(r'<title>(.*?)</title>', item)
        link  = re.search(r'<link>(.*?)</link>', item) or re.search(r'<guid>(.*?)</guid>', item)
        pub   = re.search(r'<pubDate>(.*?)</pubDate>', item)
        if title:
            t = re.sub(r'<.*?>', '', title.group(1)).strip()
            t = re.sub(r'\s*-\s*[A-Za-z0-9 .]+$', '', t).strip()
            l = link.group(1).strip() if link else ""
            p = pub.group(1).strip() if pub else ""
            headlines.append(f"- {t}" + (f" ({p})" if p else "") + (f" [{l}]" if l else ""))
    return headlines

def fetch_ticker_news(symbol, max_items=6):
    try:
        url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={symbol}&region=US&lang=en-US"
        r = requests.get(url, headers=NEWS_HEADERS, timeout=10)
        if not r.ok:
            return []
        return parse_rss_items(r.text, max_items)
    except Exception as e:
        print(f"ticker news fetch failed ({symbol}): {e}")
        return []

def fetch_macro_news(max_items=8):
    try:
        url = "https://news.google.com/rss/search?q=market+fed+earnings+economy+stocks&hl=en-US&gl=US&ceid=US:en"
        r = requests.get(url, headers=NEWS_HEADERS, timeout=10)
        if not r.ok:
            return []
        return parse_rss_items(r.text, max_items)
    except Exception as e:
        print(f"macro news fetch failed: {e}")
        return []

_calendar_cache = {"data": None, "fetched_at": 0}
CALENDAR_CACHE_TTL = 20 * 60  # refresh at most every 20 minutes

def fetch_economic_calendar():
    """Free, no-key weekly economic calendar — impact levels map to the
    classic red (High) / orange (Medium) / yellow (Low) folder colors.
    Cached for CALENDAR_CACHE_TTL to avoid hammering the feed and to
    survive occasional rate-limiting with a stale-but-usable copy."""
    now = time.time()
    if _calendar_cache["data"] and (now - _calendar_cache["fetched_at"] < CALENDAR_CACHE_TTL):
        return _calendar_cache["data"]
    try:
        r = requests.get("https://nfs.faireconomy.media/ff_calendar_thisweek.json",
                          headers=NEWS_HEADERS, timeout=12)
        if not r.ok:
            raise RuntimeError(f"HTTP {r.status_code}")
        events = r.json()
        lines = []
        for e in events:
            impact = e.get("impact", "")
            folder = {"High": "RED", "Medium": "ORANGE", "Low": "yellow"}.get(impact, impact)
            actual = e.get("actual", "")
            forecast = e.get("forecast", "")
            previous = e.get("previous", "")
            vals = f"actual={actual or '—'} forecast={forecast or '—'} previous={previous or '—'}"
            lines.append(f"- [{folder} folder] {e.get('date','')} | {e.get('country','')} | {e.get('title','')} | {vals}")
        result = "\n".join(lines) if lines else "[no events this week]"
        _calendar_cache["data"] = result
        _calendar_cache["fetched_at"] = now
        return result
    except Exception as e:
        print(f"calendar fetch failed: {e}")
        if _calendar_cache["data"]:
            return _calendar_cache["data"] + "\n[note: using a cached copy, live refresh just failed]"
        return f"[calendar unavailable: {e}]"

def fetch_dashboard_context():
    parts = []
    for label, url in DATA_SOURCES.items():
        try:
            r = requests.get(f"{url}?t={os.urandom(4).hex()}", timeout=15)
            if r.ok:
                parts.append(f"=== {label} ===\n{r.text}")
            else:
                parts.append(f"=== {label} ===\n[unavailable: HTTP {r.status_code}]")
        except Exception as e:
            parts.append(f"=== {label} ===\n[unavailable: {e}]")
    return "\n\n".join(parts)

def fetch_live_news_context(user_question):
    parts = []

    now_et = datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d %H:%M %Z")
    parts.append(f"=== Current date/time ===\n{now_et}")

    parts.append("=== This week's economic calendar (red=High impact, orange=Medium, yellow=Low) ===\n"
                  + fetch_economic_calendar())

    macro = fetch_macro_news()
    if macro:
        parts.append("=== Live macro/market headlines (Google News, recent) ===\n" + "\n".join(macro))

    for ticker in extract_tickers(user_question):
        items = fetch_ticker_news(ticker)
        if items:
            parts.append(f"=== Live news for {ticker} (Yahoo Finance, recent) ===\n" + "\n".join(items))

    return "\n\n".join(parts)

SYSTEM_PROMPT = (
    "You are the assistant for one7rade's SPY GEX Tracker, a public market "
    "dashboard tracking SPY/QQQ gamma exposure (GEX), VIX, RSI, SKEW, VIX term "
    "structure, dealer positioning, cross-asset flow, and Magnificent 7 options "
    "signals, with roughly 5 years of daily history. "
    "Every request includes: the dashboard's real data files, the current "
    "date/time, this week's economic calendar (with red/orange/yellow folder "
    "impact ratings — the same system traders mean by 'red folder news'), "
    "live macro headlines, and — when the question names a specific ticker — "
    "live news for that stock. Use all of this as ground truth, and use the "
    "current date/time to correctly identify what 'today' means among the "
    "week's calendar events. This news and calendar coverage is NOT limited "
    "to the Magnificent 7 — answer about any stock or any scheduled economic "
    "release (jobless claims, CPI, FOMC, NFP, etc.) using the provided data. "
    "Combine all of this with your own general knowledge of markets, macro "
    "conditions, and financial history for a complete, accurate answer — "
    "don't limit yourself to only what's provided, but don't contradict it "
    "either. If something needs info you truly don't have (e.g. a release "
    "that hasn't happened yet, or a specific social media post), say so "
    "plainly rather than guessing or inventing a source. "
    "Always interpret ambiguous short terms (GEX, dip, wall, regime, buy "
    "zone) in this options/market-structure context, never other meanings. "
    "\n\n"
    "FORMATTING — this is a Telegram chat, not a report: write like you're "
    "texting a knowledgeable friend, not drafting a document. Keep it short — "
    "a few sentences to a short paragraph for simple questions, at most 3-4 "
    "short sections for genuinely complex ones. Never use markdown headers "
    "(no #, ##, ###). Never use double-asterisk bold (**text**) — if you need "
    "to emphasize a key number or word, use single asterisks (*text*) and only "
    "for a handful of the most important terms, not most of the message. Avoid "
    "long bullet-point lists; prefer plain conversational sentences. No em-dash "
    "section dividers (---). Get to the point fast. This is not financial "
    "advice — give the analysis and let them decide, without excessive "
    "disclaimers."
)

def ask_gemini(user_question):
    dashboard_context = fetch_dashboard_context()
    news_context = fetch_live_news_context(user_question)
    full_prompt = (
        f"{dashboard_context}\n\n{news_context}\n\n=== USER QUESTION ===\n{user_question}"
    )

    r = requests.post(
        GEMINI_URL,
        headers={
            "x-goog-api-key": GEMINI_API_KEY,
            "Content-Type": "application/json",
        },
        json={
            "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": [{"parts": [{"text": full_prompt}]}],
        },
        timeout=60,
    )
    if not r.ok:
        raise RuntimeError(f"{r.status_code}: {r.text[:500]}")
    return r.json()["candidates"][0]["content"]["parts"][0]["text"]

def send_typing(chat_id):
    try:
        requests.post(f"{TELEGRAM_API}/sendChatAction",
                      json={"chat_id": chat_id, "action": "typing"}, timeout=10)
    except Exception as e:
        print(f"typing indicator failed: {e}")

def keep_typing(chat_id, stop_event):
    while not stop_event.is_set():
        send_typing(chat_id)
        stop_event.wait(4)

def clean_for_telegram(text):
    text = re.sub(r'^#{1,6}\s*(.+)$', r'*\1*', text, flags=re.MULTILINE)
    text = re.sub(r'\*\*(.+?)\*\*', r'*\1*', text)
    text = re.sub(r'^-{3,}\s*$', '', text, flags=re.MULTILINE)
    return text.strip()

def send_message(chat_id, text):
    text = clean_for_telegram(text)
    if len(text) > 4000:
        text = text[:4000] + "\n\n[truncated]"

    r = requests.post(f"{TELEGRAM_API}/sendMessage",
                       json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
                       timeout=15)
    if not r.ok:
        print(f"Telegram send (markdown) failed: {r.status_code} {r.text}")
        r2 = requests.post(f"{TELEGRAM_API}/sendMessage",
                            json={"chat_id": chat_id, "text": text}, timeout=15)
        if not r2.ok:
            print(f"Telegram send (plain) failed: {r2.status_code} {r2.text}")

@app.route("/webhook", methods=["POST"])
def webhook():
    update = request.get_json(force=True)
    msg = update.get("message")
    if not msg or "text" not in msg:
        return "ok"

    chat_id = str(msg["chat"]["id"])

    stop_typing = threading.Event()
    typing_thread = threading.Thread(target=keep_typing, args=(chat_id, stop_typing), daemon=True)
    typing_thread.start()

    try:
        reply = ask_gemini(msg["text"])
    except Exception as e:
        reply = f"Error: {e}"
        print(f"ask_gemini failed: {e}")
    finally:
        stop_typing.set()

    send_message(chat_id, reply)
    return "ok"

@app.route("/")
def health():
    return "bot alive"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
