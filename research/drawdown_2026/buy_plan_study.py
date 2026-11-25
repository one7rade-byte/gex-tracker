"""
buy_plan_study.py — when to buy once, and when a drop deserves 3 buys.

Simon's rule (2026-11-25): one buy in a normal correction; split into 3
buys only for a black-swan / deep multi-leg drop.

Uses every SPY drop since 1995 that reached -8% from an all-time high:
  1. Single-buy timing: buy once at -8%, at -10%, at the first RSI(14)<30
     close, or at the first RSI<30 close with VIX>30. Return 12 months later,
     how often it filled, and the worst point after buying.
  2. Deep-drop switch: which early signal separates the drops that went on
     to -20% or worse? Tested: the "second leg" (a close 5%+ below the first
     oversold close) and a credit break (HYG/IEF down 3%+ over 20 sessions,
     2007+ only).

Writes research/drawdown_2026/buy_plan_study.json (read by quick_action.py).
"""
import csv, json, os, statistics as st, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "research", "rsi_divergence"))
import rsi_study as R  # noqa: E402

SECOND_LEG = 0.95  # close at or below 95% of the first-oversold close


def main():
    spy, _, vix = R.load()
    D = sorted(spy); C = [spy[d] for d in D]; n = len(C); RS = R.rsi(C)
    hie = {}
    with open(os.path.join(ROOT, "flow_history.csv")) as fh:
        for r in csv.DictReader(fh):
            if r.get("hyg_ief"): hie[r["date"]] = float(r["hyg_ief"])
    eps, ath, ai, cur = [], C[0], 0, None
    for i, c in enumerate(C):
        if c >= ath:
            if cur: cur["end"] = i; eps.append(cur); cur = None
            ath, ai = c, i; continue
        if c / ath - 1 <= -0.08 and cur is None:
            cur = {"ath": ath, "ai": ai, "start": i}
    if cur: cur["end"] = None; eps.append(cur)
    for e in eps:
        end = e["end"] or n
        e["bottom"] = min(C[e["ai"]:end]) / e["ath"] - 1
        e["os"] = next((i for i in range(e["ai"], end) if RS[i] is not None and RS[i] < 30), None)
        e["leg2"] = next((i for i in range(e["os"], end) if C[i] <= C[e["os"]] * SECOND_LEG), None) if e["os"] is not None else None
        e["credit"] = next((i for i in range(e["ai"], end) if i >= 20 and D[i] in hie and D[i - 20] in hie
                            and hie[D[i]] / hie[D[i - 20]] - 1 <= -0.03), None)
    done = [e for e in eps if e["start"] + 252 < n]

    def single(rule):
        out = []
        for e in done:
            i = rule(e)
            if i is None or i + 252 >= n:
                continue
            out.append(((C[i + 252] / C[i] - 1) * 100, (min(C[i:i + 253]) / C[i] - 1) * 100))
        return {"filled": len(out), "of": len(done),
                "median_12m": round(st.median([x[0] for x in out]), 1),
                "positive_12m": sum(1 for x in out if x[0] > 0),
                "median_worst_after": round(st.median([x[1] for x in out]), 1),
                "worst_12m": round(min(x[0] for x in out), 1)}

    rules = {
        "at_-8pct": single(lambda e: e["start"]),
        "at_-10pct": single(lambda e: next((i for i in range(e["start"], e["end"] or n) if C[i] / e["ath"] - 1 <= -0.10), None)),
        "first_oversold": single(lambda e: e["os"]),
        "first_oversold_vix30": single(lambda e: next((i for i in range(e["ai"], e["end"] or n)
                                                         if RS[i] and RS[i] < 30 and vix.get(D[i], 0) > 30), None)),
    }
    deep = [e for e in done + [eps[-1]] if e["bottom"] <= -0.20]
    mild = [e for e in done if e["bottom"] > -0.14]
    big = [e for e in done if -0.20 < e["bottom"] <= -0.14]
    switch = {
        "second_leg": {"deep_caught": f"{sum(1 for e in deep if e['leg2'])}/{len(deep)}",
                       "big_14_20_fired": f"{sum(1 for e in big if e['leg2'])}/{len(big)}",
                       "mild_false_alarms": f"{sum(1 for e in mild if e['leg2'])}/{len(mild)}",
                       "median_dd_when_fired": round(100 * st.median([C[e['leg2']] / e['ath'] - 1 for e in done + [eps[-1]] if e["leg2"]]), 1)},
        "credit_break_2007plus": {"deep_caught": f"{sum(1 for e in deep if e['credit'] and D[e['ai']] >= '2007-05')}/{sum(1 for e in deep if D[e['ai']] >= '2007-05')}",
                                  "mild_false_alarms": f"{sum(1 for e in mild if e['credit'] and D[e['ai']] >= '2007-05')}/{sum(1 for e in mild if D[e['ai']] >= '2007-05')}"},
    }
    episodes = [{"peak": D[e["ai"]], "bottom_pct": round(100 * e["bottom"], 1),
                 "first_oversold": D[e["os"]] if e["os"] is not None else None,
                 "second_leg": D[e["leg2"]] if e["leg2"] else None,
                 "second_leg_dd_pct": round(100 * (C[e["leg2"]] / e["ath"] - 1), 1) if e["leg2"] else None,
                 "credit_break": D[e["credit"]] if e["credit"] else None} for e in done + [eps[-1]]]
    out = {"n_completed": len(done), "single_buy": rules, "deep_switch": switch, "episodes": episodes}
    with open(os.path.join(HERE, "buy_plan_study.json"), "w") as fh:
        json.dump(out, fh, indent=1)
    print(json.dumps({"single_buy": rules, "deep_switch": switch}, indent=1))


if __name__ == "__main__":
    main()
