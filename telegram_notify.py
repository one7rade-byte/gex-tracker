"""
telegram_notify.py
==================
Sends a daily market summary to Telegram.
Run 30 minutes after gex_tracker.py + regime_analyzer.py complete.

Message structure:
- Plain English summary (anyone can understand)
- Key numbers
- Signal context
- Optional deeper analysis section
"""

import csv
import json
import os
import requests
from datetime import datetime
from zoneinfo import ZoneInfo

# ── Config ────────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

GEX_CSV     = "gex_log.csv"
REGIME_CSV  = "regime_log.csv"
MAG7_CSV    = "mag7_signals_log.csv"

def n(v):
    try: return float(v) if v else None
    except: return None

# ── Load data ─────────────────────────────────────────────────────────────────

def load_latest_gex():
    if not os.path.exists(GEX_CSV): return {}
    with open(GEX_CSV, newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r.get("ticker","").strip()=="SPY"]
    return rows[-1] if rows else {}

def load_latest_regime():
    if not os.path.exists(REGIME_CSV): return {}
    with open(REGIME_CSV, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return rows[-1] if rows else {}

def load_mag7_signals():
    if not os.path.exists(MAG7_CSV): return []
    with open(MAG7_CSV, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    # Get latest date
    if not rows: return []
    latest_date = max(r.get("date","") for r in rows)
    return [r for r in rows if r.get("date","") == latest_date]

# ── Plain English generators ──────────────────────────────────────────────────

def plain_english_regime(signal, composite, hyg, vix, gex, rsi):
    """Generate a plain English summary anyone can understand."""

    # Main market status
    if signal == "STRONG_BUY":
        headline = "🟢 BUYING OPPORTUNITY — Act now"
        summary = (
            "The market has pulled back significantly while the financial system "
            "remains healthy. This is historically one of the best times to buy. "
            "Think of it like a sale at your favorite store — prices are down but "
            "the store is still open and profitable."
        )
        action = "📌 Action: Consider adding to long-term positions today."

    elif signal == "BUY_WATCH":
        headline = "🟡 SETUP BUILDING — Watch closely"
        summary = (
            "The market is pulling back and a buying opportunity may be forming. "
            "Not quite at peak entry conditions yet but getting close. "
            "Like watching a stock go on sale — wait for it to hit the right price."
        )
        action = "📌 Action: Monitor daily. Prepare to buy if conditions improve."

    elif signal == "STRONG_HOLD":
        headline = "🔵 STRONG HOLD — Stay the course"
        summary = (
            "The market is in maximum positive territory. Everything looks healthy — "
            "no signs of stress anywhere. This is not a time to buy (prices are elevated) "
            "or sell (the trend is still up). Just hold what you own."
        )
        action = "📌 Action: Hold all positions. Don't chase. Wait for next pullback."

    elif signal == "HOLD":
        headline = "🔵 HOLD — Positive regime"
        summary = (
            "Market conditions are positive and stable. No major risks visible right now. "
            "Not the best time to buy aggressively but no reason to sell either."
        )
        action = "📌 Action: Hold existing positions. Monitor for changes."

    elif signal == "CAUTION":
        if rsi and rsi > 70:
            headline = "⚠️ CAUTION — Market ran too fast"
            summary = (
                "The market has gone up a lot recently and is now 'overbought' — "
                "meaning it moved faster than normal and a pullback is likely. "
                "This is NOT a crash signal. Think of it like a rubber band stretched "
                "too far — it just needs to snap back a little before continuing up."
            )
            action = "📌 Action: Don't add new positions. Tighten stop losses."
        else:
            headline = "⚠️ CAUTION — Monitor closely"
            summary = (
                "Some mixed signals in the market. Nothing alarming but worth "
                "watching closely over the next few days."
            )
            action = "📌 Action: Hold positions. Reduce size on new trades."

    elif signal == "DEFENSIVE":
        headline = "🔴 DEFENSIVE — Credit stress detected"
        summary = (
            "The bond market is showing signs of stress. This is an early warning "
            "signal that something bigger might be coming. Not a full crash signal "
            "yet but time to be careful and reduce risk."
        )
        action = "📌 Action: Reduce exposure. Move to safer assets. Watch HYG closely."

    elif signal == "CRISIS":
        headline = "🚨 CRISIS — Extreme caution"
        summary = (
            "Credit markets are in serious stress. This is the pattern that preceded "
            "major crashes like 2008 and COVID. Protect capital first."
        )
        action = "📌 Action: Exit risky positions. Hold cash. Wait for credit to stabilize."

    else:
        headline = "⚪ NEUTRAL — Mixed signals"
        summary = "Market sending mixed signals. No clear direction."
        action = "📌 Action: Hold. Wait for clearer signal."

    return headline, summary, action


def format_credit_health(hyg):
    if hyg is None: return "—"
    if hyg > 79: return f"✅ HEALTHY (${hyg:.2f}) — All dips are buyable"
    if hyg > 76: return f"🟡 MILD STRESS (${hyg:.2f}) — Be selective"
    if hyg > 72: return f"🔴 STRESS (${hyg:.2f}) — Reduce risk"
    return f"🚨 CRISIS (${hyg:.2f}) — Exit positions"


def format_dollar(dxy):
    if dxy is None: return "—"
    if dxy > 104: return f"📈 RISING ({dxy:.2f}) — Cash hoarding, panic mode"
    if dxy < 100: return f"📉 FALLING ({dxy:.2f}) — Risk appetite, good for stocks"
    return f"➡️ NEUTRAL ({dxy:.2f}) — Calm"


def format_yield(y):
    if y is None: return "—"
    if y > 4.5: return f"⚠️ HIGH ({y:.2f}%) — Headwind for stocks"
    if y < 3.8: return f"✅ LOW ({y:.2f}%) — Tailwind for stocks"
    return f"➡️ NEUTRAL ({y:.2f}%)"


def format_mag7(mag7_rows):
    if not mag7_rows: return ""
    top = sorted(mag7_rows, key=lambda r: float(r.get("opportunity_score",0) or 0), reverse=True)
    lines = []
    for r in top[:3]:
        ticker = r.get("ticker","?")
        signal = r.get("signal","?")
        try:
            score = float(r.get("opportunity_score") or 0)
        except:
            score = 0
        if score >= 6:
            lines.append(f"  • {ticker}: Score {score:.0f}/10 — {signal}")
    if not lines: return ""
    return "\n🏢 Top MAG7 Opportunities:\n" + "\n".join(lines)


# ── Build message ─────────────────────────────────────────────────────────────

def build_message(gex, regime, mag7):
    today = datetime.now(ZoneInfo("America/New_York")).strftime("%b %d, %Y")

    # Extract values
    spy     = n(gex.get("spot_price"))
    gex_b   = n(gex.get("net_gex_b"))
    vix     = n(gex.get("vix"))
    rsi     = n(gex.get("spy_rsi_14"))
    hyg     = n(gex.get("hyg"))
    dxy     = n(gex.get("dxy"))
    gold    = n(gex.get("gold"))
    yield10y= n(gex.get("yield_10y"))
    call_w  = n(gex.get("call_wall"))
    put_w   = n(gex.get("put_wall"))
    copper  = n(gex.get("copper"))
    eem     = n(gex.get("eem"))

    signal    = regime.get("regime_signal","HOLD")
    composite = n(regime.get("composite_score")) or 0
    bs_watch  = regime.get("black_swan_watch","False") == "True"
    bs_reasons= regime.get("black_swan_reasons","")
    flow_reg  = regime.get("flow_regime","").replace("_"," ")

    # Get plain English
    headline, summary, action = plain_english_regime(signal, composite, hyg, vix, gex_b, rsi)

    # Black swan warning
    bs_text = ""
    if bs_watch:
        bs_text = f"\n\n⚠️⚠️ BLACK SWAN WATCH ⚠️⚠️\n{bs_reasons}"

    # GEX interpretation
    if gex_b is None:
        gex_text = "—"
    elif gex_b > 10:
        gex_text = f"+{gex_b:.1f}B 🟢 (dealers buying dips)"
    elif gex_b > 0:
        gex_text = f"+{gex_b:.1f}B 🟡 (mild positive)"
    elif gex_b > -5:
        gex_text = f"{gex_b:.1f}B 🟡 (mild negative)"
    elif gex_b > -10:
        gex_text = f"{gex_b:.1f}B 🔴 (dealers amplifying moves)"
    else:
        gex_text = f"{gex_b:.1f}B 🚨 (dealers maximally short)"

    # RSI interpretation
    if rsi is None:
        rsi_text = "—"
    elif rsi > 75:
        rsi_text = f"{rsi:.0f} ⚠️ Overbought — ran too fast"
    elif rsi < 30:
        rsi_text = f"{rsi:.0f} 🟢 Oversold — potential buy zone"
    elif rsi < 45:
        rsi_text = f"{rsi:.0f} 🟡 Neutral-low"
    else:
        rsi_text = f"{rsi:.0f} ✅ Normal"

    # MAG7
    mag7_text = format_mag7(mag7)

    # Composite score bar
    filled = int(((composite + 8) / 16) * 10)
    bar = "█" * filled + "░" * (10 - filled)

    msg = f"""📊 *SPY GEX Daily — {today}*

{headline}

{summary}

{action}{bs_text}

─────────────────────
*KEY NUMBERS*
SPY: *${spy:.2f}* | VIX: {vix:.2f}
GEX: {gex_text}
RSI: {rsi_text}

Support: ${put_w:.0f} | Resistance: ${call_w:.0f}

─────────────────────
*MACRO HEALTH*
🏦 Credit (HYG): {format_credit_health(hyg)}
💵 Dollar (DXY): {format_dollar(dxy)}
🥇 Gold: ${gold:.2f}
📈 10Y Yield: {format_yield(yield10y)}
🔵 Flow: {flow_reg}{mag7_text}

─────────────────────
*REGIME SCORE*
[{bar}] {composite:+.0f}/8
Signal: {signal.replace("_"," ")}

_Dashboard: one7rade-byte.github.io/gex-tracker/_
_🤖 one7rade GEX Tracker_"""

    return msg


def build_deep_analysis(gex, regime):
    """Second message with deeper technical details."""
    composite = n(regime.get("composite_score")) or 0
    credit_s  = regime.get("credit_score","?")
    vol_s     = regime.get("vol_score","?")
    flow_s    = regime.get("flow_score","?")
    growth_s  = regime.get("growth_score","?")
    skew_s    = regime.get("skew_score","?")
    hyg       = n(gex.get("hyg"))
    skew      = n(gex.get("skew_index"))
    vix9d_r   = n(gex.get("vix9d_vix_ratio"))
    copper    = n(gex.get("copper"))
    eem       = n(gex.get("eem"))
    tlt       = n(gex.get("tlt"))
    xlre      = n(gex.get("xlre"))
    oil       = n(gex.get("oil"))
    brief     = regime.get("brief","")

    msg = f"""📖 *DEEP ANALYSIS*

*Composite Score Breakdown*
Credit (HYG): {credit_s}/3
Volatility (VIX): {vol_s}/3
Flow (DXY/Gold): {flow_s}/2
Growth (Copper/EEM): {growth_s}/2
SKEW signal: {skew_s}

*Cross-Asset Detail*
HYG (credit): ${hyg:.2f} {"✅ >$78 = bull intact" if hyg and hyg>78 else "⚠️ monitor"}
TLT (bonds): ${tlt:.2f}
Copper: ${copper:.2f} {"🟢 growth healthy" if copper and copper>35 else "🟡 watch"}
EEM (EM): ${eem:.2f}
Oil: ${oil:.2f}
XLRE (real estate): ${xlre:.2f}

*Technical Signals*
SKEW: {skew:.1f} {"⚠️ elevated tail hedging" if skew and skew>145 else "✅ normal"}
VIX9D/VIX ratio: {round(vix9d_r,3) if vix9d_r else "—"} {"⚠️ near-term spike" if vix9d_r and vix9d_r>1.10 else "✅ calm"}

*Key Thresholds*
• HYG >$78 = buy all dips aggressively
• HYG $74-78 = caution, selective only  
• HYG <$74 = defensive, reduce exposure
• VIX9D/VIX >1.10 = near-term capitulation

*Today's Brief*
_{brief}_"""

    return msg


# ── Send to Telegram ──────────────────────────────────────────────────────────

def send_telegram(text, parse_mode="Markdown"):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }
    try:
        r = requests.post(url, json=payload, timeout=15)
        if r.status_code == 200:
            print(f"  ✅ Telegram message sent")
            return True
        else:
            print(f"  ❌ Telegram error: {r.status_code} — {r.text[:200]}")
            return False
    except Exception as e:
        print(f"  ❌ Telegram request failed: {e}")
        return False


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    now = datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d %H:%M")
    print(f"  Telegram Notify  |  {now}")

    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("  ❌ TELEGRAM_TOKEN or TELEGRAM_CHAT_ID not set")
        return

    # Load data
    gex    = load_latest_gex()
    regime = load_latest_regime()
    mag7   = load_mag7_signals()

    if not gex:
        print("  ❌ No GEX data found")
        return

    print(f"  GEX date: {gex.get('date')} | Signal: {regime.get('regime_signal','?')}")

    # Send main summary
    main_msg = build_message(gex, regime, mag7)
    send_telegram(main_msg)

    # Send deep analysis as second message
    deep_msg = build_deep_analysis(gex, regime)
    send_telegram(deep_msg)

    print("  ✅ Done")


if __name__ == "__main__":
    main()
