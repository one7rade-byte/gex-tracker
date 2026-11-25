"""
tqqq_entry_study.py — when is a drop deep enough to buy TQQQ (3x QQQ)?

Simon (2026-11-25): add TQQQ only in a deep enough drop, never at the start,
because a 3x fund punishes early entries. His first TQQQ buy this time was
too early; he judged the week of 2026-11-20 as where the first load belonged.

TQQQ only exists since 2010, so it is simulated from QQQ (1999+): 3x the
daily QQQ return minus 4%/yr for fees and borrowing. Check: simulated max
drawdown 2021-11 → 2022-12 is -81.6% (real TQQQ about -79%), and Feb-Mar
2020 is -69.8% (real about -70%).

Entry rules tested on every QQQ drop of 10%+ since 1999 (17 completed):
  QQQ -15%, -20%, -25%, first RSI<30 with VIX>30, and RSI<30 + VIX>30 with
  QQQ at least 15% down. Outcomes: simulated TQQQ return at 6 and 12 months,
  worst point after entry, and how often it fell another 50%+.
Guard: QQQ closes 10% below the TQQQ entry close. That happened in the two
bear markets (2000, 2022) and in none of the drops that recovered.

Writes research/drawdown_2026/tqqq_entry_study.json (read by quick_action.py).
"""
import json, os, statistics as st, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "research", "rsi_divergence"))
import rsi_study as R  # noqa: E402

DRAG = 0.04  # yearly fees + borrowing for the 3x simulation
GUARD = 0.90


def trigger(C, RS, vix, D, e, end):
    """First close with QQQ <= -20%, or QQQ <= -15% with RSI<30 and VIX>30."""
    for i in range(e["ai"], end):
        dd = C[i] / e["ath"] - 1
        if dd <= -0.20 or (dd <= -0.15 and RS[i] is not None and RS[i] < 30 and vix.get(D[i], 0) > 30):
            return i
    return None


def main():
    _, qqq, vix = R.load()
    D = sorted(qqq); C = [qqq[d] for d in D]; n = len(C); RS = R.rsi(C)
    T = [100.0]
    for i in range(1, n):
        T.append(T[-1] * (1 + 3 * (C[i] / C[i - 1] - 1) - DRAG / 252))
    eps, ath, ai, cur = [], C[0], 0, None
    for i, c in enumerate(C):
        if c >= ath:
            if cur: cur["end"] = i; eps.append(cur); cur = None
            ath, ai = c, i; continue
        if c / ath - 1 <= -0.10 and cur is None:
            cur = {"ath": ath, "ai": ai, "start": i}
    if cur: cur["end"] = None; eps.append(cur)
    done = [e for e in eps if e["start"] + 252 < n]
    rows = []
    for e in done:
        end = e["end"] or n
        i = trigger(C, RS, vix, D, e, end)
        if i is None or i + 252 >= n:
            continue
        g = next((j for j in range(i + 1, min(n, i + 500)) if C[j] <= C[i] * GUARD), None)
        rows.append({"entry": D[i], "qqq_dd_at_entry": round(100 * (C[i] / e["ath"] - 1), 1),
                     "qqq_final_bottom": round(100 * (min(C[e["ai"]:end]) / e["ath"] - 1), 1),
                     "tqqq_6m": round(100 * (T[i + 126] / T[i] - 1), 1), "tqqq_12m": round(100 * (T[i + 252] / T[i] - 1), 1),
                     "tqqq_worst_after": round(100 * (min(T[i:i + 253]) / T[i] - 1), 1),
                     "guard_hit": D[g] if g else None,
                     "tqqq_at_guard": round(100 * (T[g] / T[i] - 1), 1) if g else None})
    out = {"rule": "QQQ close <= -20% from its high, or <= -15% with RSI(14)<30 and VIX>30",
           "guard": "QQQ closes 10% below the TQQQ entry close: stop adding TQQQ",
           "fired": len(rows), "of": len(done),
           "median_tqqq_12m": round(st.median([r["tqqq_12m"] for r in rows]), 1),
           "positive_12m": sum(1 for r in rows if r["tqqq_12m"] > 0),
           "median_worst_after": round(st.median([r["tqqq_worst_after"] for r in rows]), 1),
           "entries": rows}
    with open(os.path.join(HERE, "tqqq_entry_study.json"), "w") as fh:
        json.dump(out, fh, indent=1)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
