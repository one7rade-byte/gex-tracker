"""
intelligence_engine.py
──────────────────────
Daily market intelligence — fully rule-based, no API costs.

Reads gex_log.csv + mag7_log.csv, fetches news headlines,
classifies macro vs company-specific fear, and writes a
plain-English daily brief to intelligence_report.json.
"""

import csv
import json
import os
import re
import time
from datetime import datetime, date

import requests

GEX_CSV    = "gex_log.csv"
MAG7_CSV   = "mag7_log.csv"
INTEL_CSV  = "intelligence_log.csv"
INTEL_JSON = "intelligence_report.json"

TICKERS = ["AAPL", "MSFT", "NVDA", "GOOGL", "META", "AMZN", "TSLA"]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/json,*/*",
}

INTEL_CSV_HEADERS = [
    "date", "macro_regime", "fear_score", "bear_score", "bull_score",
    "vix", "skew", "gex_b", "vix_term_structure",
    "macro_news_summary", "macro_news_sentiment",
    "top_opportunity", "top_opportunity_score", "top_opportunity_reason",
    "avoid_names", "overall_signal", "ai_brief", "voo_vgt_action",
]

# ── Data loaders ──────────────────────────────────────────────────────────────

def load_latest_gex():
    if not os.path.isfile(GEX_CSV): return {}
    with open(GEX_CSV, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return rows[-1] if rows else {}

def load_latest_mag7():
    if not os.path.isfile(MAG7_CSV): return []
    with open(MAG7_CSV, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows: return []
    latest = max(r["date"] for r in rows if r.get("date"))
    return [r for r in rows if r.get("date") == latest]

def load_trend_history(days=20):
    if not os.path.isfile(GEX_CSV): return []
    with open(GEX_CSV, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    def sf(r, k):
        try: return float(r.get(k,"") or "")
        except: return None
    return [{"date":r.get("date",""),"gex":sf(r,"net_gex_b"),"vix":sf(r,"vix"),
             "skew":sf(r,"skew_index"),"fear":sf(r,"fear_score"),"bear":sf(r,"bear_score"),
             "bull":sf(r,"bull_score"),"term":r.get("vix_term_structure",""),
             "rsi":sf(r,"spy_rsi_14"),"above_200ma":r.get("spy_above_200ma","")}
            for r in rows[-days:]]

def load_mag7_trend(ticker, days=20):
    if not os.path.isfile(MAG7_CSV): return []
    with open(MAG7_CSV, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    result = []
    for r in [x for x in rows if x.get("ticker")==ticker][-days:]:
        try:
            result.append({"date":r.get("date",""),
                           "rsi":float(r.get("rsi_14","") or 0),
                           "rsi_pct":float(r.get("rsi_pct","") or 0),
                           "score":float(r.get("opportunity_score","") or 0),
                           "above":r.get("above_200ma","")})
        except: pass
    return result

# ── News fetchers ─────────────────────────────────────────────────────────────

# High-impact macro keywords
HIGH_IMPACT_MACRO_KW = [
    "fed rate","federal reserve","rate decision","fomc","interest rate",
    "cpi report","inflation data","pce data","jobs report","nonfarm payroll",
    "gdp report","recession","rate hike","rate cut","tariff","trade war",
    "earnings miss","earnings beat","guidance cut","guidance raise",
    "market crash","circuit breaker","vix spike","volatility spike",
    "bank failure","banking crisis","credit downgrade","debt ceiling",
    "geopolitical","oil shock","sanctions","default","bankruptcy major",
]

TICKER_KEYWORDS = {
    "AAPL":  ["apple","aapl"],
    "MSFT":  ["microsoft","msft","azure","copilot"],
    "NVDA":  ["nvidia","nvda","gpu","blackwell","h100"],
    "GOOGL": ["google","googl","alphabet","gemini","waymo","youtube"],
    "META":  ["meta","facebook","instagram","zuckerberg","llama"],
    "AMZN":  ["amazon","amzn","aws","alexa","prime"],
    "TSLA":  ["tesla","tsla","elon","musk","cybertruck"],
    "SPY":   ["s&p","s&p 500","sp500","spy","dow jones","stock market","broad market"],
    "QQQ":   ["nasdaq","qqq","tech stocks","technology sector"],
}

def extract_pub_date(item_text):
    m = re.search(r'<pubDate>(.*?)</pubDate>', item_text)
    if not m: return None
    try:
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(m.group(1).strip()).strftime("%Y-%m-%d")
    except:
        dm = re.search(r'(\d{1,2} \w{3} \d{4})', m.group(1))
        return dm.group(1) if dm else None

def tag_tickers(title, summary=""):
    text = (title + " " + summary).lower()
    found = [t for t, kws in TICKER_KEYWORDS.items() if any(kw in text for kw in kws)]
    return found if found else ["MARKET"]

def is_high_impact(title, summary=""):
    text = (title + " " + summary).lower()
    return any(kw in text for kw in HIGH_IMPACT_MACRO_KW)

def fetch_yahoo_news(symbol, max_items=10):
    headlines = []
    try:
        url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={symbol}&region=US&lang=en-US"
        r = requests.get(url, headers=HEADERS, timeout=10)
        for item in re.findall(r'<item>(.*?)</item>', r.text, re.DOTALL)[:max_items]:
            title = re.search(r'<title><!\[CDATA\[(.*?)\]\]></title>', item) or re.search(r'<title>(.*?)</title>', item)
            desc  = re.search(r'<description><!\[CDATA\[(.*?)\]\]></description>', item) or re.search(r'<description>(.*?)</description>', item)
            link  = re.search(r'<link>(.*?)</link>', item) or re.search(r'<guid>(.*?)</guid>', item)
            if title:
                t = title.group(1).strip()
                s = desc.group(1).strip()[:300] if desc else ""
                l = link.group(1).strip() if link else ""
                headlines.append({
                    "title": t, "summary": s, "link": l,
                    "pub_date":    extract_pub_date(item),
                    "tickers":     tag_tickers(t, s),
                    "high_impact": is_high_impact(t, s),
                })
    except Exception as e:
        print(f"  News fetch failed ({symbol}): {e}")
    return headlines

def fetch_market_news():
    from datetime import datetime, timedelta
    cutoff = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    seen, all_h = set(), []
    for sym in ["SPY", "%5EGSPC", "%5EVIX"]:
        for h in fetch_yahoo_news(sym, 10):
            if h["title"] not in seen:
                seen.add(h["title"])
                all_h.append(h)
    recent     = [h for h in all_h if not h.get("pub_date") or h["pub_date"] >= cutoff]
    high_imp   = [h for h in recent if h["high_impact"]]
    normal     = [h for h in recent if not h["high_impact"]]
    result     = high_imp[:6] + normal[:4]
    print(f"  Market news: {len(result)} total ({len(high_imp)} high impact, last 7 days)")
    return result[:10]


# ── News classifier ───────────────────────────────────────────────────────────

MACRO_KW = ["recession","inflation","rate hike","fed ","federal reserve","tariff",
            "trade war","selloff","sell-off","market falls","market drops","crash",
            "yield","treasury","gdp","jobs report","unemployment","cpi","pce",
            "geopolitical","war","sanctions","oil price","energy","credit",
            "debt ceiling","banking crisis","vix","fear","risk off","downturn"]

NEG_KW = ["earnings miss","misses estimates","below expectations","guidance cut",
          "lowers guidance","disappoints","revenue miss","profit warning",
          "layoffs","job cuts","restructuring","fraud","sec investigation",
          "antitrust","lawsuit","regulatory","recall","product failure",
          "ceo resigns","executive departs","probe","downgrade","price target cut"]

POS_KW = ["earnings beat","beats estimates","above expectations","raises guidance",
          "strong results","record revenue","new product","partnership",
          "buyback","dividend increase","upgrade","price target raised",
          "breakthrough","contract win","market share gain","outperform"]

FUND_KW = ["merger","acquisition completed","spin-off","bankruptcy","strategic pivot",
           "new ceo","business model change","delisting","chapter 11"]

def classify_headlines(headlines):
    counts = {"macro_fear":0,"company_negative":0,"company_positive":0,"fundamental_change":0}
    key = []
    for h in headlines:
        text = (h.get("title","")+" "+h.get("summary","")).lower()
        if any(kw in text for kw in FUND_KW):   counts["fundamental_change"] += 1; key.append(h["title"])
        if any(kw in text for kw in NEG_KW):    counts["company_negative"] += 1;   key.append(h["title"])
        if any(kw in text for kw in POS_KW):    counts["company_positive"] += 1;   key.append(h["title"])
        if any(kw in text for kw in MACRO_KW):  counts["macro_fear"] += 1

    if counts["fundamental_change"] > 0:   dominant = "fundamental_change"
    elif counts["company_negative"] > counts["company_positive"]: dominant = "company_negative"
    elif counts["company_positive"] > counts["company_negative"]: dominant = "company_positive"
    elif counts["macro_fear"] > 0:         dominant = "macro_fear"
    else:                                  dominant = "neutral"

    return {**counts, "dominant": dominant, "key_headlines": list(dict.fromkeys(key))[:3]}

# ── Trend analyzers ───────────────────────────────────────────────────────────

def analyze_macro_trend(history):
    if len(history) < 3:
        return {"regime":"insufficient_data"}
    recent = history[-5:]
    older  = history[-15:-5] if len(history) >= 15 else history[:max(1,len(history)-5)]

    def avg(lst, k):
        v = [x[k] for x in lst if x.get(k) is not None]
        return sum(v)/len(v) if v else None

    vix_r, vix_o = avg(recent,"vix"), avg(older,"vix")
    gex_r, gex_o = avg(recent,"gex"), avg(older,"gex")
    fear_r       = avg(recent,"fear")
    last         = history[-1]

    vix_trend  = "rising" if vix_r and vix_o and vix_r > vix_o+1 else "falling" if vix_r and vix_o and vix_r < vix_o-1 else "stable"
    gex_trend  = "improving" if gex_r and gex_o and gex_r > gex_o else "deteriorating" if gex_r and gex_o and gex_r < gex_o else "stable"
    fear_trend = "building" if fear_r and avg(older,"fear") and fear_r > avg(older,"fear") else "easing" if fear_r and avg(older,"fear") and fear_r < avg(older,"fear") else "stable"
    neg_days   = sum(1 for x in history[-10:] if x.get("gex") is not None and x["gex"] < 0)

    if   last.get("fear") and last["fear"] >= 7:   regime = "high_fear"
    elif last.get("bull") and last["bull"] >= 7:   regime = "strong_bull"
    elif last.get("bear") and last["bear"] >= 5:   regime = "bear_warning"
    elif last.get("gex")  and last["gex"] > 5:     regime = "positive_gex"
    elif last.get("gex")  and last["gex"] < -3:    regime = "negative_gex"
    else:                                           regime = "mixed"

    return {"regime":regime,"vix_trend":vix_trend,"vix_current":last.get("vix"),
            "gex_trend":gex_trend,"gex_current":last.get("gex"),
            "fear_trend":fear_trend,"fear_current":last.get("fear"),
            "bear_current":last.get("bear"),"bull_current":last.get("bull"),
            "neg_gex_days":neg_days,"skew_current":last.get("skew"),
            "term_struct":last.get("term"),"above_200ma":last.get("above_200ma"),
            "spy_rsi":last.get("rsi")}

def analyze_stock_trend(ticker):
    hist = load_mag7_trend(ticker, 20)
    if not hist: return {"rsi_direction":"no_data","days_oversold":0}
    recent = hist[-5:] if len(hist)>=5 else hist
    older  = hist[-15:-5] if len(hist)>=15 else []
    def avg_pct(lst): v=[x["rsi_pct"] for x in lst if x.get("rsi_pct")]; return sum(v)/len(v) if v else 50
    r_avg, o_avg = avg_pct(recent), avg_pct(older)
    direction = "getting_more_oversold" if r_avg < o_avg-5 else "recovering" if r_avg > o_avg+5 else "stable"
    days_os   = sum(1 for x in hist[-10:] if x.get("rsi_pct") is not None and x["rsi_pct"] < 30)
    return {"rsi_direction":direction,"days_oversold":days_os,
            "rsi_pct_current":hist[-1].get("rsi_pct"),"score_current":hist[-1].get("score")}

# ── Rule-based brief generator ────────────────────────────────────────────────

def generate_brief(macro, mag7_data, macro_news_class, today):
    """
    Generates a structured plain-English brief purely from data.
    No API calls. Returns dict with sections.
    """
    vix    = macro.get("vix_current") or 0
    gex    = macro.get("gex_current") or 0
    skew   = macro.get("skew_current") or 0
    fear   = macro.get("fear_current") or 0
    bear   = macro.get("bear_current") or 0
    bull   = macro.get("bull_current") or 0
    regime = macro.get("regime","mixed")
    term   = macro.get("term_struct","")
    vt     = macro.get("vix_trend","stable")
    gt     = macro.get("gex_trend","stable")
    neg_d  = macro.get("neg_gex_days",0)
    rsi    = macro.get("spy_rsi") or 0
    above  = macro.get("above_200ma","")

    # ── MACRO PICTURE ─────────────────────────────────────────────────────────
    macro_lines = []

    # GEX read
    if gex < -5:
        macro_lines.append(f"SPY GEX is deeply negative at ${gex:.1f}B — dealers are net short gamma and amplifying moves in both directions. The market is in an unstable, high-energy state.")
    elif gex < 0:
        macro_lines.append(f"SPY GEX is negative at ${gex:.1f}B — dealers are short gamma. Market regime is unstable but not in free-fall.")
    elif gex > 10:
        macro_lines.append(f"SPY GEX is strongly positive at +${gex:.1f}B — dealers are long gamma and actively stabilizing the market. Low volatility, pinned range likely.")
    else:
        macro_lines.append(f"SPY GEX is positive at +${gex:.1f}B — dealers are providing a cushion on dips. Bullish but not peak suppression.")

    # VIX + trend
    vix_desc = "elevated" if vix > 22 else "moderately elevated" if vix > 18 else "calm"
    macro_lines.append(f"VIX is {vix:.1f} ({vix_desc}, {vt} trend over 5 days). {'Term structure in backwardation — near-term fear exceeds long-term, institutions hedging imminent risk.' if term=='backwardation' else 'Term structure in contango — calm, orderly vol curve.'}")

    # SKEW
    if skew > 145:
        macro_lines.append(f"SKEW at {skew:.0f} is extreme — large institutions are paying a significant premium for deep OTM puts. This level historically precedes a sharp move within 2-4 weeks.")
    elif skew > 135:
        macro_lines.append(f"SKEW at {skew:.0f} is elevated — smart money is actively buying tail protection. Not panic, but meaningful hedging activity.")
    else:
        macro_lines.append(f"SKEW at {skew:.0f} is in the normal range — no unusual institutional tail hedging.")

    # Trend context
    if neg_d >= 7:
        macro_lines.append(f"GEX has been negative {neg_d} of the last 10 days — this is a prolonged negative regime, not a one-day event.")
    elif gt == "improving":
        macro_lines.append("GEX is improving over the past week — dealer positioning is becoming more supportive.")

    # News driver
    news_dom = macro_news_class.get("dominant","neutral")
    if news_dom == "macro_fear":
        macro_lines.append("Market headlines are dominated by macro fear themes (Fed, inflation, geopolitical) — this is broad market anxiety, not company-specific deterioration.")
    elif news_dom == "company_negative":
        macro_lines.append("Warning: company-specific negative news is present in headlines — review which names are affected before loading.")
    else:
        macro_lines.append("No dominant negative news theme today — market moves appear technical rather than news-driven.")

    macro_picture = " ".join(macro_lines)

    # ── VOO/VGT ACTION ────────────────────────────────────────────────────────
    if fear >= 8 and gex < -5:
        voo_action = f"LOAD — Fear score {fear:.0f}/10 with deeply negative GEX. This is a high-conviction loading zone for VOO/VGT. Add in tranches, not all at once."
        overall    = "LOAD"
    elif fear >= 6 and vix > 20:
        voo_action = f"WATCH — Fear building ({fear:.0f}/10, VIX {vix:.1f}). Not at peak fear yet but the setup is forming. Begin preparing capital, add a small tranche if VOO/VGT dips further."
        overall    = "WATCH"
    elif bear >= 7:
        voo_action = f"REDUCE — Bear score {bear:.0f}/10. Multiple bearish signals aligned. Hold existing long-term positions but do not add. Wait for GEX to turn positive and VIX to stabilize."
        overall    = "REDUCE"
    elif bull >= 7 and gex > 5:
        voo_action = f"HOLD — Strong bull regime (bull score {bull:.0f}/10, GEX +${gex:.1f}B). Hold all positions. Market is elevated and stable — not a new entry point but not an exit either."
        overall    = "HOLD"
    elif gex < 0 and vix > 19:
        voo_action = f"WATCH — GEX negative with VIX at {vix:.1f}. Mixed signals. Hold current positions, do not add aggressively. Watch for VIX to push above 22-25 as the real loading zone."
        overall    = "WATCH"
    else:
        voo_action = f"HOLD — No strong signal today. Market is in a mixed regime. Hold existing VOO/VGT positions. Wait for fear score to reach 6+ or bull score to confirm."
        overall    = "HOLD"

    # ── MAG 7 OPPORTUNITIES ───────────────────────────────────────────────────
    opp_lines  = []
    avoid_names = []
    opportunities = []

    for ticker, data in sorted(mag7_data.items(), key=lambda x: x[1].get("score",0), reverse=True):
        score     = data.get("score",0) or 0
        rsi_pct   = data.get("rsi_pct")
        news_cls  = data.get("news_classification",{})
        news_dom  = news_cls.get("dominant","neutral")
        trend     = data.get("trend",{})
        above_200 = data.get("above_200ma")
        days_os   = trend.get("days_oversold",0)
        rsi_dir   = trend.get("rsi_direction","stable")

        if news_dom in ("company_negative","fundamental_change"):
            avoid_names.append(ticker)
            key_h = news_cls.get("key_headlines",["company-specific issues"])
            opp_lines.append(f"{ticker} AVOID — company-specific negative news detected: '{key_h[0][:60]}...' Do not buy this dip until news clears.")
        elif rsi_pct is not None and rsi_pct <= 20 and score >= 3:
            conf = "high" if rsi_pct <= 10 else "moderate"
            macro_driven = "macro-driven selloff" if news_dom in ("macro_fear","neutral") else "mixed drivers"
            opp_lines.append(f"{ticker} OPPORTUNITY ({conf} confidence) — RSI at {rsi_pct:.0f}th percentile of own history, {days_os} of last 10 days oversold, {macro_driven}. Score {score:.0f}/10. {above_200=='True' and 'Above 200MA — uptrend intact.' or 'Below 200MA — scale in slowly.'}")
            opportunities.append((ticker, score, rsi_pct))
        elif score >= 4:
            opp_lines.append(f"{ticker} WATCH — score {score:.0f}/10, RSI at {rsi_pct:.0f}th pct. Not yet at peak oversold but building." if rsi_pct else f"{ticker} WATCH — score {score:.0f}/10.")

    if not opp_lines:
        opp_lines.append("No Mag 7 names are significantly oversold today. All names are in neutral or positive territory vs their own history.")

    mag7_section = " ".join(opp_lines[:4])

    # Top opportunity
    top_ticker = opportunities[0][0] if opportunities else None
    top_score  = opportunities[0][1] if opportunities else 0

    # ── WATCH FOR ─────────────────────────────────────────────────────────────
    watch_lines = []
    if overall in ("WATCH","HOLD") and fear < 8:
        vix_needed = max(0, 22 - vix)
        watch_lines.append(f"VIX pushing above 22-25 (currently {vix:.1f}, needs +{vix_needed:.1f} pts) with GEX remaining negative would trigger a high-conviction buy zone.")
    if gex < 0:
        watch_lines.append(f"GEX flipping positive would confirm dealer stabilization — that's the technical all-clear for loading.")
    if skew > 135:
        watch_lines.append(f"SKEW dropping back below 130 would signal institutional tail hedging is unwinding — a sign the fear peak is passing.")
    if not watch_lines:
        watch_lines.append("Monitor for VIX re-test of recent highs combined with GEX turning more negative — that would upgrade the signal to LOAD.")

    watch_section = " ".join(watch_lines[:2])

    # ── Assemble full brief ───────────────────────────────────────────────────
    brief = f"""MACRO PICTURE: {macro_picture}

VOO/VGT ACTION: {voo_action}

MAG 7 OPPORTUNITIES: {mag7_section}

WATCH FOR: {watch_section}

OVERALL SIGNAL: {overall}"""

    return {
        "overall_signal": overall,
        "voo_vgt_action": voo_action,
        "macro_picture":  macro_picture,
        "mag7_section":   mag7_section,
        "watch_section":  watch_section,
        "top_opportunity": top_ticker,
        "top_score":       top_score,
        "avoid_names":     avoid_names,
        "full_brief":      brief,
    }

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    today = date.today().strftime("%Y-%m-%d")
    now   = datetime.now().strftime("%I:%M %p")

    print("="*60)
    print(f"  Intelligence Engine  |  {today}  {now}")
    print("="*60)

    print("\n[1] Loading data...")
    gex_row   = load_latest_gex()
    mag7_rows = load_latest_mag7()
    history   = load_trend_history(20)

    if not gex_row:
        print("  No GEX data. Run gex_tracker.py first.")
        return

    print(f"  GEX: {gex_row.get('date')}  VIX={gex_row.get('vix')}  GEX={gex_row.get('net_gex_b')}")

    print("\n[2] Analyzing 20-day macro trend...")
    macro = analyze_macro_trend(history)
    print(f"  Regime: {macro['regime']}  VIX trend: {macro['vix_trend']}  GEX trend: {macro['gex_trend']}")

    print("\n[3] Analyzing Mag7 trends...")
    mag7_data = {}
    for row in mag7_rows:
        tk = row.get("ticker")
        if not tk: continue
        trend = analyze_stock_trend(tk)
        try:
            score   = float(row.get("opportunity_score",0) or 0)
            rsi_pct = float(row.get("rsi_pct",0) or 0) if row.get("rsi_pct") else None
            above   = row.get("above_200ma")=="True"
        except:
            score=0; rsi_pct=None; above=None
        mag7_data[tk] = {"score":score,"rsi_pct":rsi_pct,"above_200ma":above,
                          "signal":row.get("signal",""),"detail":row.get("signal_detail",""),
                          "trend":trend}
        print(f"  {tk}: score={score}  rsi_pct={rsi_pct}  direction={trend.get('rsi_direction')}")

    print("\n[4] Fetching news...")
    macro_headlines = fetch_market_news()
    macro_news_cls  = classify_headlines(macro_headlines)
    print(f"  Macro: {len(macro_headlines)} headlines, dominant={macro_news_cls['dominant']}")

    for tk in TICKERS:
        headlines = fetch_yahoo_news(tk, 6)
        cls = classify_headlines(headlines)
        if tk in mag7_data:
            mag7_data[tk]["news_classification"] = cls
            mag7_data[tk]["headlines"] = [h["title"] for h in headlines[:4]]
        print(f"  {tk}: {len(headlines)} headlines, dominant={cls['dominant']}")
        time.sleep(0.5)

    print("\n[5] Generating intelligence brief...")
    result = generate_brief(macro, mag7_data, macro_news_cls, today)
    print(f"  Signal: {result['overall_signal']}")
    print(f"  Top opportunity: {result['top_opportunity']} ({result['top_score']}/10)")
    print(f"  Avoid: {result['avoid_names']}")

    # Save CSV
    macro_summary = "; ".join(h["title"] for h in macro_headlines[:3])
    csv_row = {
        "date":today,"macro_regime":macro.get("regime"),
        "fear_score":macro.get("fear_current"),"bear_score":macro.get("bear_current"),
        "bull_score":macro.get("bull_current"),"vix":macro.get("vix_current"),
        "skew":macro.get("skew_current"),"gex_b":macro.get("gex_current"),
        "vix_term_structure":macro.get("term_struct"),
        "macro_news_summary":macro_summary[:200],
        "macro_news_sentiment":macro_news_cls.get("dominant"),
        "top_opportunity":result["top_opportunity"] or "",
        "top_opportunity_score":result["top_score"],
        "top_opportunity_reason":mag7_data.get(result["top_opportunity"],{}).get("detail","")[:200] if result["top_opportunity"] else "",
        "avoid_names":",".join(result["avoid_names"]),
        "overall_signal":result["overall_signal"],
        "ai_brief":result["full_brief"][:2000],
        "voo_vgt_action":result["voo_vgt_action"][:300],
    }
    exists = os.path.isfile(INTEL_CSV)
    with open(INTEL_CSV,"a",newline="",encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=INTEL_CSV_HEADERS, extrasaction="ignore")
        if not exists: w.writeheader()
        w.writerow(csv_row)

    # Save JSON for dashboard
    report = {
        "date":today,"generated_at":now,
        "overall_signal":result["overall_signal"],
        "voo_vgt_action":result["voo_vgt_action"],
        "macro_picture": result["macro_picture"],
        "mag7_section":  result["mag7_section"],
        "watch_section": result["watch_section"],
        "ai_brief":      result["full_brief"],
        "macro_trend":   macro,
        "top_opportunity":{"ticker":result["top_opportunity"],"score":result["top_score"],
            "reason":mag7_data.get(result["top_opportunity"],{}).get("detail","") if result["top_opportunity"] else "",
            "news":mag7_data.get(result["top_opportunity"],{}).get("news_classification",{}).get("dominant","") if result["top_opportunity"] else ""},
        "avoid_names":   result["avoid_names"],
        "mag7_snapshot": {t:{"score":d.get("score"),"rsi_pct":d.get("rsi_pct"),
            "above_200ma":d.get("above_200ma"),
            "news":d.get("news_classification",{}).get("dominant","neutral"),
            "rsi_dir":d.get("trend",{}).get("rsi_direction",""),
            "days_oversold":d.get("trend",{}).get("days_oversold",0),
            "headlines":d.get("headlines",[])} for t,d in mag7_data.items()},
        "macro_headlines":[{"title":h["title"],"link":h.get("link",""),"pub_date":h.get("pub_date",""),"tickers":h.get("tickers",["MARKET"]),"high_impact":h.get("high_impact",False)} for h in macro_headlines[:8]],
    }

    with open(INTEL_JSON,"w",encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print(f"\n  Saved {INTEL_CSV} and {INTEL_JSON}")
    print("\nDone.")

if __name__ == "__main__":
    main()
