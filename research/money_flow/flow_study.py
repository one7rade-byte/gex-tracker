"""
flow_study.py — where is money moving across assets, and does it help decide
when to take risk off or put it on?

Eight cross-asset "flow pairs", each the 60-session relative return of a
risk-on asset vs a safety asset (positive = money moving toward risk):
  stocks_vs_bonds     SPY vs TLT (long Treasuries)
  stocks_vs_gold      SPY vs GLD
  credit_vs_treasury  HYG vs IEF (junk vs 7-10y Treasuries)
  cyclical_vs_defens  XLY+XLK vs XLU+XLP
  copper_vs_gold      HG=F vs GC=F (growth vs fear)
  dollar (inverted)   -UUP 60d change (a rising dollar is risk-off)
  small_vs_large      IWM vs SPY
  em_vs_us            EEM vs SPY
Each pair is z-scored against its own trailing 2 years only (no look-ahead).
RISK APPETITE SCORE = the average of the 8 z-scores. Its percentile is ranked
against the score's own past only.

Tests (2009+, when every series has 2 years of history):
  1. Score quintile → SPY 60/120-session return and the chance of a 10%+ drop,
     vs all days; split 2009-2017 / 2018+.
  2. TAKE RISK OFF: SPY within 5% of its high AND score in its bottom 20%.
     Backtest: 50% exposure while on, vs always invested.
  3. PUT RISK ON: SPY 8%+ below its high AND the score rising 0.5+ over 20
     sessions (money rotating back toward risk). Forward returns vs all
     drawdown days, and vs buying at -8% with no flow condition.
Writes research/money_flow/flow_study.json and prints the tables.
"""
import bisect, csv, json, math, os, statistics as st

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
H, ZWIN = 60, 504

PAIRS = {
    "stocks_vs_bonds": (("spy",), ("tlt",)),
    "stocks_vs_gold": (("spy",), ("gld",)),
    "credit_vs_treasury": (("hyg",), ("ief",)),
    "cyclical_vs_defens": (("xly", "xlk"), ("xlu", "xlp")),
    "copper_vs_gold": (("copper",), ("gold",)),
    "dollar_inverted": ((), ("uup",)),
    "small_vs_large": (("iwm",), ("spy",)),
    "em_vs_us": (("eem",), ("spy",)),
}
LABELS = {
    "stocks_vs_bonds": ("bonds", "stocks"), "stocks_vs_gold": ("gold", "stocks"),
    "credit_vs_treasury": ("Treasuries", "junk bonds"), "cyclical_vs_defens": ("defensive sectors", "cyclicals/tech"),
    "copper_vs_gold": ("gold", "copper"), "dollar_inverted": ("the dollar", "out of the dollar"),
    "small_vs_large": ("large caps", "small caps"), "em_vs_us": ("US stocks", "emerging markets"),
}


def f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def load():
    with open(os.path.join(ROOT, "flow_history.csv"), newline="") as fh:
        return [r for r in csv.DictReader(fh) if f(r.get("spy"))]


def basket(r, keys):
    vals = [f(r.get(k)) for k in keys]
    return sum(vals) if vals and all(v for v in vals) else None


def compute(rows):
    """Per-day pair values (60d log relative return), z-scores and the score."""
    n = len(rows)
    raw = {p: [None] * n for p in PAIRS}
    for p, (up, dn) in PAIRS.items():
        for i in range(H, n):
            a1, a0 = (basket(rows[i], up), basket(rows[i - H], up)) if up else (1.0, 1.0)
            b1, b0 = basket(rows[i], dn), basket(rows[i - H], dn)
            if a1 and a0 and b1 and b0:
                raw[p][i] = math.log(a1 / a0) - math.log(b1 / b0)
    z = {p: [None] * n for p in PAIRS}
    for p in PAIRS:
        for i in range(n):
            win = [x for x in raw[p][max(0, i - ZWIN):i] if x is not None]
            if raw[p][i] is not None and len(win) >= ZWIN * 0.8:
                m, s = st.mean(win), st.pstdev(win)
                z[p][i] = (raw[p][i] - m) / s if s else 0.0
    score = [None] * n
    for i in range(n):
        v = [z[p][i] for p in PAIRS]
        if all(x is not None for x in v):
            score[i] = sum(v) / len(v)
    # percentile of the score vs its own past (expanding, no look-ahead)
    pct, hist = [None] * n, []
    for i in range(n):
        if score[i] is None:
            continue
        if len(hist) >= 250:
            pct[i] = 100 * bisect.bisect_left(hist, score[i]) / len(hist)
        bisect.insort(hist, score[i])
    return raw, z, score, pct


