"""
P3 (IDEA_BACKLOG, signal accuracy): deeper-but-downgraded entries / second tranche.

Question: after a STRONG_BUY-type first entry, if price falls further (and the
signal downgrades), is adding a second tranche lower a good rule? Compared
against (a) holding the first tranche only and (b) putting all the money in on
the first fire, at fixed sizing, episode level.

Data: deep_history_backtest_log.csv (1995-10-17 .. 2026-08-21), closes only.
  SB  = STRONG_BUY proxy: composite>=1 & RSI14<50 & SKEW>138 & VIX>17 (as P1/P2;
        fires only from 2010 because of SKEW).
  SBX = same without the SKEW leg (fires 1995+) -> gives a by-era check.
Episode = first fire of a cluster whose fire days are separated by >10 trading
days (same as P2). Entry 1 = episode close P0 on day i0.

Tranche triggers (first close within W trading days after i0):
  Dx      close <= P0*(1-x%)                          x in 2,3,5
  Dx_dg   same, AND proxy composite < 1 that day (signal downgraded)
  Dx_on   same, AND proxy still firing that day (a re-fire below entry)
Common endpoint T = i0 + HOLD (20 or 30). Tranche bought at its close, held to T.

Strategies on a 2-unit budget (returns / MAE in % of the full budget):
  ALL  2 units at P0
  ONE  1 unit at P0, other unit idle (cash, 0%)
  TR   1 unit at P0 + 1 unit at the trigger close if it fires before T-5, else ONE
Portfolio MAE = worst mark-to-market P&L along i0+1..T, % of budget.

Base comparison: the same TR mechanics applied with entry 1 = every day
(day level) -> "is the edge from the signal, or from any -x% dip add?".

Live: regime_log.csv STRONG_BUY episodes (same gap rule) with SPY closes from
gex_log.csv through the latest day; windows still open are reported to date.

Run from repo root: python3 research/p3_second_tranche.py
"""
import csv, json, statistics as st
from collections import OrderedDict

OUT = OrderedDict()

def pct(a, b):
    return (b / a - 1) * 100

