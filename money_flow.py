"""
money_flow.py — daily read of where money is moving across assets
(stocks, bonds, gold, credit, sectors, copper, the dollar, small caps, EM).

Same calculation as research/money_flow/flow_study.py (single source of
truth): 8 flow pairs, each the 60-session relative return of a risk asset vs
a safety asset, z-scored against its own past 2 years. The RISK APPETITE
SCORE is their average, ranked against its own past (percentile).

What the backtest supports (2010-02 → 2026-11, research/money_flow/FINDINGS.md):
  - Score in its bottom 20%: a 10%+ SPY drop followed within 120 sessions
    30.1% of the time vs 12.2% in the top 20% (all days 20.5%). This held in
    2009-17 and 2018+.
  - Put risk on: SPY 8%+ below its high AND the score up 0.5+ over 20
    sessions (money rotating back toward risk). The first signal per drop
    came after the low each time: 2010-07, 2011-10, 2019-01, 2020-04, 2022-05,
    2025-05 (median +15.6% over 120 sessions; 2022 was early).
  - Halving exposure whenever the score is in its bottom 20% cut max
    drawdown from -34% to -24%, at about 1 pt/yr of return.

Writes money_flow.json (dashboard card, Quick Action, Telegram). Runs in
gex_daily.yml after flow_extras.py.
"""
import json
import math
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "research", "money_flow"))
import flow_study as FS  # noqa: E402

OUT = os.path.join(ROOT, "money_flow.json")
STUDY = os.path.join(ROOT, "research", "money_flow", "flow_study.json")
NAMES = {
    "stocks_vs_bonds": "Stocks vs bonds", "stocks_vs_gold": "Stocks vs gold", "credit_vs_treasury": "Junk vs Treasuries",
    "cyclical_vs_defens": "Cyclicals vs defensives", "copper_vs_gold": "Copper vs gold", "dollar_inverted": "Dollar",
    "small_vs_large": "Small vs large caps", "em_vs_us": "EM vs US",
}


def main():
    rows = FS.load()
    raw, z, score, pct = FS.compute(rows)
    D = [r["date"] for r in rows]; S = [FS.f(r["spy"]) for r in rows]; n = len(rows)
    hi = max(S[max(0, n - 252):])
    chg20 = score[-1] - score[-21] if score[-1] is not None and score[-21] is not None else None
    dd = (S[-1] / hi - 1) * 100

    def trig(i):
        h = max(S[max(0, i - 251):i + 1])
        return (S[i] <= 0.92 * h and i >= 20 and score[i] is not None and score[i - 20] is not None
                and score[i] - score[i - 20] >= 0.5)
    last_trig = next((D[i] for i in range(n - 1, max(0, n - 260), -1) if trig(i)), None)
    p = pct[-1]
    state = "RISK-OFF FLOWS" if p is not None and p < 20 else "RISK-ON FLOWS" if p is not None and p >= 80 else "MIXED FLOWS"
    try:
        with open(STUDY, encoding="utf-8") as fh:
            st_ = json.load(fh)
    except (OSError, ValueError):
        st_ = {}
    q = st_.get("quintiles", {})
    qkey = None if p is None else list(q)[min(4, int(p // 20))] if q else None
    pairs = []
    for k in FS.PAIRS:
        r_, z_ = raw[k][-1], z[k][-1]
        if r_ is None:
            continue
        rel = 100 * (math.exp(r_) - 1)
        if k == "dollar_inverted":
            detail = f"dollar {100 * (math.exp(-r_) - 1):+.1f}% over 60 days"
        else:
            up, dn = (FS.LABELS[k][1], FS.LABELS[k][0])
            detail = f"{up} {'beat' if rel > 0 else 'lagged'} {dn} by {abs(rel):.1f}% over 60 days"
        pairs.append({"key": k, "name": NAMES[k], "toward": FS.LABELS[k][1] if r_ > 0 else FS.LABELS[k][0],
                      "risk_on": r_ > 0, "rel_60d_pct": round(rel, 2), "detail": detail,
                      "z": round(z_, 2) if z_ is not None else None})
    out = {"date": D[-1], "score": round(score[-1], 2) if score[-1] is not None else None,
           "percentile": round(p, 1) if p is not None else None, "score_20d_change": round(chg20, 2) if chg20 is not None else None,
           "state": state, "spy_vs_high_pct": round(dd, 1),
           "risk_on_trigger_today": trig(n - 1), "last_risk_on_trigger": last_trig,
           "pairs": sorted(pairs, key=lambda x: (x["z"] if x["z"] is not None else 0)),
           "history_for_this_quintile": q.get(qkey) if qkey else None, "history_quintile": qkey,
           "history_all_days": st_.get("all"), "risk_on_history": (st_.get("risk_on_in_drawdown") or {}).get("first_signal_per_episode"),
           "risk_on_history_dates": (st_.get("risk_on_in_drawdown") or {}).get("first_signal_dates")}
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1)
    print(f"{out['date']}: {state} | score {out['score']} ({out['percentile']} pct), 20d change {out['score_20d_change']} "
          f"| risk-on trigger today {out['risk_on_trigger_today']}, last {last_trig}")
    for x in out["pairs"]:
        print(f"  {x['name']:24s} → {x['toward']:18s} {x['detail']} (z {x['z']})")


if __name__ == "__main__":
    main()
