"""P5: early vs confirmation entries after SPY <= -3.5% one-day drops.

Rules were fixed before looking at results (mirroring the live event ledger,
research/event_2026_11_05 on branch claude/event-2026-11-05):
  A    trigger-day close (day 0)
  G5   first close <= -5% vs the 60d closing high before the trigger (day >= 0)
  H10  first close <= -10% vs that high
  I    first close with RSI14 < 30 (simple-average RSI, as deep_history_backtest.py)
  B    first contango close (VIX/VIX3M < 1), day > 0            [VIX3M from 2006-07]
  C    first close with VIX < 22, day >= 0
  C2   first close with VIX <= 0.8 x trigger-day VIX, day > 0   (era-neutral VIX rule)
  K    first close with HYG 5d >= 0 ("credit holding"), day > 0 [HYG from 2007-04]
  F    stabilization proxy: contango AND VIX < 22 AND HYG 5d >= 0, day > 0 (2007+)
  R    first close above the pre-drop close (drop fully retraced), day > 0
VIX9D < VIX (live checklist) has no deep history, so it is not tested.

Event = SPY close-to-close <= -3.5%, first of a cluster (>= 20 trading days since the
previous qualifying drop). Rules must fire within 60 trading days. Common endpoint
T+60 (trigger + 60 trading days). Closes only.
Data: deep_history_backtest_log.csv for 1995-1998, flow_history.csv for 1999+
(same unadjusted closes at the seam). Run from the repo root.
"""
import csv, json, sys, statistics as st
THR = float(sys.argv[1]) if len(sys.argv) > 1 else -3.5
SEP = sys.argv[2] if len(sys.argv) > 2 else "drop"  # "drop": >=20d since previous qualifying drop; "event": since previous event
OUT = "" if len(sys.argv) <= 1 else f"_{abs(THR)}_{SEP}"

rows = []
for r in csv.DictReader(open("deep_history_backtest_log.csv")):
    if r["date"] < "1999-01-01":
        rows.append(dict(date=r["date"], spy=float(r["spy_close"]), vix=float(r["vix"]) if r["vix"] else None,
                         vix3m=None, hyg=None))
for r in csv.DictReader(open("flow_history.csv")):
    f = lambda k: float(r[k]) if r[k] else None
    rows.append(dict(date=r["date"], spy=f("spy"), vix=f("vix"), vix3m=f("vix3m"), hyg=f("hyg")))
rows = [r for r in rows if r["spy"]]
N = len(rows)
P = [r["spy"] for r in rows]

def rsi(i, n=14):
    if i < n: return None
    g = [max(P[k] - P[k-1], 0) for k in range(i-n+1, i+1)]
    l = [max(P[k-1] - P[k], 0) for k in range(i-n+1, i+1)]
    al = sum(l) / n
    return 100.0 if al == 0 else 100 - 100 / (1 + (sum(g) / n) / al)

def hyg5(i):
    if i < 5 or rows[i]["hyg"] is None or rows[i-5]["hyg"] is None: return None
    return (rows[i]["hyg"] / rows[i-5]["hyg"] - 1) * 100

def contango(i):
    v, v3 = rows[i]["vix"], rows[i]["vix3m"]
    return None if v is None or v3 is None else v / v3 < 1

# events
ev, last = [], -999
for i in range(1, N):
    if (P[i] / P[i-1] - 1) * 100 <= THR:
        if SEP == "drop":
            if i - last >= 20: ev.append(i)
            last = i
        elif not ev or i - ev[-1] >= 20:
            ev.append(i)
W, END = 60, 60

def era(d): return "pre-2010" if d < "2010" else ("2010-17" if d < "2018" else "2018+")

def rule_fns(t):
    hi = max(P[max(0, t-60):t])
    v0 = rows[t]["vix"]
    have_ts = rows[t]["vix3m"] is not None
    have_cr = rows[t]["hyg"] is not None
    return {
        "A":   (True,  lambda i: i == t),
        "G5":  (True,  lambda i: (P[i]/hi-1)*100 <= -5),
        "H10": (True,  lambda i: (P[i]/hi-1)*100 <= -10),
        "I":   (True,  lambda i: (rsi(i) or 100) < 30),
        "B":   (have_ts, lambda i: i > t and contango(i) is True),
        "C":   (True,  lambda i: rows[i]["vix"] is not None and rows[i]["vix"] < 22),
        "C2":  (True,  lambda i: i > t and rows[i]["vix"] is not None and rows[i]["vix"] <= 0.8 * v0),
        "K":   (have_cr, lambda i: i > t and (hyg5(i) is not None and hyg5(i) >= 0)),
        "F":   (have_ts and have_cr, lambda i: i > t and contango(i) is True and rows[i]["vix"] < 22
                                               and hyg5(i) is not None and hyg5(i) >= 0),
        "R":   (True,  lambda i: i > t and P[i] > P[t-1]),
    }, hi

