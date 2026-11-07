"""
P1 (IDEA_BACKLOG, signal accuracy): does gating STRONG_BUY on the composite
EXCLUDING vol_score beat the live composite>=1 gate?

Data: deep_history_backtest_log.csv (1995-10-17 .. 2026-08-21), produced by
deep_history_backtest.py with regime_analyzer's own score_* functions.
GEX has no history, so the setup is the non-GEX legs of STRONG_BUY:
RSI<50, SKEW>138, VIX>17 (RSI = deep_history_backtest.calc_rsi, simple 14d).

vol_score is NOT stored in the log. It is recovered exactly from the logged
composite: vol = (composite - 1.5*credit - flow - growth - skew)/1.2, using
regime_analyzer's own score functions for the other legs (score_flow ignores
tlt). Rows where the composite was clamped at +-8 or the residual is not an
integer fall back to score_volatility(vix, None, None) and are counted.

Run from repo root:  python3 research/p1_vol_gate.py
"""
import csv, json, math, os, sys, statistics as st
sys.path.insert(0, os.getcwd())
from regime_analyzer import (score_credit, score_volatility, score_flow,
                             score_growth, score_skew)

def f(x):
    try:
        return float(x) if x not in ("", None) else None
    except ValueError:
        return None

rows = list(csv.DictReader(open("deep_history_backtest_log.csv")))
closes = [float(r["spy_close"]) for r in rows]

# RSI: replicate deep_history_backtest.calc_rsi (simple avg, last 15 closes)
def calc_rsi(c, period=14):
    if len(c) < period + 1: return None
    g = [max(c[i]-c[i-1], 0) for i in range(1, len(c))]
    l = [max(c[i-1]-c[i], 0) for i in range(1, len(c))]
    ag, al = sum(g[-period:])/period, sum(l[-period:])/period
    if al == 0: return 100.0
    return 100 - 100/(1+ag/al)

fallback = 0
D = []
for i, r in enumerate(rows):
    vix, hyg, dxy, gold, copper, eem, skew = (f(r[k]) for k in
        ("vix", "hyg", "dxy", "gold", "copper", "eem", "skew"))
    comp = float(r["composite_score"])
    c = score_credit(hyg); fl = score_flow(dxy, gold, None)
    g = score_growth(copper, eem); s = score_skew(skew, vix)
    resid = (comp - 1.5*c - fl - g - s)/1.2
    if abs(comp) < 8 and abs(resid - round(resid)) < 0.09 and -3 <= round(resid) <= 3:
        v = int(round(resid))
    else:
        v = score_volatility(vix, None, None); fallback += 1
    exvol = 1.5*c + fl + g + s
    rsi = calc_rsi(closes[max(0, i-14):i+1]) if i >= 14 else None
    fwd, mae = {}, {}
    for h in (5, 10, 20):
        if i + h < len(closes):
            fwd[h] = (closes[i+h]/closes[i]-1)*100
            mae[h] = (min(closes[i+1:i+h+1])/closes[i]-1)*100
    D.append(dict(i=i, date=r["date"], vix=vix, skew=skew, hyg=hyg, comp=comp,
                  credit=c, vol=v, flow=fl, growth=g, skew_s=s, exvol=exvol,
                  rsi=rsi, fwd=fwd, mae=mae))

def legs(d, rsi_max=50):
    return (d["rsi"] is not None and d["rsi"] < rsi_max and d["skew"] is not None
            and d["skew"] > 138 and d["vix"] is not None and d["vix"] > 17)

ERAS = {"full": ("0000", "9999"), "pre_2010": ("0000", "2009-12-31"),
        "2010_2017": ("2010-01-01", "2017-12-31"), "2018+": ("2018-01-01", "9999")}

def stats(sel, h):
    xs = [d for d in sel if h in d["fwd"]]
    if not xs: return None
    r = [d["fwd"][h] for d in xs]; m = [d["mae"][h] for d in xs]
    return dict(n=len(xs), hit=round(100*sum(x > 0 for x in r)/len(r), 1),
                avg=round(st.mean(r), 2), med=round(st.median(r), 2),
                mae_avg=round(st.mean(m), 2), mae_p10=round(sorted(m)[int(0.1*len(m))], 2),
                mae_worst=round(min(m), 2), p_mae_le_m3=round(100*sum(x <= -3 for x in m)/len(m), 1))

