import os
import re
import time
import threading
from datetime import datetime
from zoneinfo import ZoneInfo
from flask import Flask, request
import requests

app = Flask(__name__)

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent"

RAW_BASE = "https://raw.githubusercontent.com/one7rade-byte/gex-tracker/main"

NEWS_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/json,*/*",
}

MAX_TOOL_ROUNDS = 5  # safety cap on tool-call back-and-forth per question

# ---------------------------------------------------------------------------
# Raw fetch helpers — these do the actual HTTP work. Tools below call these.
# ---------------------------------------------------------------------------

def fetch_csv_tail(url, days=30):
    """Fetch a CSV and return only the header + last `days` data rows,
    instead of dumping the whole growing file into every request."""
    try:
        r = requests.get(f"{url}?t={os.urandom(4).hex()}", timeout=15)
        if not r.ok:
            return f"[unavailable: HTTP {r.status_code}]"
        lines = r.text.strip().split("\n")
        if len(lines) <= 1:
            return r.text
        header, rows = lines[0], lines[1:]
        tail = rows[-days:] if days and days > 0 else rows
        return "\n".join([header] + tail)
    except Exception as e:
        return f"[unavailable: {e}]"

def fetch_json(url):
    try:
        r = requests.get(f"{url}?t={os.urandom(4).hex()}", timeout=15)
        if not r.ok:
            return f"[unavailable: HTTP {r.status_code}]"
        return r.text
    except Exception as e:
        return f"[unavailable: {e}]"

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
CALENDAR_CACHE_TTL = 20 * 60

def fetch_economic_calendar():
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
            actual, forecast, previous = e.get("actual", ""), e.get("forecast", ""), e.get("previous", "")
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

# ---------------------------------------------------------------------------
# Tools — one function per data source, each callable by Gemini on demand.
# ---------------------------------------------------------------------------

def tool_get_gex_data(days=30):
    return fetch_csv_tail(f"{RAW_BASE}/gex_log.csv", days)

def tool_get_regime_data(days=30):
    return fetch_csv_tail(f"{RAW_BASE}/regime_log.csv", days)

def tool_get_mag7_signals(days=30):
    return fetch_csv_tail(f"{RAW_BASE}/mag7_signals_log.csv", days)

def tool_get_intelligence_report():
    return fetch_json(f"{RAW_BASE}/intelligence_report.json")

def tool_get_signal_performance():
    return fetch_json(f"{RAW_BASE}/signal_performance_summary.json")

def tool_get_sector_rotation():
    return fetch_json(f"{RAW_BASE}/sector_rotation_top.json")

def tool_get_ticker_news(ticker):
    items = fetch_ticker_news(ticker.upper())
    return "\n".join(items) if items else f"[no recent news found for {ticker}]"

def tool_get_macro_news():
    items = fetch_macro_news()
    return "\n".join(items) if items else "[no macro headlines available]"

def tool_get_economic_calendar():
    return fetch_economic_calendar()

TOOL_DISPATCH = {
    "get_gex_data": lambda a: tool_get_gex_data(a.get("days", 30)),
    "get_regime_data": lambda a: tool_get_regime_data(a.get("days", 30)),
    "get_mag7_signals": lambda a: tool_get_mag7_signals(a.get("days", 30)),
    "get_intelligence_report": lambda a: tool_get_intelligence_report(),
    "get_signal_performance": lambda a: tool_get_signal_performance(),
    "get_sector_rotation": lambda a: tool_get_sector_rotation(),
    "get_ticker_news": lambda a: tool_get_ticker_news(a.get("ticker", "")),
    "get_macro_news": lambda a: tool_get_macro_news(),
    "get_economic_calendar": lambda a: tool_get_economic_calendar(),
}

GEMINI_TOOLS = [{
    "function_declarations": [
        {
            "name": "get_gex_data",
            "description": "SPY/QQQ daily gamma exposure (GEX), VIX, RSI, SKEW, and cross-asset macro log. Data starts 2026-03-30. Use for questions about current or recent GEX regime, dealer positioning, or SPY/QQQ options structure.",
            "parameters": {"type": "OBJECT", "properties": {
                "days": {"type": "INTEGER", "description": "Most recent trading days to return. Default 30."}
            }},
        },
        {
            "name": "get_regime_data",
            "description": "Daily regime signal log: composite score, flow_regime, regime_signal (e.g. STRONG_BUY, HOLD). Use for questions about the current market regime or how the signal has behaved recently.",
            "parameters": {"type": "OBJECT", "properties": {
                "days": {"type": "INTEGER", "description": "Most recent trading days to return. Default 30."}
            }},
        },
        {
            "name": "get_mag7_signals",
            "description": "Magnificent 7 opportunity scanner and squeeze signals, per ticker, over recent days.",
            "parameters": {"type": "OBJECT", "properties": {
                "days": {"type": "INTEGER", "description": "Most recent trading days to return. Default 30."}
            }},
        },
        {
            "name": "get_intelligence_report",
            "description": "Latest daily intelligence report summarizing today's overall market conditions.",
            "parameters": {"type": "OBJECT", "properties": {}},
        },
        {
            "name": "get_signal_performance",
            "description": "Real historical accuracy of each regime signal type — hit rate and average forward return at 5/10/20 trading days. Use this, never a guess, whenever asked how reliable a signal has been.",
            "parameters": {"type": "OBJECT", "properties": {}},
        },
        {
            "name": "get_sector_rotation",
            "description": "Today's money-flow/rotation read across 11 GICS sectors plus gold/bonds/dollar/credit/EM/small-caps/Bitcoin, vs SPY. LEADING/IMPROVING = money flowing toward; WEAKENING/LAGGING = money flowing away.",
            "parameters": {"type": "OBJECT", "properties": {}},
        },
        {
            "name": "get_ticker_news",
            "description": "Live recent news headlines for one specific stock ticker.",
            "parameters": {"type": "OBJECT", "properties": {
                "ticker": {"type": "STRING", "description": "Stock ticker symbol, e.g. AAPL"}
            }, "required": ["ticker"]},
        },
        {
            "name": "get_macro_news",
            "description": "Live macro/market headlines (Fed, earnings, economy) from Google News.",
            "parameters": {"type": "OBJECT", "properties": {}},
        },
        {
            "name": "get_economic_calendar",
            "description": "This week's economic calendar with High/Medium/Low impact ratings (red/orange/yellow folders) and actual/forecast/previous values where released.",
            "parameters": {"type": "OBJECT", "properties": {}},
        },
    ]
}]

SYSTEM_PROMPT = (
    "You are the assistant for one7rade's SPY GEX Tracker, a public market "
    "dashboard tracking SPY/QQQ gamma exposure (GEX), VIX, RSI, SKEW, VIX term "
    "structure, dealer positioning, cross-asset flow, and Magnificent 7 options "
    "signals. The daily history log started 2026-03-30 and grows by one "
    "trading day every day the tracker runs — always describe its depth as "
    "'since inception' or by the actual date range in the data, never guess "
    "a round number like '5 years'. "
    "\n\n"
    "You have tools to pull the dashboard's real data on demand — call "
    "whichever ones are actually relevant to the question, not all of them. "
    "Don't guess at numbers a tool could give you exactly. If a question "
    "doesn't need any tool (e.g. general market education), just answer. "
    "\n\n"
    "Always interpret ambiguous short terms (GEX, dip, wall, regime, buy "
    "zone) in this options/market-structure context, never other meanings. "
    "Combine tool results with your own general knowledge of markets, macro "
    "conditions, and financial history for a complete, accurate answer — "
    "don't limit yourself to only what tools return, but don't contradict "
    "them either. If something needs info you truly don't have (a release "
    "that hasn't happened yet, a specific social media post), say so "
    "plainly rather than guessing or inventing a source. "
    "\n\n"
    "FORMATTING — this is a Telegram chat, not a report: write like you're "
    "texting a knowledgeable friend. Keep it short — a few sentences to a "
    "short paragraph for simple questions, at most 3-4 short sections for "
    "genuinely complex ones. Never use markdown headers (#, ##, ###). Never "
    "use double-asterisk bold (**text**) — for emphasis use single asterisks "
    "(*text*) sparingly. Avoid long bullet lists; prefer plain conversational "
    "sentences. No em-dash section dividers (---). Get to the point fast. "
    "This is not financial advice — give the analysis and let them decide, "
    "without excessive disclaimers."
)

# ---------------------------------------------------------------------------
# Gemini call + tool-dispatch loop
# ---------------------------------------------------------------------------

def call_gemini(contents):
    r = requests.post(
        GEMINI_URL,
        headers={"x-goog-api-key": GEMINI_API_KEY, "Content-Type": "application/json"},
        json={
            "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": contents,
            "tools": GEMINI_TOOLS,
        },
        timeout=60,
    )
    if not r.ok:
        raise RuntimeError(f"{r.status_code}: {r.text[:500]}")
    return r.json()

def ask_gemini(user_question):
    now_et = datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d %H:%M %Z")
    opening = f"Current date/time: {now_et}\n\nUser question: {user_question}"
    contents = [{"role": "user", "parts": [{"text": opening}]}]

    tools_called = []

    for _ in range(MAX_TOOL_ROUNDS):
        data = call_gemini(contents)
        candidate = data["candidates"][0]
        parts = candidate["content"]["parts"]

        function_calls = [p["functionCall"] for p in parts if "functionCall" in p]
        if not function_calls:
            text = "".join(p.get("text", "") for p in parts if "text" in p)
            return text, tools_called

        contents.append({"role": "model", "parts": parts})

        response_parts = []
        for fc in function_calls:
            name, args = fc.get("name"), fc.get("args", {}) or {}
            fn = TOOL_DISPATCH.get(name)
            try:
                result = fn(args) if fn else f"[unknown tool: {name}]"
            except Exception as e:
                result = f"[tool error: {e}]"
            tools_called.append({"name": name, "args": args})
            response_parts.append({"functionResponse": {"name": name, "response": {"result": result}}})

        # FIX: Gemini's REST API does not accept role "function" — it must
        # be "user" when sending functionResponse parts back to the model.
        contents.append({"role": "user", "parts": response_parts})

    return "I gathered a lot of data but couldn't settle on an answer — try rephrasing.", tools_called

# ---------------------------------------------------------------------------
# Telegram plumbing (unchanged)
# ---------------------------------------------------------------------------

def send_typing(chat_id):
    try:
        requests.post(f"{TELEGRAM_API}/sendChatAction", json={"chat_id": chat_id, "action": "typing"}, timeout=10)
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
                       json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}, timeout=15)
    if not r.ok:
        print(f"Telegram send (markdown) failed: {r.status_code} {r.text}")
        r2 = requests.post(f"{TELEGRAM_API}/sendMessage", json={"chat_id": chat_id, "text": text}, timeout=15)
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
        reply, tools_called = ask_gemini(msg["text"])
        print(f"[{chat_id}] tools used: {[t['name'] for t in tools_called]}")
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
