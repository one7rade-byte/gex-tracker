"""
curve_study.py — do the 2y/10y yield-curve regimes tell us anything about SPY?

Regimes (20-session change, see yield_curve.py): BULL STEEPENER, BULL
FLATTENER, BEAR STEEPENER, BEAR FLATTENER, FLAT (spread moved under 10bp).
Also tests the curve LEVEL: inverted (10y-2y < 0) and the "un-inversion"
(first day back above 0 after 60+ inverted sessions), the classic
late-cycle / recession warning.

SPY from deep_history + flow_history (1995+). Outcomes: SPY return over the
next 60 and 120 sessions, and the chance of a 10%+ drop (worst close vs the
signal-day close) within 120 sessions, compared with the base rate over all
days. Split pre-2010 / 2010+ to check the result holds across eras.

Writes research/yield_curve/curve_study.json.
"""
import csv, json, os, statistics as st, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "research", "rsi_divergence"))
import rsi_study as R  # noqa: E402


def main():
    spy, _, _ = R.load()
    with open(os.path.join(ROOT, "yield_curve.csv")) as fh:
        yc = {r["date"]: r for r in csv.DictReader(fh)}
    D = [d for d in sorted(spy) if d in yc and yc[d].get("regime")]
    C = [spy[d] for d in D]; n = len(C)

    def outcome(i):
        if i + 120 >= n:
            return None
        return ((C[i + 60] / C[i] - 1) * 100, (C[i + 120] / C[i] - 1) * 100,
                min(C[i + 1:i + 121]) / C[i] - 1 <= -0.10)

    def summ(idx):
        o = [outcome(i) for i in idx]; o = [x for x in o if x]
        if not o:
            return {"n": 0}
        return {"n": len(o), "median_60d": round(st.median(x[0] for x in o), 2),
                "median_120d": round(st.median(x[1] for x in o), 2),
                "up_120d_pct": round(100 * sum(x[1] > 0 for x in o) / len(o), 1),
                "drop10_120d_pct": round(100 * sum(x[2] for x in o) / len(o), 1)}

    res = {"from": D[0], "to": D[-1], "all_days": summ(range(n)), "by_regime": {}, "by_era": {}}
    regs = ["BULL STEEPENER", "BULL FLATTENER", "BEAR STEEPENER", "BEAR FLATTENER", "FLAT"]
    for g in regs:
        idx = [i for i in range(n) if yc[D[i]]["regime"] == g]
        res["by_regime"][g] = summ(idx) | {"share_of_days_pct": round(100 * len(idx) / n, 1)}
    for era, lo, hi in (("1995-2009", "1995", "2010"), ("2010+", "2010", "2100")):
        res["by_era"][era] = {"all_days": summ([i for i in range(n) if lo <= D[i] < hi])}
        for g in regs:
            res["by_era"][era][g] = summ([i for i in range(n) if yc[D[i]]["regime"] == g and lo <= D[i] < hi])
    # Inversion and un-inversion
    sp = [float(yc[d]["spread_10_2"]) for d in D]
    inv = [i for i in range(n) if sp[i] < 0]
    res["inverted"] = summ(inv) | {"share_of_days_pct": round(100 * len(inv) / n, 1)}
    unin, run = [], 0
    for i in range(n):
        if sp[i] < 0:
            run += 1
        else:
            if run >= 60:
                unin.append(i)
            run = 0
    res["uninversion_events"] = [{"date": D[i], "spy_120d": round((C[i + 120] / C[i] - 1) * 100, 1) if i + 120 < n else None,
                                  "worst_250d": round((min(C[i + 1:i + 251]) / C[i] - 1) * 100, 1) if i + 250 < n else None}
                                 for i in unin]
    res["now"] = {k: yc[D[-1]].get(k) for k in ("date", "y2", "y10", "spread_10_2", "chg2_20d", "chg10_20d", "regime")}
    with open(os.path.join(HERE, "curve_study.json"), "w") as fh:
        json.dump(res, fh, indent=1)
    a = res["all_days"]
    print(f"{res['from']} → {res['to']} | ALL days n={a['n']}: 60d {a['median_60d']}%, 120d {a['median_120d']}%, up {a['up_120d_pct']}%, 10%+ drop {a['drop10_120d_pct']}%")
    for g, v in res["by_regime"].items():
        print(f"{g:15s} {v['share_of_days_pct']:5.1f}% of days | 60d {v['median_60d']}% 120d {v['median_120d']}% up {v['up_120d_pct']}% | 10%+ drop {v['drop10_120d_pct']}%")
    for era, v in res["by_era"].items():
        print(era, {g: (x.get("n"), x.get("median_120d"), x.get("drop10_120d_pct")) for g, x in v.items()})
    i_ = res["inverted"]
    print(f"INVERTED {i_['share_of_days_pct']}% of days | 120d {i_['median_120d']}% | 10%+ drop {i_['drop10_120d_pct']}%")
    print("un-inversions:", res["uninversion_events"])
    print("now:", res["now"])


if __name__ == "__main__":
    main()