def main():
    rows = load()
    D = [r["date"] for r in rows]; S = [f(r["spy"]) for r in rows]; n = len(rows)
    raw, z, score, pct = compute(rows)
    idx = [i for i in range(n) if pct[i] is not None]
    k0 = idx[0]
    hi = [max(S[max(0, i - 251):i + 1]) for i in range(n)]

    def out(i):
        if i + 120 >= n:
            return None
        return ((S[i + 60] / S[i] - 1) * 100, (S[i + 120] / S[i] - 1) * 100, min(S[i + 1:i + 121]) / S[i] - 1 <= -0.10)

    def summ(ix):
        o = [out(i) for i in ix]; o = [x for x in o if x]
        if not o:
            return {"n": 0}
        return {"n": len(o), "median_60d": round(st.median(x[0] for x in o), 2), "median_120d": round(st.median(x[1] for x in o), 2),
                "up_120d_pct": round(100 * sum(x[1] > 0 for x in o) / len(o), 1),
                "drop10_pct": round(100 * sum(x[2] for x in o) / len(o), 1)}

    res = {"from": D[k0], "to": D[-1], "all": summ(idx), "quintiles": {}, "eras": {}}
    for q in range(5):
        lo, hi_ = 20 * q, 20 * (q + 1)
        res["quintiles"][f"Q{q+1} ({lo}-{hi_} pct)"] = summ([i for i in idx if lo <= pct[i] < hi_ or (q == 4 and pct[i] == 100)])
    for era, a, b in (("2009-2017", "2009", "2018"), ("2018+", "2018", "2100")):
        e = [i for i in idx if a <= D[i] < b]
        res["eras"][era] = {"all": summ(e), "bottom_20": summ([i for i in e if pct[i] < 20]), "top_20": summ([i for i in e if pct[i] >= 80])}

    # 2. Take risk off near highs
    off = [i for i in idx if S[i] >= 0.95 * hi[i] and pct[i] < 20]
    res["risk_off_near_high"] = summ(off) | {"days_pct": round(100 * len(off) / len(idx), 1),
                                              "base_near_high": summ([i for i in idx if S[i] >= 0.95 * hi[i]])}

    def bt(flag, lev=1.0):
        eq = pk = 1.0; mdd = 0.0
        for j in range(k0 + 1, n):
            r = S[j] / S[j - 1] - 1
            e = 0.5 if flag(j - 1) else 1.0
            eq *= 1 + e * r; pk = max(pk, eq); mdd = min(mdd, eq / pk - 1)
        yrs = (n - 1 - k0) / 252
        return round(100 * (eq ** (1 / yrs) - 1), 2), round(100 * mdd, 1)
    offset = set(off)
    res["risk_off_backtest"] = {"always": bt(lambda j: False), "half_when_on": bt(lambda j: j in offset),
                                "half_when_bottom20_any": bt(lambda j: pct[j] is not None and pct[j] < 20)}

    # 3. Put risk on during drawdowns
    dd = [i for i in idx if S[i] <= 0.92 * hi[i]]
    turn = [i for i in dd if i >= 20 and score[i - 20] is not None and score[i] - score[i - 20] >= 0.5]
    first_turn, last = [], -999
    for i in turn:
        if i - last > 40:
            first_turn.append(i)
        last = i
    res["risk_on_in_drawdown"] = {"all_drawdown_days": summ(dd), "score_rising": summ(turn), "first_signal_per_episode": summ(first_turn),
                                  "first_signal_dates": [D[i] for i in first_turn]}

    # Today
    cur = {p: {"z": round(z[p][-1], 2) if z[p][-1] is not None else None,
               "rel_60d_pct": round(100 * (math.exp(raw[p][-1]) - 1), 2) if raw[p][-1] is not None else None,
               "toward": LABELS[p][1] if (raw[p][-1] or 0) > 0 else LABELS[p][0]} for p in PAIRS}
    res["now"] = {"date": D[-1], "score": round(score[-1], 2) if score[-1] is not None else None,
                  "percentile": round(pct[-1], 1) if pct[-1] is not None else None,
                  "score_20d_change": round(score[-1] - score[-21], 2) if score[-1] is not None and score[-21] is not None else None,
                  "spy_vs_high_pct": round((S[-1] / hi[-1] - 1) * 100, 1), "pairs": cur}
    with open(os.path.join(HERE, "flow_study.json"), "w") as fh:
        json.dump(res, fh, indent=1)
    a = res["all"]
    print(f"{res['from']} → {res['to']} ALL n={a['n']}: 60d {a['median_60d']} 120d {a['median_120d']} up {a['up_120d_pct']}% drop10 {a['drop10_pct']}%")
    for k, v in res["quintiles"].items():
        print(f"  {k:16s} n={v['n']:4d} 60d {v['median_60d']:6} 120d {v['median_120d']:6} up {v['up_120d_pct']}% drop10 {v['drop10_pct']}%")
    for k, v in res["eras"].items():
        print(" ", k, {x: (y.get("n"), y.get("median_120d"), y.get("drop10_pct")) for x, y in v.items()})
    r_ = res["risk_off_near_high"]
    print(f"RISK OFF near high + bottom 20%: on {r_['days_pct']}% | n={r_['n']} 120d {r_['median_120d']} drop10 {r_['drop10_pct']}% vs near-high base {r_['base_near_high']['median_120d']} / {r_['base_near_high']['drop10_pct']}%")
    print("  backtest (CAGR, maxDD):", res["risk_off_backtest"])
    ro = res["risk_on_in_drawdown"]
    print(f"RISK ON in drawdown: all dd days 120d {ro['all_drawdown_days'].get('median_120d')} up {ro['all_drawdown_days'].get('up_120d_pct')}% | score rising {ro['score_rising'].get('median_120d')} up {ro['score_rising'].get('up_120d_pct')}% n={ro['score_rising'].get('n')} | first per episode {ro['first_signal_per_episode']} {ro['first_signal_dates']}")
    print("NOW:", json.dumps(res["now"]))


if __name__ == "__main__":
    main()
