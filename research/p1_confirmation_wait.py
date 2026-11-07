"""P1 follow-up: for setups blocked ONLY by vol_score (group B in p1_vol_gate.py),
compare entering on the blocked day vs waiting for the current gate to pass
(first later day with composite >= 1, within 20 trading days). Also: same
question for every legs episode (first legs day vs first comp>=1 legs day).
Run from repo root: python3 research/p1_confirmation_wait.py"""
import runpy, statistics as st
g = runpy.run_path("research/p1_vol_gate.py", run_name="lib")
D, legs, episodes = g["D"], g["legs"], g["episodes"]
C = [float(x) for x in [None] * 0] or None
import csv
closes = [float(r["spy_close"]) for r in csv.DictReader(open("deep_history_backtest_log.csv"))]

def mae(i, h=20):
    if i + h >= len(closes): return None
    return (min(closes[i+1:i+h+1]) / closes[i] - 1) * 100
def fwd(i, h=20):
    return (closes[i+h] / closes[i] - 1) * 100 if i + h < len(closes) else None

B = [d for d in D if legs(d) and d["comp"] < 1 and d["exvol"] >= 1]
rows = []
for b in episodes(B):
    i = b["i"]; j = next((k for k in range(i+1, min(i+21, len(D))) if D[k]["comp"] >= 1), None)
    end = i + 20  # common endpoint: 20d after the blocked day
    r = dict(blocked=b["date"], blocked_px=round(closes[i], 2), wait_days=(j - i) if j else None,
             confirm=D[j]["date"] if j else None,
             cost_of_wait_pct=round((closes[j]/closes[i]-1)*100, 2) if j else None,
             early_to_common_end=round((closes[end]/closes[i]-1)*100, 2) if end < len(closes) else None,
             late_to_common_end=round((closes[end]/closes[j]-1)*100, 2) if j and end < len(closes) and j < end else None,
             early_mae20=round(mae(i), 2) if mae(i) is not None else None,
             late_mae20=round(mae(j), 2) if j and mae(j) is not None else None,
             late_fwd20=round(fwd(j), 2) if j and fwd(j) is not None else None)
    rows.append(r)
for r in rows: print(r)
ok = [r for r in rows if r["confirm"] and r["late_mae20"] is not None]
print("\nB episodes:", len(rows), " with confirmation within 20d:", len(ok))
if ok:
    print("median cost of waiting %:", st.median(r["cost_of_wait_pct"] for r in ok),
          " mean:", round(st.mean(r["cost_of_wait_pct"] for r in ok), 2))
    print("mean MAE20 early:", round(st.mean(r["early_mae20"] for r in ok), 2),
          " late:", round(st.mean(r["late_mae20"] for r in ok), 2))
    print("mean to common end early:", round(st.mean(r["early_to_common_end"] for r in ok), 2),
          " late:", round(st.mean(r["late_to_common_end"] for r in ok if r["late_to_common_end"] is not None), 2))
