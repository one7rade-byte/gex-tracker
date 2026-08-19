import os
from flask import Flask, request
import requests

app = Flask(__name__)

TELEGRAM_TOKEN   = os.environ["TELEGRAM_TOKEN"]
GEMINI_API_KEY   = os.environ["GEMINI_API_KEY"]
ALLOWED_CHAT_ID  = os.environ.get("TELEGRAM_CHAT_ID")  # optional lockdown to just you

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
GEMINI_API   = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"

def ask_gemini(prompt):
    r = requests.post(GEMINI_API, json={
        "contents": [{"parts": [{"text": prompt}]}]
    }, timeout=30)
    r.raise_for_status()
    return r.json()["candidates"][0]["content"]["parts"][0]["text"]

def send_message(chat_id, text):
    requests.post(f"{TELEGRAM_API}/sendMessage",
                  json={"chat_id": chat_id, "text": text}, timeout=15)

@app.route("/webhook", methods=["POST"])
def webhook():
    update = request.get_json(force=True)
    msg = update.get("message")
    if not msg or "text" not in msg:
        return "ok"

    chat_id = str(msg["chat"]["id"])
    if ALLOWED_CHAT_ID and chat_id != str(ALLOWED_CHAT_ID):
        return "ok"  # ignore anyone but you — protects your free quota

    try:
        reply = ask_gemini(msg["text"])
    except Exception as e:
        reply = f"Error: {e}"
    send_message(chat_id, reply)
    return "ok"

@app.route("/")
def health():
    return "bot alive"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