RULES = ["A", "G5", "H10", "I", "B", "C", "C2", "K", "F", "R"]
res, open_ev = [], []
for t in ev:
    fns, hi = rule_fns(t)
    resolved = t + END < N
    e = dict(date=rows[t]["date"], trig_px=P[t], drop=round((P[t]/P[t-1]-1)*100, 2),
             off_high=round((P[t-1]/hi-1)*100, 2), era=era(rows[t]["date"]), resolved=resolved, r={})
    e["near_high"] = e["off_high"] > -2
    end = min(t + END, N - 1)
    e["low_to_end"] = round((min(P[t:end+1]) / P[t] - 1) * 100, 2)
    for k in RULES:
        ok, fn = fns[k]
        if not ok: e["r"][k] = None; continue
        j = next((i for i in range(t, min(t + W, end) + 1) if fn(i)), None)
        if j is None: e["r"][k] = dict(fired=False); continue
        x = dict(fired=True, lag=j - t, px=P[j], cost=round((P[j]/P[t]-1)*100, 2))
        if j < end:
            x["to_end"] = round((P[end]/P[j]-1)*100, 2)
            x["mae_end"] = round((min(P[j+1:end+1])/P[j]-1)*100, 2)
        else:
            x["to_end"], x["mae_end"] = 0.0, 0.0
        if j + 20 < N:
            x["f20"] = round((P[j+20]/P[j]-1)*100, 2)
            x["mae20"] = round((min(P[j+1:j+21])/P[j]-1)*100, 2)
        e["r"][k] = x
    (res if resolved else open_ev).append(e)

def m(v): return round(st.mean(v), 2) if v else None
def md(v): return round(st.median(v), 2) if v else None

def summarize(E, label):
    out = {}
    print(f"\n=== {label}: {len(E)} events ===")
    print(f"{'rule':5} {'avail':>5} {'fired':>5} {'lag_med':>7} {'cost_avg':>8} {'cost_med':>8} {'toEnd_avg':>9} {'toEnd_med':>9} "
          f"{'hit_end':>7} {'MAEend':>7} {'P(MAE<=-5)':>10} {'f20':>6} {'hit20':>6} | vsA: {'dRet':>6} {'dMAE':>6} {'beatA':>6}")
    for k in RULES:
        av = [e for e in E if e["r"][k] is not None]
        fi = [e for e in av if e["r"][k]["fired"]]
        if not av: continue
        X = [e["r"][k] for e in fi]
        te = [x["to_end"] for x in X]; me = [x["mae_end"] for x in X]
        f20 = [x["f20"] for x in X if "f20" in x]
        # paired vs A, missed events count as cash (0 return, 0 MAE) for the "rule as a policy" view
        dret, dmae, beat = [], [], 0
        for e in av:
            a = e["r"]["A"]; x = e["r"][k]
            rr = x["to_end"] if x["fired"] else 0.0; mm = x["mae_end"] if x["fired"] else 0.0
            dret.append(rr - a["to_end"]); dmae.append(mm - a["mae_end"]); beat += rr > a["to_end"]
        row = dict(avail=len(av), fired=len(fi), lag_med=md([x["lag"] for x in X]),
                   cost_avg=m([x["cost"] for x in X]), cost_med=md([x["cost"] for x in X]),
                   to_end_avg=m(te), to_end_med=md(te), hit_end=round(100*sum(v > 0 for v in te)/len(te), 1) if te else None,
                   mae_end_avg=m(me), p_mae_le5=round(100*sum(v <= -5 for v in me)/len(me), 1) if me else None,
                   f20_avg=m(f20), hit20=round(100*sum(v > 0 for v in f20)/len(f20), 1) if f20 else None,
                   policy_dret_vs_A=m(dret), policy_dmae_vs_A=m(dmae), beat_A=f"{beat}/{len(av)}")
        out[k] = row
        print(f"{k:5} {row['avail']:>5} {row['fired']:>5} {str(row['lag_med']):>7} {str(row['cost_avg']):>8} {str(row['cost_med']):>8} "
              f"{str(row['to_end_avg']):>9} {str(row['to_end_med']):>9} {str(row['hit_end']):>7} {str(row['mae_end_avg']):>7} "
              f"{str(row['p_mae_le5']):>10} {str(row['f20_avg']):>6} {str(row['hit20']):>6} | {str(row['policy_dret_vs_A']):>9} "
              f"{str(row['policy_dmae_vs_A']):>6} {row['beat_A']:>6}")
    return out

