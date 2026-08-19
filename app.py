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

def send_typing(chat_id):
    try:
        requests.post(f"{TELEGRAM_API}/sendChatAction",
                      json={"chat_id": chat_id, "action": "typing"}, timeout=10)
    except Exception as e:
        print(f"typing indicator failed: {e}")

def keep_typing(chat_id, stop_event):
    # Telegram's "typing..." only lasts ~5s, so keep refreshing it
    # every 4s until the Gemini call finishes (or fails).
    while not stop_event.is_set():
        send_typing(chat_id)
        stop_event.wait(4)

def ask_gemini(prompt):
    r = requests.post(
        GEMINI_URL,
        headers={
            "x-goog-api-key": GEMINI_API_KEY,
            "Content-Type": "application/json",
        },
        json={"contents": [{"parts": [{"text": prompt}]}]},
        timeout=45,
    )
    if not r.ok:
        raise RuntimeError(f"{r.status_code}: {r.text[:500]}")
    return r.json()["candidates"][0]["content"]["parts"][0]["text"]

def send_message(chat_id, text):
    # Telegram caps a single message at 4096 chars — truncate to be safe
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
        return "ok"  # ignore anyone but you — protects your free quota

    # Show "typing..." right away and keep it alive while Gemini thinks,
    # so the chat never looks frozen or broken.
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