def fl(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None

def calc_rsi(c, period=14):  # replica of deep_history_backtest.calc_rsi (see p1/p2)
    if len(c) < period + 1:
        return None
    g = [max(c[k] - c[k - 1], 0) for k in range(1, len(c))]
    l = [max(c[k - 1] - c[k], 0) for k in range(1, len(c))]
    ag, al = sum(g[-period:]) / period, sum(l[-period:]) / period
    return 100.0 if al == 0 else 100 - 100 / (1 + ag / al)

rows = list(csv.DictReader(open("deep_history_backtest_log.csv")))
D = [r["date"] for r in rows]
C = [float(r["spy_close"]) for r in rows]
N = len(C)
comp = [fl(r["composite_score"]) for r in rows]
vix = [fl(r["vix"]) for r in rows]
skew = [fl(r["skew"]) for r in rows]
rsi = [calc_rsi(C[max(0, i - 14):i + 1]) if i >= 14 else None for i in range(N)]

def sb(i, use_skew=True):
    ok = comp[i] is not None and comp[i] >= 1 and rsi[i] is not None and rsi[i] < 50 \
        and vix[i] is not None and vix[i] > 17
    if use_skew:
        ok = ok and skew[i] is not None and skew[i] > 138
    return ok

FIRE = {"SB": [sb(i, True) for i in range(N)], "SBX": [sb(i, False) for i in range(N)]}

def episodes(fire, gap=10):
    out, last = [], None
    for i in range(N):
        if fire[i]:
            if last is None or i - last > gap:
                out.append(i)
            last = i
    return out

def trigger(i0, x, W, mode, fire, latest):
    """first day j in (i0, i0+W] (and j <= latest) where close <= P0*(1-x%) and the mode condition holds"""
    for j in range(i0 + 1, min(i0 + W, latest) + 1):
        if pct(C[i0], C[j]) <= -x:
            if mode == "any":
                return j
            if mode == "dg" and comp[j] is not None and comp[j] < 1:
                return j
            if mode == "on" and fire[j]:
                return j
    return None

def run(i0, x, W, mode, hold, fire):
    """returns dict for one entry; None if the window is incomplete"""
    T = i0 + hold
    if T >= N:
        return None
    j = trigger(i0, x, W, mode, fire, T - 5)  # tranche must have >=5 days left
    r0 = pct(C[i0], C[T])
    # path P&L (% of 2-unit budget)
    pa, po, pt = [], [], []
    for k in range(i0 + 1, T + 1):
        a = pct(C[i0], C[k])
        pa.append(a)                     # ALL: 2 units * a / 2 units
        po.append(a / 2)                 # ONE
        pt.append(a / 2 + (pct(C[j], C[k]) / 2 if (j is not None and k > j) else 0.0))
    ps = [a / 2 + (pct(C[i0 + 5], C[k]) / 2 if k > i0 + 5 else 0.0) for a, k in zip(pa, range(i0 + 1, T + 1))]
    rt = None if j is None else pct(C[j], C[T])
    further = None if j is None else min(pct(C[j], C[k]) for k in range(j + 1, T + 1))
    return dict(i0=i0, date=D[i0], fired=j is not None, lag=None if j is None else j - i0,
                tr_date=None if j is None else D[j], r0=r0, r_tr=rt, further_mae=further,
                ALL=pa[-1], ONE=po[-1], TR=pt[-1], STAG=ps[-1],
                mae_ALL=min(pa), mae_ONE=min(po), mae_TR=min(pt), mae_STAG=min(ps))

def agg(res):
    if not res:
        return None
    f = [r for r in res if r["fired"]]
    o = OrderedDict(n=len(res), fired=len(f), fire_pct=round(100 * len(f) / len(res), 1))
    if f:
        rt = [r["r_tr"] for r in f]
        o.update(tr_hit=round(100 * sum(v > 0 for v in rt) / len(rt), 1),
                 tr_avg=round(st.mean(rt), 2), tr_med=round(st.median(rt), 2),
                 tr_further_mae=round(st.mean(r["further_mae"] for r in f), 2),
                 tr_p_further_le_m3=round(100 * sum(r["further_mae"] <= -3 for r in f) / len(f), 1),
                 tr_worst=round(min(rt), 2),
                 entry1_avg_when_fired=round(st.mean(r["r0"] for r in f), 2))
    for s in ("ALL", "ONE", "TR", "STAG"):
        v = [r[s] for r in res]; m = [r["mae_" + s] for r in res]
        o[s] = OrderedDict(avg=round(st.mean(v), 2), hit=round(100 * sum(x > 0 for x in v) / len(v), 1),
                           mae_avg=round(st.mean(m), 2), mae_worst=round(min(m), 2),
                           p_mae_le_m3=round(100 * sum(x <= -3 for x in m) / len(m), 1))
    # return per unit of average capital deployed (TR deploys 1 + fire share)
    cap_tr = 1 + len(f) / len(res)
    o["TR_ret_per_unit_deployed"] = round(o["TR"]["avg"] * 2 / cap_tr, 2)
    o["ALL_ret_per_unit_deployed"] = o["ALL"]["avg"]
    return o

ERAS = OrderedDict([("full", ("0000", "9999")), ("pre_2010", ("0000", "2009-12-31")),
                    ("2010_2017", ("2010-01-01", "2017-12-31")), ("2018+", ("2018-01-01", "9999")),
                    ("2010+", ("2010-01-01", "9999"))])

def fmt(o):
    if o is None:
        return "n/a"
    s = f"n={o['n']:3d} fired {o['fired']:3d} ({o['fire_pct']:5.1f}%)"
    if o["fired"]:
        s += (f" | tranche->T hit {o['tr_hit']:5.1f}% avg {o['tr_avg']:+.2f} med {o['tr_med']:+.2f} "
              f"furtherMAE {o['tr_further_mae']:+.2f} P(<=-3) {o['tr_p_further_le_m3']:4.1f}% worst {o['tr_worst']:+.2f}")
    s += (f" || ALL {o['ALL']['avg']:+.2f}/{o['ALL']['hit']:.0f}%/MAE {o['ALL']['mae_avg']:+.2f}"
          f" ONE {o['ONE']['avg']:+.2f}/MAE {o['ONE']['mae_avg']:+.2f}"
          f" TR {o['TR']['avg']:+.2f}/{o['TR']['hit']:.0f}%/MAE {o['TR']['mae_avg']:+.2f} (worst {o['TR']['mae_worst']:+.2f})"
          f" STAG {o['STAG']['avg']:+.2f}/MAE {o['STAG']['mae_avg']:+.2f}"
          f" | per-unit TR {o['TR_ret_per_unit_deployed']:+.2f} vs ALL {o['ALL_ret_per_unit_deployed']:+.2f}")
    return s

GRID = [(x, W, m) for x in (2, 3, 5) for W in (5, 10, 20) for m in ("any", "dg", "on")]
detail = {}
for proxy in ("SB", "SBX"):
    eps = episodes(FIRE[proxy])
    OUT[proxy] = OrderedDict()
    print(f"\n===== {proxy}: {len(eps)} episodes ({D[eps[0]]}..{D[eps[-1]]}) =====")
    for hold in (20, 30):
        for (x, W, m) in GRID:
            key = f"D{x}_W{W}_{m}_H{hold}"
            OUT[proxy][key] = OrderedDict()
            line = []
            for era, (a, b) in ERAS.items():
                res = [r for r in (run(i, x, W, m, hold, FIRE[proxy]) for i in eps if a <= D[i] <= b) if r]
                o = agg(res); OUT[proxy][key][era] = o
                if era == "full":
                    detail[(proxy, key)] = res
                if proxy == "SB" and era not in ("2010+", "2018+", "2010_2017"):
                    continue
                print(f"  {key:16s} {era:9s} {fmt(o)}")

# Base: TR mechanics from every day (day level), main variants only
print("\n===== BASE: entry 1 = every day (day level) =====")
OUT["BASE"] = OrderedDict()
for (x, W, m) in [(2, 5, "any"), (3, 10, "any"), (5, 20, "any"), (3, 10, "dg"), (5, 20, "dg")]:
    for hold in (20, 30):
        key = f"D{x}_W{W}_{m}_H{hold}"
        OUT["BASE"][key] = OrderedDict()
        for era, (a, b) in ERAS.items():
            res = [r for r in (run(i, x, W, m, hold, FIRE["SBX"]) for i in range(30, N) if a <= D[i] <= b) if r]
            o = agg(res); OUT["BASE"][key][era] = o
            print(f"  {key:16s} {era:9s} {fmt(o)}")

# Episode-level detail for the main variant
def show(proxy, key):
    print(f"\n{proxy} {key}: episodes where the tranche fired (date, entry1->T, tranche date, lag, tranche->T, further MAE, TR-ALL)")
    lst = []
    for r in detail[(proxy, key)]:
        if r["fired"]:
            print(f"  {r['date']} r0 {r['r0']:+6.2f} | {r['tr_date']} lag {r['lag']:2d} r_tr {r['r_tr']:+6.2f} "
                  f"further {r['further_mae']:+6.2f} | TR {r['TR']:+6.2f} ALL {r['ALL']:+6.2f} ONE {r['ONE']:+6.2f}")
            lst.append({k: (round(v, 2) if isinstance(v, float) else v) for k, v in r.items()})
    OUT.setdefault("detail", {})[f"{proxy}_{key}"] = lst

for proxy, key in [("SB", "D3_W10_any_H30"), ("SB", "D3_W10_dg_H30"), ("SBX", "D3_W10_any_H30"), ("SBX", "D5_W20_any_H30")]:
    show(proxy, key)

# ---------------- Live ----------------
spy = sorted((r["date"], float(r["spot_price"])) for r in csv.DictReader(open("gex_log.csv"))
             if r["ticker"] == "SPY" and r["spot_price"])
LD = [d for d, _ in spy]; LC = [c for _, c in spy]; LI = {d: i for i, d in enumerate(LD)}
sig = {r["date"]: r for r in csv.DictReader(open("regime_log.csv")) if r.get("regime_signal")}
sbl = [LI[d] for d in LD if d in sig and sig[d]["regime_signal"] == "STRONG_BUY"]
eps_l, last = [], None
for i in sbl:
    if last is None or i - last > 10:
        eps_l.append(i)
    last = i
print(f"\n===== LIVE STRONG_BUY episodes (gap >10 trading days), SPY closes {LD[0]}..{LD[-1]} =====")
OUT["live"] = []
for i0 in eps_l:
    T = min(i0 + 30, len(LC) - 1)
    rec = OrderedDict(date=LD[i0], entry=LC[i0], days_elapsed=T - i0, closed=(i0 + 30 < len(LC)),
                      r0_to_date=round(pct(LC[i0], LC[T]), 2),
                      mae_to_date=round(min([pct(LC[i0], c) for c in LC[i0 + 1:T + 1]] or [0.0]), 2))
    for x, W in ((2, 5), (3, 10), (5, 20)):
        j = next((k for k in range(i0 + 1, min(i0 + W, T) + 1) if pct(LC[i0], LC[k]) <= -x), None)
        if j is None:
            rec[f"D{x}_W{W}"] = None
        else:
            s = sig.get(LD[j], {}).get("regime_signal")
            rec[f"D{x}_W{W}"] = OrderedDict(date=LD[j], price=LC[j], signal_that_day=s,
                                            r_tr_to_date=round(pct(LC[j], LC[T]), 2),
                                            TR_to_date=round((pct(LC[i0], LC[T]) + pct(LC[j], LC[T])) / 2, 2),
                                            ALL_to_date=round(pct(LC[i0], LC[T]), 2))
    OUT["live"].append(rec)
    print(" ", json.dumps(rec))

json.dump(OUT, open("research/p3_second_tranche_results.json", "w"), indent=1, default=str)
