"""
ladder_history.py — buy-low ladder evidence for SPY (1995+) and QQQ (1999+).

For every drawdown episode (from an all-time-high close until the next new
all-time high), records the first day the index closed at each tier below
its ATH (-5, -8, -10, -15, -20, -25, -30, -40%). For each tier: how often
the decline went on to the next tiers, the final bottom, how long until the
bottom and the recovery, and forward returns from buying at that tier.

Credit split (SPY, 2007+ where HYG/IEF exist in flow_history.csv): HYG/IEF
20-day change at the tier-cross day. Calm credit (> -1.5%) vs stressed.

Writes research/drawdown_2026/ladder_history.json and prints tables.
"""
import csv, json, os, statistics as st
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
TIERS = [-5, -8, -10, -15, -20, -25, -30, -40]

def series():
    spy = {}
    with open(os.path.join(ROOT, "deep_history_backtest_log.csv")) as fh:
        for r in csv.DictReader(fh):
            if r.get("spy_close"): spy[r["date"]] = float(r["spy_close"])
    qqq, hie = {}, {}
    with open(os.path.join(ROOT, "flow_history.csv")) as fh:
        for r in csv.DictReader(fh):
            if r.get("spy"): spy[r["date"]] = float(r["spy"])  # flow_history extends past Aug 2026
            if r.get("qqq"): qqq[r["date"]] = float(r["qqq"])
            if r.get("hyg_ief"): hie[r["date"]] = float(r["hyg_ief"])
    return spy, qqq, hie

def episodes(px, hie=None):
    D = sorted(px); C = [px[d] for d in D]
    out, ath, ath_i, cur = [], C[0], 0, None
    for i, c in enumerate(C):
        if c >= ath:
            if cur: cur["recovered"] = D[i]; cur["days_to_recover"] = i - cur["ath_i"]; out.append(cur); cur = None
            ath, ath_i = c, i; continue
        dd = (c / ath - 1) * 100
        if dd <= TIERS[0] and cur is None:
            cur = {"ath_date": D[ath_i], "ath": ath, "ath_i": ath_i, "tiers": {}, "bottom": dd, "bottom_date": D[i], "recovered": None}
        if cur:
            if dd < cur["bottom"]: cur["bottom"], cur["bottom_date"] = dd, D[i]
            for t in TIERS:
                if dd <= t and str(t) not in cur["tiers"]:
                    fw = {}
                    for h, lab in ((63, "3m"), (126, "6m"), (252, "12m")):
                        fw[lab] = round((C[i + h] / c - 1) * 100, 2) if i + h < len(C) else None
                    w = C[i:i + 253]
                    cr = None
                    if hie is not None:
                        a, b = hie.get(D[i]), hie.get(D[i - 20]) if i >= 20 else None
                        cr = round((a / b - 1) * 100, 2) if a and b else None
                    cur["tiers"][str(t)] = {"date": D[i], "price": c, "fwd": fw, "worst_after_12m": round((min(w) / c - 1) * 100, 2), "credit20": cr}
    if cur: cur["recovered"] = None; out.append(cur)
    return out