def episodes(sel, gap=10):
    """first day of each cluster of fire days separated by > gap trading days"""
    out, last = [], -999
    for d in sel:
        if d["i"] - last > gap: out.append(d)
        last = d["i"]
    return out

def groups(era, rsi_max=50, thr=1):
    lo, hi = ERAS[era]
    E = [d for d in D if lo <= d["date"] <= hi]
    L = [d for d in E if legs(d, rsi_max)]
    return E, {
        "base_all_days": E,
        "legs_all": L,
        "A_current_gate_pass (comp>=1)": [d for d in L if d["comp"] >= thr],
        "B_blocked_only_by_vol (comp<1, exvol>=1)": [d for d in L if d["comp"] < thr and d["exvol"] >= thr],
        "C_blocked_by_nonvol (exvol<1)": [d for d in L if d["exvol"] < thr],
        "NEW_gate_pass (exvol>=1)": [d for d in L if d["exvol"] >= thr],
    }

out = {"rows": len(D), "date_range": [D[0]["date"], D[-1]["date"]],
       "vol_fallback_rows": fallback, "results": {}}
for rsi_max in (50, 40):
    for era in ERAS:
        E, G = groups(era, rsi_max)
        key = f"rsi<{rsi_max}|{era}"
        out["results"][key] = {}
        for name, sel in G.items():
            ep = episodes(sel) if name != "base_all_days" else None
            out["results"][key][name] = {
                "days": len(sel), "pct_of_days": round(100*len(sel)/max(1, len(E)), 2),
                "episodes": len(ep) if ep is not None else None,
                "day_level": {h: stats(sel, h) for h in (5, 10, 20)},
                "episode_level": {h: stats(ep, h) for h in (5, 10, 20)} if ep else None,
            }

# list B episodes (full, rsi<50) with outcomes — failure cases
E, G = groups("full")
out["B_episodes"] = [dict(date=d["date"], vix=d["vix"], hyg=d["hyg"], comp=d["comp"],
                          exvol=d["exvol"], vol=d["vol"], rsi=round(d["rsi"], 1),
                          fwd20=round(d["fwd"].get(20, float("nan")), 2),
                          mae20=round(d["mae"].get(20, float("nan")), 2))
                     for d in episodes(G["B_blocked_only_by_vol (comp<1, exvol>=1)"])]
json.dump(out, open("research/p1_vol_gate_results.json", "w"), indent=1)

def show(key, h=20):
    print(f"\n== {key}  h={h}d")
    print(f"{'group':44s} {'days':>5s} {'%d':>5s} {'ep':>4s} | day: {'hit':>5s} {'avg':>6s} {'mae':>6s} {'p10':>6s} {'<=-3%':>5s} | ep: {'hit':>5s} {'avg':>6s} {'mae':>6s} {'worst':>6s}")
    for name, v in out["results"][key].items():
        s = v["day_level"][h]; e = (v["episode_level"] or {}).get(h)
        if not s: print(f"{name:44s} {v['days']:5d}"); continue
        es = f"{e['hit']:5.1f} {e['avg']:6.2f} {e['mae_avg']:6.2f} {e['mae_worst']:6.2f}" if e else ""
        print(f"{name:44s} {v['days']:5d} {v['pct_of_days']:5.2f} {str(v['episodes'] or ''):>4s} | {s['hit']:5.1f} {s['avg']:6.2f} {s['mae_avg']:6.2f} {s['mae_p10']:6.2f} {s['p_mae_le_m3']:5.1f} | {es}")

if __name__ == "__main__":
    print("rows", out["rows"], out["date_range"], "vol fallback rows", fallback)
    for k in out["results"]:
        for h in (10, 20):
            show(k, h)
    print("\nB episodes (rsi<50, full):")
    for b in out["B_episodes"]: print(b)