# base: any day, T+60 return and MAE
base60 = [(P[i+60]/P[i]-1)*100 for i in range(N-60)]
basemae = [(min(P[i+1:i+61])/P[i]-1)*100 for i in range(N-60)]
print(f"Base (all days {rows[0]['date']}..): fwd60 avg {m(base60)} hit {round(100*sum(v>0 for v in base60)/len(base60),1)}% "
      f"MAE60 avg {m(basemae)} P(MAE60<=-5) {round(100*sum(v<=-5 for v in basemae)/len(basemae),1)}%")
for sub in ["2007+"]:
    idx = [i for i in range(N-60) if rows[i]["date"] >= "2007-04-11"]
    b = [base60[i] for i in idx]; bm = [basemae[i] for i in idx]
    print(f"Base 2007-04+: fwd60 avg {m(b)} hit {round(100*sum(v>0 for v in b)/len(b),1)}% MAE60 {m(bm)} "
          f"P(MAE60<=-5) {round(100*sum(v<=-5 for v in bm)/len(bm),1)}%")

print("\nEvents (date, drop, off 60d high before drop, low to T+60 vs trigger, era):")
for e in res + open_ev:
    tag = "" if e["resolved"] else "  [OPEN]"
    print(e["date"], e["drop"], e["off_high"], e["low_to_end"], e["era"], tag)

S = {"all": summarize(res, "ALL resolved"),
     "2007+": summarize([e for e in res if e["date"] >= "2007-04-11"], "2007-04+ (all rules available)")}
for er in ["pre-2010", "2010-17", "2018+"]:
    S[er] = summarize([e for e in res if e["era"] == er], er)
S["near_high"] = summarize([e for e in res if e["near_high"]], "near high (<2% off 60d high before drop)")
S["already_falling"] = summarize([e for e in res if not e["near_high"]], "already falling (>=2% off high)")

print("\nPer-event detail (rule: lag/cost/to_end/mae_end):")
for e in res + open_ev:
    parts = []
    for k in RULES:
        x = e["r"][k]
        if x is None: parts.append(f"{k}:na")
        elif not x["fired"]: parts.append(f"{k}:--")
        else: parts.append(f"{k}:{x['lag']}/{x['cost']:+}/{x.get('to_end', 0):+}/{x.get('mae_end', 0):+}")
    print(e["date"], ("OPEN " if not e["resolved"] else ""), " ".join(parts))

json.dump(dict(summary=S, events=res, open_events=open_ev), open(f"research/p5_confirmation_entries_results{OUT}.json", "w"),
          indent=1, default=str)

# Sensitivity: median paired difference, and mean excluding the two crash events (2008-09-15, 2020-02-27)
print("\nPaired vs A (missed = cash): median dRet / median dMAE; mean dRet / dMAE excluding 2008-09-15 and 2020-02-27")
for k in RULES:
    D_ = []
    for e in res:
        x, a = e["r"][k], e["r"]["A"]
        if x is None: continue
        rr = x["to_end"] if x["fired"] else 0.0; mm = x["mae_end"] if x["fired"] else 0.0
        D_.append((e["date"], rr - a["to_end"], mm - a["mae_end"]))
    ex = [d for d in D_ if d[0] not in ("2008-09-15", "2020-02-27")]
    print(f"{k:4} n={len(D_):2} med dRet {md([d[1] for d in D_])} med dMAE {md([d[2] for d in D_])} | ex-crash n={len(ex)} "
          f"mean dRet {m([d[1] for d in ex])} mean dMAE {m([d[2] for d in ex])}")
