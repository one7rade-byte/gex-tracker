"""
quick_action.py — one-line "what does the system say to do right now" read.

Single source of truth for the dashboard's Quick Action card and the line at
the top of the daily Telegram summary. Runs in gex_daily.yml after
regime_analyzer.py and flow_extras.py; writes quick_action.json.

Philosophy (Simon's): don't be first, don't be last, follow where the big
money is moving. So a BUY setup alone isn't "add": it's "wait for
confirmation" until enough of the 5 confirmation checks are in.

Actions:
  DEFEND    big money leaving: credit breaking, backwardation 3+ days,
            regime DEFENSIVE/CRISIS, or flows show broad de-risking
  ADD       buy setup + 3 or more of the 5 confirmations, at least one of
            them from dealers/price (GEX positive 2 days or SPY above zero gamma)
  WAIT      buy setup, but fewer than 3 confirmations (don't be first)
  TIGHTEN   regime CAUTION
  HOLD      HOLD / STRONG_HOLD
"""

import csv
import json
import os

GEX_CSV, REGIME_CSV, FLOW_CSV, OUT = "gex_log.csv", "regime_log.csv", "flow_history.csv", "quick_action.json"


def f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def read(p):
    if not os.path.exists(p):
        return []
    with open(p, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def pct(a, b):
    return (a / b - 1) * 100 if a is not None and b else None


def flow_read(date):
    rows = [r for r in read(FLOW_CSV) if r["date"] <= date]
    if len(rows) < 11:
        return None, None, {}
    cur, old = rows[-1], rows[-11]
    ch = {k: pct(f(cur.get(k)), f(old.get(k))) for k in ("smh_spy", "rsp_spy", "defensive_cyclical", "hyg_ief")}
    smh, rsp, dc, cr = ch["smh_spy"], ch["rsp_spy"], ch["defensive_cyclical"], ch["hyg_ief"]
    if cr is not None and dc is not None and cr <= -1 and dc >= 3:
        lab = ("Leaving stocks: credit sold, money into defensives", "red")
    elif smh is not None and rsp is not None and smh <= -6 and rsp >= 2.5:
        lab = ("Rotating OUT of tech into the rest of the market, not leaving stocks", "amber")
    elif smh is not None and dc is not None and smh >= 4 and dc <= -2:
        lab = ("Rotating back INTO tech: risk-on", "green")
    else:
        lab = ("No strong rotation", "gray")
    return lab, cur["date"], ch


def main():
    gex = [r for r in read(GEX_CSV) if r.get("ticker", "SPY").strip() == "SPY"]
    reg = {r["date"]: r for r in read(REGIME_CSV)}
    if len(gex) < 6:
        raise SystemExit("not enough gex_log history")
    g, date = gex[-1], gex[-1]["date"]
    signal = (reg.get(date, {}).get("regime_signal") or "").upper()

    spy, vix, gexb, zg = f(g["spot_price"]), f(g["vix"]), f(g["net_gex_b"]), f(g["zero_gamma"])
    hyg5 = pct(f(g["hyg"]), f(gex[-6]["hyg"]))
    term = (g.get("vix_term_structure") or "").strip()
    backw = 0
    for r in reversed(gex):
        if (r.get("vix_term_structure") or "").strip() != "backwardation":
            break
        backw += 1
    gex2 = all((f(r["net_gex_b"]) or -1) > 0 for r in gex[-2:])

    checks = [
        ("Fear easing: VIX curve back in contango", term == "contango"),
        ("VIX below 22", vix is not None and vix < 22),
        ("Dealers supportive: GEX positive 2 days", gex2),
        ("SPY back above zero gamma", spy is not None and zg is not None and spy > zg),
        ("Credit holding: HYG flat or up over 5 days", hyg5 is not None and hyg5 >= 0),
    ]
    n_conf = sum(ok for _, ok in checks)
    flow, flow_date, flow_ch = flow_read(date)

    credit_breaking = hyg5 is not None and hyg5 <= -1.5
    buy = signal in ("STRONG_BUY", "BUY_WATCH")
    # "Follow the whales": at least one confirmation must come from dealer
    # positioning / price (GEX positive 2 days, or SPY back above zero gamma).
    # Without this, calm-before-the-storm days (e.g. 2026-10-30: contango, VIX
    # <22, credit flat) counted as "confirmed" right before the Nov 5 drop.
    whale_conf = checks[2][1] or checks[3][1]
    if signal in ("DEFENSIVE", "CRISIS") or credit_breaking or backw >= 3 or (flow and flow[1] == "red"):
        action, tone = "DEFEND", "red"
        head = "Big money is leaving. No new adds; protect what you have."
    elif buy and n_conf >= 3 and whale_conf:
        action, tone = "ADD", "green"
        head = f"Buy setup with {n_conf}/5 confirmations in. Scale in."
    elif buy:
        action, tone = "WAIT FOR CONFIRMATION", "amber"
        head = f"Buy setup is building, but only {n_conf}/5 confirmations. Don't be first."
    elif signal == "CAUTION":
        action, tone = "TIGHTEN", "amber"
        head = "Regime weakening. Tighten stops; no new size."
    else:
        action, tone = "HOLD", "blue"
        head = "Trend intact. Hold."

    credit_txt = ("unknown" if hyg5 is None else
                  f"breaking (HYG {hyg5:+.1f}% in 5 days)" if credit_breaking else
                  f"calm (HYG {hyg5:+.1f}% in 5 days)" if hyg5 > -0.75 else
                  f"softening (HYG {hyg5:+.1f}% in 5 days)")
    fear_txt = f"VIX {vix:.1f}, " + (f"backwardation day {backw}" if backw else term or "n/a")
    reasons = [
        {"label": "Signal", "text": signal.replace("_", " ").title() or "n/a",
         "tone": "green" if buy else "red" if signal in ("DEFENSIVE", "CRISIS") else "amber" if signal == "CAUTION" else "blue"},
        {"label": "Big money", "text": flow[0] if flow else "flow data not available yet",
         "tone": flow[1] if flow else "gray"},
        {"label": "Credit", "text": credit_txt,
         "tone": "red" if credit_breaking else "green" if (hyg5 or 0) > -0.75 else "amber"},
        {"label": "Fear", "text": fear_txt, "tone": "red" if backw else "amber" if (vix or 0) >= 22 else "green"},
    ]
    out = {
        "date": date, "action": action, "tone": tone, "headline": head,
        "confirmations": n_conf, "confirmations_total": len(checks),
        "checks": [{"label": l, "ok": bool(ok)} for l, ok in checks],
        "reasons": reasons, "flow_date": flow_date,
        "flow_10d_pct": {k: (round(v, 2) if v is not None else None) for k, v in flow_ch.items()},
    }
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1)
    print(f"{date}: {action} — {head}")
    for r in reasons:
        print(f"  {r['label']}: {r['text']}")


def telegram_line():
    """Plain text (no Markdown special chars) for the top of the Telegram summary."""
    try:
        with open(OUT, encoding="utf-8") as fh:
            q = json.load(fh)
    except (OSError, ValueError):
        return ""
    icon = {"green": "🟢", "amber": "🟡", "red": "🔴", "blue": "🔵"}.get(q.get("tone"), "⚪")
    lines = [f"{icon} QUICK ACTION: {q['action']}", q["headline"]]
    for r in q.get("reasons", [])[1:]:
        lines.append(f"• {r['label']}: {r['text']}")
    return "\n".join(lines).replace("*", "").replace("_", " ").replace("`", "")


if __name__ == "__main__":
    main()
