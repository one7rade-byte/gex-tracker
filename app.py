import os
import threading
from flask import Flask, request
import requests

app = Flask(__name__)

TELEGRAM_TOKEN   = os.environ["TELEGRAM_TOKEN"]
GEMINI_API_KEY   = os.environ["GEMINI_API_KEY"]
ALLOWED_CHAT_ID  = os.environ.get("TELEGRAM_CHAT_ID")  # optional lockdown to just you

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
GEMINI_URL   = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent"

RAW_BASE = "https://raw.githubusercontent.com/one7rade-byte/gex-tracker/main"
DATA_SOURCES = {
    "SPY/QQQ daily GEX + VIX + macro log (gex_log.csv, ~5yr history)": f"{RAW_BASE}/gex_log.csv",
    "Regime signal log (regime_log.csv)": f"{RAW_BASE}/regime_log.csv",
    "Mag 7 opportunity scanner + squeeze signals (mag7_signals_log.csv)": f"{RAW_BASE}/mag7_signals_log.csv",
    "Latest daily intelligence report (intelligence_report.json)": f"{RAW_BASE}/intelligence_report.json",
}

def fetch_dashboard_context():
    """Pull the current dashboard data files so Gemini can ground its
    answer in real history instead of guessing. Fetched fresh every
    request so it's never stale; failures on one file don't block others."""
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

SYSTEM_PROMPT = (
    "You are the assistant for one7rade's SPY GEX Tracker, a personal market "
    "dashboard tracking SPY/QQQ gamma exposure (GEX), VIX, RSI, SKEW, VIX term "
    "structure, dealer positioning, cross-asset flow, and Magnificent 7 options "
    "signals, with roughly 5 years of daily history. "
    "Every request includes the current contents of the dashboard's real data "
    "files below — use them as ground truth for anything about specific dates, "
    "GEX/VIX levels, signals, scores, or historical patterns in this data. "
    "Combine that with your own general knowledge of markets, macro conditions, "
    "and financial news to give a complete, accurate, well-reasoned answer — "
    "don't limit yourself to only what's in the data, but don't contradict it "
    "either. If a question needs current news or price action beyond what's "
    "in the data or your knowledge, say so plainly rather than guessing. "
    "Always interpret ambiguous short terms (GEX, dip, wall, regime, buy zone) "
    "in this options/market-structure context, never other meanings. "
    "Answer like a knowledgeable trading assistant: concise, direct, no "
    "unnecessary hedging or disclaimers."
)

def ask_gemini(prompt):
    context = fetch_dashboard_context()
    full_prompt = f"{context}\n\n=== USER QUESTION ===\n{prompt}"

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

def send_message(chat_id, text):
    if len(text) > 4000:
        text = text[:4000] + "\n\n[truncated]"
    r = requests.post(f"{TELEGRAM_API}/sendMessage",
                       json={"chat_id": chat_id, "text": text}, timeout=15)
    if not r.ok:
        print(f"Telegram send failed: {r.status_code} {r.text}")

@app.route("/webhook", methods=["POST"])
def webhook():
    update = request.get_json(force=True)
    msg = update.get("message")
    if not msg or "text" not in msg:
        return "ok"

    chat_id = str(msg["chat"]["id"])
    if ALLOWED_CHAT_ID and chat_id != str(ALLOWED_CHAT_ID):
        return "ok"

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