def table(name, eps, current_dd=None):
    rows = []
    print(f"\n{name}: {len(eps)} drawdown episodes of 5%+ (open episode included)")
    print(f"{'tier':>5} {'n':>3} {'went to -10':>11} {'-15':>5} {'-20':>5} {'-30':>5} {'med bottom':>10} {'med 6m':>7} {'med 12m':>8} {'12m>0':>6} {'med worst 12m':>13}")
    for t in TIERS:
        hit = [e for e in eps if str(t) in e["tiers"]]
        closed = [e for e in hit if e["recovered"] or e is not eps[-1]]
        if not hit: continue
        def frac(x): 
            c = [e for e in closed if e is not eps[-1]] or closed
            return f"{100*sum(1 for e in c if e['bottom']<=x)/len(c):.0f}%" if x < t else "—"
        f6 = [e["tiers"][str(t)]["fwd"]["6m"] for e in hit if e["tiers"][str(t)]["fwd"]["6m"] is not None]
        f12 = [e["tiers"][str(t)]["fwd"]["12m"] for e in hit if e["tiers"][str(t)]["fwd"]["12m"] is not None]
        wr = [e["tiers"][str(t)]["worst_after_12m"] for e in hit if e["tiers"][str(t)]["fwd"]["12m"] is not None]
        bt = [e["bottom"] for e in hit if e is not eps[-1]]
        r = {"tier": t, "n": len(hit), "to_m10": frac(-10), "to_m15": frac(-15), "to_m20": frac(-20), "to_m30": frac(-30),
             "median_bottom": round(st.median(bt), 1) if bt else None,
             "median_6m": round(st.median(f6), 1) if f6 else None, "median_12m": round(st.median(f12), 1) if f12 else None,
             "pos_12m": f"{sum(x>0 for x in f12)}/{len(f12)}", "median_worst_12m": round(st.median(wr), 1) if wr else None}
        rows.append(r)
        print(f"{t:>5} {len(hit):>3} {r['to_m10']:>11} {r['to_m15']:>5} {r['to_m20']:>5} {r['to_m30']:>5} {r['median_bottom']!s:>10} {r['median_6m']!s:>7} {r['median_12m']!s:>8} {r['pos_12m']:>6} {r['median_worst_12m']!s:>13}")
    return rows

def main():
    spy, qqq, hie = series()
    se, qe = episodes(spy, hie), episodes(qqq)
    res = {"spy": table("SPY (1995+)", se), "qqq": table("QQQ (1999+)", qe)}
    # Credit split for SPY tier crossings since 2007
    print("\nSPY tier crossings 2007+, split by credit (HYG/IEF 20d change on the cross day):")
    split = {}
    for t in (-8, -10, -15):
        for lab, cond in (("calm", lambda x: x > -1.5), ("stressed", lambda x: x <= -1.5)):
            g = [e for e in se if str(t) in e["tiers"] and e["tiers"][str(t)]["credit20"] is not None and cond(e["tiers"][str(t)]["credit20"])]
            bt = [e["bottom"] for e in g if e is not se[-1]]
            f12 = [e["tiers"][str(t)]["fwd"]["12m"] for e in g if e["tiers"][str(t)]["fwd"]["12m"] is not None]
            split[f"{t}_{lab}"] = {"n": len(g), "median_bottom": round(st.median(bt), 1) if bt else None,
                                    "deeper_than_m20": f"{sum(b<=-20 for b in bt)}/{len(bt)}",
                                    "median_12m": round(st.median(f12), 1) if f12 else None, "dates": [e["tiers"][str(t)]["date"] for e in g]}
            print(f"  {t}% {lab:8s} n={len(g)} median bottom {split[f'{t}_{lab}']['median_bottom']} | reached -20%: {split[f'{t}_{lab}']['deeper_than_m20']} | median 12m fwd {split[f'{t}_{lab}']['median_12m']} | {split[f'{t}_{lab}']['dates']}")
    res["spy_credit_split"] = split
    res["spy_episodes"] = [{k: v for k, v in e.items() if k != "tiers"} | {"tiers_hit": list(e["tiers"])} for e in se]
    res["qqq_episodes"] = [{k: v for k, v in e.items() if k != "tiers"} | {"tiers_hit": list(e["tiers"])} for e in qe]
    print("\nSPY episodes that reached -20% or worse:", [(e["ath_date"], round(e["bottom"], 1), e["bottom_date"]) for e in se if e["bottom"] <= -20])
    print("Current SPY episode:", {k: se[-1][k] for k in ("ath_date", "ath", "bottom", "bottom_date", "recovered")}, list(se[-1]["tiers"]))
    print("Current QQQ episode:", {k: qe[-1][k] for k in ("ath_date", "ath", "bottom", "bottom_date", "recovered")}, list(qe[-1]["tiers"]))
    with open(os.path.join(HERE, "ladder_history.json"), "w") as fh: json.dump(res, fh, indent=1, default=str)

if __name__ == "__main__": main()
