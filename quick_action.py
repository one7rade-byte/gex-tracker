"""
quick_action.py — one-line "what does the system say to do right now" read.

Single source of truth for the dashboard's Quick Action card and the line at
the top of the daily Telegram summary. Runs in gex_daily.yml after
regime_analyzer.py and flow_extras.py; writes quick_action.json.

Philosophy (Simon's): don't be first, don't be last, follow where the big
money is moving. So a BUY setup alone isn't "add": it's "wait for
confirmation" until enough of the 5 confirmation checks are in.

Buy-low rule (Simon, 2026-11-19/25): never "exit" into a drop. A normal
correction gets ONE buy, at -8% from SPY's all-time high. Three buys are only
for a deep / black-swan drop, which is switched on by a "second leg": SPY
closes 5%+ below its first-oversold (RSI<30) close. Since 1995 that happened
in all 5 drops of 20%+ and in none of the 9 mild corrections
(research/drawdown_2026/buy_plan_study.py). The research agent's P0b test
showed stress flags are volatility flags, not sell signals.

Actions:
  BUY ZONE  SPY 8%+ below its high, normal correction: one buy.
  DEEP-DROP second leg confirmed: 3 buys (-8%, the second leg, then -25% or
            5 straight closes above the 50-day average, whichever comes first).
  NO RUSH   stress flag (backwardation 3+ days, or credit breaking / big
            money leaving for 2 days in a row) while SPY is less than 8% off
            its high. Not a sell signal: don't add size yet.
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


# Levels the drawdown tracker measures (research only, not the plan).
LADDER = [(-8, None), (-12, None), (-15, None), (-20, None), (-25, None), (-30, None)]
BUY_PLAN_STUDY = os.path.join("research", "drawdown_2026", "buy_plan_study.json")
BUY1_DD, SECOND_LEG, BUY3_DD = -8, 0.95, -25


def _rsi(C, n=14):
    R = [None] * len(C)
    if len(C) <= n:
        return R
    g = sum(max(C[i] - C[i - 1], 0) for i in range(1, n + 1)) / n
    l = sum(max(C[i - 1] - C[i], 0) for i in range(1, n + 1)) / n
    R[n] = 100 - 100 / (1 + g / l) if l else 100
    for i in range(n + 1, len(C)):
        d = C[i] - C[i - 1]
        g, l = (g * (n - 1) + max(d, 0)) / n, (l * (n - 1) + max(-d, 0)) / n
        R[i] = 100 - 100 / (1 + g / l) if l else 100
    return R


def ladder_read(date, spot):
    """SPY all-time high, drawdown, and the buy plan: one buy in a normal
    correction, three buys once a second leg confirms a deep drop."""
    rows = [r for r in read(FLOW_CSV) if r["date"] <= date and f(r.get("spy"))]
    if not rows:
        return None
    closes = [(r["date"], f(r["spy"])) for r in rows]
    if spot and closes[-1][0] != date:
        closes.append((date, spot))
    D, C = [d for d, _ in closes], [c for _, c in closes]
    ai = max(range(len(C)), key=lambda i: C[i])
    ath_date, ath, last = D[ai], C[ai], C[-1]
    R = _rsi(C)
    ma50 = [sum(C[i - 49:i + 1]) / 50 if i >= 49 else None for i in range(len(C))]
    p1 = round(ath * (1 + BUY1_DD / 100), 2)
    i1 = next((i for i in range(ai, len(C)) if C[i] <= p1), None)
    ios = next((i for i in range(ai, len(C)) if R[i] is not None and R[i] < 30), None)
    p2 = round(C[ios] * SECOND_LEG, 2) if ios is not None else None
    i2 = next((i for i in range(ios, len(C)) if C[i] <= p2), None) if ios is not None else None
    p3 = round(ath * (1 + BUY3_DD / 100), 2)
    i3 = None
    if i2 is not None:
        # 5 straight closes above the 50-day avg: a 1-day reclaim fired too
        # early in 2018 (Dec 3, before the Dec 24 low); 5 days fixed it.
        i3 = next((i for i in range(i2 + 5, len(C)) if C[i] <= p3 or
                   all(ma50[j] and C[j] > ma50[j] for j in range(i - 4, i + 1))), None)
    try:
        with open(BUY_PLAN_STUDY, encoding="utf-8") as fh:
            study = json.load(fh)
    except (OSError, ValueError):
        study = {}
    tiers = [
        {"tier": BUY1_DD, "price": p1, "label": "Buy 1 (the single buy)", "hit_date": D[i1] if i1 is not None else None},
        {"tier": round((p2 / ath - 1) * 100, 1) if p2 else None, "price": p2,
         "label": "Deep-drop switch / Buy 2 (5% under first oversold)", "hit_date": D[i2] if i2 is not None else None},
        {"tier": BUY3_DD, "price": p3, "label": "Buy 3 (or 5 closes above the 50-day avg)", "hit_date": D[i3] if i3 is not None else None},
    ]
    return {"ath": round(ath, 2), "ath_date": ath_date, "last": round(last, 2),
            "drawdown_pct": round((last / ath - 1) * 100, 1), "tiers": tiers,
            "mode": "DEEP" if i2 is not None else "NORMAL",
            "tranches_hit": sum(1 for t in tiers if t["hit_date"]),
            "first_oversold": {"date": D[ios], "close": round(C[ios], 2)} if ios is not None else None,
            "ma50": round(ma50[-1], 2) if ma50[-1] else None, "study": study}


RSI_STUDY = os.path.join("research", "rsi_divergence", "rsi_study.json")


def rsi_read(date, spot):
    """Latest 'first oversold' (RSI(14) < 30 after 60+ sessions without one) in
    the last 60 sessions, with what history says happens next
    (research/rsi_divergence/rsi_study.py, SPY 1995+)."""
    closes = [(r["date"], f(r["spy"])) for r in read(FLOW_CSV) if r["date"] <= date and f(r.get("spy"))]
    if spot and closes and closes[-1][0] != date:
        closes.append((date, spot))
    if len(closes) < 300:
        return None
    C = [c for _, c in closes]
    n, R = 14, [None] * len(C)
    g = sum(max(C[i] - C[i - 1], 0) for i in range(1, n + 1)) / n
    l = sum(max(C[i - 1] - C[i], 0) for i in range(1, n + 1)) / n
    for i in range(n, len(C)):
        if i > n:
            d = C[i] - C[i - 1]
            g, l = (g * (n - 1) + max(d, 0)) / n, (l * (n - 1) + max(-d, 0)) / n
        R[i] = 100 - 100 / (1 + g / l) if l else 100
    first, last_os = None, -999
    for i in range(n, len(C)):
        if R[i] < 30:
            if i - last_os >= 60:
                first = i
            last_os = i
    out = {"rsi": round(R[-1], 1)}
    if first is not None and len(C) - 1 - first <= 60:
        fd, fc = closes[first]
        vix_hi = False
        for r in read(FLOW_CSV):
            if r["date"] == fd:
                vix_hi = (f(r.get("vix")) or 0) > 30
        try:
            with open(RSI_STUDY, encoding="utf-8") as fh:
                st_ = json.load(fh)["spy"]["oversold_vix_over_30" if vix_hi else "oversold_vix_under_30"]
        except (OSError, ValueError, KeyError):
            st_ = {}
        drop = st_.get("median_further_drop_60d")
        out.update({"first_oversold_date": fd, "first_oversold_close": round(fc, 2), "vix_over_30": vix_hi,
                    "undercut_pct": st_.get("undercut_within_60d_pct"), "median_further_drop_60d": drop,
                    "retest_zone": round(fc * (1 + drop / 100), 2) if drop is not None else None,
                    "median_12m": st_.get("median_f250"), "positive_12m_pct": st_.get("f250_positive_pct"),
                    "n": st_.get("n"), "low_since": round(min(C[first:]), 2)})
    return out


TQQQ_STUDY = os.path.join("research", "drawdown_2026", "tqqq_entry_study.json")


def tqqq_read(date):
    """TQQQ (3x QQQ) entry zone: only in a deep drop, never at the start.
    Trigger: QQQ closes 20%+ below its high, or 15%+ below with RSI<30 and
    VIX>30 the same day. Guard: QQQ closes 10% below the entry close, which
    means stop adding TQQQ (it happened in the 2000 and 2022 bear markets
    and in none of the drops that recovered). research/drawdown_2026/tqqq_entry_study.py"""
    rows = [r for r in read(FLOW_CSV) if r["date"] <= date and f(r.get("qqq"))]
    if len(rows) < 300:
        return None
    D, C = [r["date"] for r in rows], [f(r["qqq"]) for r in rows]
    V = {r["date"]: f(r.get("vix")) for r in rows}
    R = _rsi(C)
    ai = max(range(len(C)), key=lambda i: C[i])
    ath = C[ai]
    i0 = next((i for i in range(ai, len(C)) if C[i] / ath - 1 <= -0.20 or
               (C[i] / ath - 1 <= -0.15 and R[i] is not None and R[i] < 30 and (V.get(D[i]) or 0) > 30)), None)
    try:
        with open(TQQQ_STUDY, encoding="utf-8") as fh:
            st_ = json.load(fh)
    except (OSError, ValueError):
        st_ = {}
    out = {"qqq_ath": round(ath, 2), "qqq_ath_date": D[ai], "qqq_last": round(C[-1], 2),
           "qqq_dd_pct": round((C[-1] / ath - 1) * 100, 1), "trigger_level": round(ath * 0.8, 2),
           "entry_date": None, "status": "NOT YET", "study": {k: st_.get(k) for k in ("fired", "of", "median_tqqq_12m", "positive_12m", "median_worst_after")}}
    if i0 is not None:
        guard = round(C[i0] * 0.90, 2)
        g = next((i for i in range(i0 + 1, len(C)) if C[i] <= guard), None)
        out.update({"entry_date": D[i0], "entry_qqq": round(C[i0], 2), "entry_dd_pct": round((C[i0] / ath - 1) * 100, 1),
                    "guard_level": guard, "guard_hit": D[g] if g is not None else None,
                    "status": "GUARD HIT: STOP ADDING" if g is not None else "ZONE OPEN"})
    return out


CURVE_CSV = "yield_curve.csv"
CURVE_STUDY = os.path.join("research", "yield_curve", "curve_study.json")
CURVE_MEANING = {
    "BULL STEEPENER": "yields falling, 2y faster: the market expects Fed cuts",
    "BULL FLATTENER": "yields falling, 10y faster: growth fears, flight to safety",
    "BEAR STEEPENER": "yields rising, 10y faster: inflation / fiscal / term-premium worry",
    "BEAR FLATTENER": "yields rising, 2y faster: the Fed is tightening",
    "FLAT": "the 10y-2y spread moved less than 10bp in 20 sessions",
}


def curve_read(date):
    """2y/10y regime from yield_curve.csv plus its SPY track record
    (research/yield_curve/curve_study.py, 1995+, split by era)."""
    rows = [r for r in read(CURVE_CSV) if r["date"] <= date and r.get("regime")]
    if not rows:
        return None
    r = rows[-1]
    try:
        with open(CURVE_STUDY, encoding="utf-8") as fh:
            st_ = json.load(fh)
    except (OSError, ValueError):
        st_ = {}
    g = r["regime"]
    # Curve CAUTION (sizing only, never "sell"): bear flattener, the year after
    # an un-inversion (first positive close after 60+ inverted sessions), or a
    # bull steepener while credit is weak (HYG/IEF -1.5%+ over 20 sessions).
    # Backtest 1999+ (half size while on): SPY CAGR 7.37% vs 6.44%, max DD
    # -44.5% vs -56.5%; simulated TQQQ since 2010 35.5% vs 34.3%, -76.2% vs -81.6%.
    sp = [f(x["spread_10_2"]) for x in rows[-1300:]]
    unin_until, run = -1, 0
    for i, v in enumerate(sp):
        if v is not None and v < 0:
            run += 1
        else:
            if run >= 60:
                unin_until = i + 250
            run = 0
    in_unin = len(sp) - 1 <= unin_until
    fl = [x for x in read(FLOW_CSV) if x["date"] <= date and f(x.get("hyg_ief"))]
    cred20 = (f(fl[-1]["hyg_ief"]) / f(fl[-21]["hyg_ief"]) - 1) * 100 if len(fl) > 21 else None
    why = [w for w, on in (("bear flattener (Fed tightening)", g == "BEAR FLATTENER"),
                           ("within a year of an un-inversion", in_unin),
                           ("bull steepener with weak credit", g == "BULL STEEPENER" and cred20 is not None and cred20 <= -1.5)) if on]
    allh = (st_.get("by_regime") or {}).get(g, {})
    recent = ((st_.get("by_era") or {}).get("2010+") or {}).get(g, {})
    base = ((st_.get("by_era") or {}).get("2010+") or {}).get("all_days", {})
    return {"date": r["date"], "y2": f(r["y2"]), "y10": f(r["y10"]), "spread": f(r["spread_10_2"]),
            "chg2": f(r.get("chg2_20d")), "chg10": f(r.get("chg10_20d")), "regime": g,
            "meaning": CURVE_MEANING.get(g, ""), "inverted": (f(r["spread_10_2"]) or 0) < 0,
            "hist_all": allh, "hist_2010": recent, "base_2010": base,
            "caution": bool(why), "caution_why": why, "hyg_ief_20d_pct": round(cred20, 2) if cred20 is not None else None}


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
    # 2-day persistence for the credit and flow flags (research P0b: cuts
    # whipsaw ~40%); backwardation already needs 3 days.
    hyg5_prev = pct(f(gex[-2]["hyg"]), f(gex[-7]["hyg"])) if len(gex) >= 7 else None
    credit_2d = credit_breaking and hyg5_prev is not None and hyg5_prev <= -1.5
    flow_prev = flow_read(gex[-2]["date"])[0] if len(gex) >= 2 else None
    flow_red_2d = bool(flow and flow[1] == "red" and flow_prev and flow_prev[1] == "red")
    stress = credit_2d or backw >= 3 or flow_red_2d or signal in ("DEFENSIVE", "CRISIS")
    stress_why = ", ".join(w for w, on in (("credit breaking 2 days", credit_2d),
                                          (f"VIX backwardation {backw} days", backw >= 3),
                                          ("big money leaving 2 days", flow_red_2d),
                                          (f"regime {signal.lower()}", signal in ("DEFENSIVE", "CRISIS"))) if on)
    lad = ladder_read(date, spy)
    buy = signal in ("STRONG_BUY", "BUY_WATCH")
    # "Follow the whales": at least one confirmation must come from dealer
    # positioning / price (GEX positive 2 days, or SPY back above zero gamma).
    # Without this, calm-before-the-storm days (e.g. 2026-10-30: contango, VIX
    # <22, credit flat) counted as "confirmed" right before the Nov 5 drop.
    whale_conf = checks[2][1] or checks[3][1]
    confirmed = n_conf >= 3 and whale_conf

    if lad and lad["tranches_hit"] > 0:
        t1, t2, t3 = lad["tiers"]
        sb = (lad.get("study") or {}).get("single_buy", {}).get("at_-8pct", {})
        sw = (lad.get("study") or {}).get("deep_switch", {}).get("second_leg", {})
        fo = lad.get("first_oversold")
        if lad["mode"] == "NORMAL":
            action, tone = "BUY ZONE: SINGLE BUY", "green"
            head = (f"SPY is {abs(lad['drawdown_pct']):.1f}% below its {lad['ath_date']} high. Normal-correction plan: one buy. "
                    f"The buy zone opened at -8% ({t1['price']:.2f}) on {t1['hit_date']}.")
            if sb:
                head += (f" History: one buy at -8% returned a median {sb['median_12m']:+.1f}% over 12 months "
                         f"({sb['positive_12m']}/{sb['filled']} positive), usually after about {sb['median_worst_after']:.0f}% more first.")
            if fo and t2["price"]:
                head += (f" Switch to the 3-buy deep-drop plan only if SPY closes below {t2['price']:.2f} "
                         f"(5% under the {fo['date']} first-oversold close of {fo['close']:.2f})")
                head += (f": that second leg came in {sw['deep_caught']} drops of 20%+ since 1995 and {sw['mild_false_alarms']} mild corrections."
                         if sw else ".")
            else:
                head += " The deep-drop switch level is set once RSI first goes oversold."
        else:
            action, tone = "DEEP-DROP MODE: 3 BUYS", "amber"
            head = (f"SPY made a second leg on {t2['hit_date']} (closed below {t2['price']:.2f}, 5% under the first-oversold close), "
                    f"the pattern of every 20%+ drop since 1995. Plan: Buy 1 at -8% ({t1['price']:.2f}), "
                    f"Buy 2 at the second leg ({t2['price']:.2f}), Buy 3 at -25% ({t3['price']:.2f}) or after 5 straight closes above "
                    f"the 50-day average (now {lad['ma50']:.2f}), whichever comes first.")
            if t3["hit_date"]:
                head += f" Buy 3 triggered on {t3['hit_date']}."
            elif credit_2d:
                head += " Credit is breaking, so use -25% for Buy 3, not the 50-day reclaim."
        if stress and lad["mode"] == "NORMAL":
            head += f" Fear is still high ({stress_why}), so a retest is likely; that's not a reason for a second buy unless the switch level breaks."
        elif confirmed:
            head += f" {n_conf}/5 confirmations are in, so the bounce has support."
    elif stress:
        action, tone = "NO RUSH", "amber"
        head = (f"Fear is high ({stress_why}). Not a sell signal: hold, but don't add in size yet."
                + (f" The buy zone opens at {lad['tiers'][0]['price']:.2f} (-8% from the high)." if lad else ""))
    elif buy and confirmed:
        action, tone = "ADD", "green"
        head = f"Buy setup with {n_conf}/5 confirmations in. Scale in."
    elif buy:
        action, tone = "WAIT FOR CONFIRMATION", "amber"
        head = f"Buy setup is building, but only {n_conf}/5 confirmations. Don't be first."
    elif signal == "CAUTION":
        action, tone = "TIGHTEN", "amber"
        head = "Regime weakening. No new size; not a sell signal on its own."
    else:
        action, tone = "HOLD", "blue"
        head = "No buy setup and no stress. Hold."

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
    ro_ = rsi_read(date, spy) or {}
    if ro_.get("rsi") is not None:
        txt = f"RSI(14) {ro_['rsi']}"
        if ro_.get("first_oversold_date"):
            txt += (f"; first oversold {ro_['first_oversold_date']} at {ro_['first_oversold_close']:.2f}"
                    f" (low since {ro_['low_since']:.2f}; typical retest zone ~{ro_['retest_zone']:.0f})")
        reasons.append({"label": "RSI", "text": txt, "tone": "green" if ro_["rsi"] < 30 else "amber" if ro_["rsi"] < 40 else "gray"})
    try:
        with open("money_flow.json", encoding="utf-8") as fh:
            mf = json.load(fh)
    except (OSError, ValueError):
        mf = None
    if mf and mf.get("percentile") is not None:
        h = mf.get("history_for_this_quintile") or {}
        txt = (f"{mf['state'].title()}: risk appetite at the {mf['percentile']:.0f}th percentile "
               f"({'falling' if (mf.get('score_20d_change') or 0) < 0 else 'rising'} over 20 days).")
        moves = [p_ for p_ in mf["pairs"] if p_.get("z") is not None and abs(p_["z"]) >= 1]
        if moves:
            def side(p_):
                if p_["key"] == "dollar_inverted":
                    return "into the dollar" if not p_["risk_on"] else "out of the dollar"
                a, b = p_["name"].split(" vs ")
                win, lose = (a, b) if p_["risk_on"] else (b, a)
                fix = {"us": "US", "em": "EM", "treasuries": "Treasuries"}
                w_, l_ = (fix.get(x.lower(), x.lower()) for x in (win, lose))
                return f"{w_} over {l_}"
            txt += " Biggest moves: " + "; ".join(side(p_) for p_ in moves) + "."
        if h.get("n"):
            txt += (f" Since 2010 at this level, a 10%+ drop followed within 120 days {h['drop10_pct']:.0f}% of the time "
                    f"(all days {mf['history_all_days']['drop10_pct']:.0f}%).")
        if mf.get("risk_on_trigger_today"):
            txt += " RISK-ON TRIGGER: money is rotating back toward risk during a drawdown, the 'whales returning' signal."
        elif mf.get("spy_vs_high_pct", 0) <= -8:
            txt += " Watching for money to rotate back toward risk (score up 0.5+ over 20 days) to confirm adding more."
        reasons.append({"label": "Money flow", "text": txt,
                        "tone": "green" if mf.get("risk_on_trigger_today") or mf["state"] == "RISK-ON FLOWS" else "amber" if mf["state"] == "RISK-OFF FLOWS" else "gray"})
    cv = curve_read(date)
    if cv:
        h, b = cv["hist_2010"], cv["base_2010"]
        txt = (f"{cv['regime'].title()} ({cv['meaning']}). 2y {cv['y2']:.2f}%, 10y {cv['y10']:.2f}%, spread {cv['spread']:+.2f}"
               + (" (INVERTED)" if cv["inverted"] else "")
               + (f"; 20d change 2y {cv['chg2']:+.2f}, 10y {cv['chg10']:+.2f}" if cv["chg2"] is not None else ""))
        if h.get("n") and b.get("n"):
            txt += (f". Since 2010, SPY in this regime: median {h['median_120d']:+.1f}% over 120d with a 10%+ drop "
                    f"{h['drop10_120d_pct']:.0f}% of the time (all days: {b['median_120d']:+.1f}%, {b['drop10_120d_pct']:.0f}%)")
        txt += (f". CURVE CAUTION ON ({', '.join(cv['caution_why'])}): use half size for new adds, especially TQQQ. Not a sell signal"
                if cv["caution"] else ". Curve caution off")
        reasons.append({"label": "Yield curve", "text": txt, "tone": "amber" if cv["caution"] else "gray"})
    tq = tqqq_read(date)
    if tq:
        sd = tq["study"] or {}
        if tq["status"] == "NOT YET":
            txt = (f"not yet: QQQ {tq['qqq_dd_pct']:+.1f}% from its high; the entry zone opens at QQQ {tq['trigger_level']:.2f} (-20%), "
                   f"or at -15% with RSI<30 and VIX>30")
            tone_ = "gray"
        elif tq["status"] == "ZONE OPEN":
            txt = (f"entry zone open since {tq['entry_date']} (QQQ {tq['entry_qqq']:.2f}, {tq['entry_dd_pct']:+.1f}%)"
                   + (f"; past entries returned a median {sd['median_tqqq_12m']:+.0f}% in 12 months ({sd['positive_12m']}/{sd['fired']} positive)"
                      if sd.get("median_tqqq_12m") is not None else "")
                   + f". Stop adding if QQQ closes below {tq['guard_level']:.2f} (10% under the entry)"
                   + (". Curve caution is ON: half size" if cv and cv.get("caution") else ""))
            tone_ = "green"
        else:
            txt = (f"STOP ADDING: QQQ closed 10% below the {tq['entry_date']} entry on {tq['guard_hit']}, the pattern of the 2000 and 2022 bear markets. "
                   f"No more leveraged buys; any further buys go to the SPY plan")
            tone_ = "red"
        reasons.append({"label": "TQQQ", "text": txt, "tone": tone_})
    if lad:
        reasons.insert(1, {"label": "From high", "text": f"SPY {lad['drawdown_pct']:+.1f}% vs {lad['ath']:.2f} ({lad['ath_date']})",
                           "tone": "green" if lad["tranches_hit"] else "gray"})
    out = {
        "date": date, "action": action, "tone": tone, "headline": head,
        "confirmations": n_conf, "confirmations_total": len(checks),
        "checks": [{"label": l, "ok": bool(ok)} for l, ok in checks],
        "reasons": reasons, "flow_date": flow_date, "ladder": lad, "rsi_oversold": ro_, "tqqq": tq, "yield_curve": cv, "money_flow": mf,
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
    lad = q.get("ladder") or {}
    if lad.get("tranches_hit"):
        hit = [f"{t['label'].split(' (')[0]} {t['price']:.0f}" + (" ✓" if t["hit_date"] else "")
               for t in lad["tiers"] if t.get("price")]
        lines.append(f"• Plan ({lad.get('mode', '').lower()}): " + " | ".join(hit))
    return "\n".join(lines).replace("*", "").replace("_", " ").replace("`", "")


if __name__ == "__main__":
    main()
