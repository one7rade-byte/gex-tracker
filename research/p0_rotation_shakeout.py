"""
P0 (IDEA_BACKLOG, signal accuracy): validate the "rotation shakeout" flag.

Rule R (from the 2026-11-05 first read):
    SMH/SPY 10d % change <= -6  AND  RSP/SPY 10d % change >= +2.5
i.e. money leaving semis/megacap tech while the equal-weight index outperforms.

Questions:
 1. Day- and episode-level: base rate, fire rate, P(>=3% dip within 10d),
    fwd 5/10/20 return + hit rate, MAE 10/20. By era.
 2. Threshold sensitivity (is the 6-episode result a cherry-picked corner?).
 3. Does credit (HYG/IEF 10d) or defensive/cyclical separate the bad cases?
 4. As a "heads-up, then wait for confirmation" rule: compare entering at the
    flag vs waiting for a confirmation (cost of waiting vs drawdown avoided).

Data: flow_history.csv (repo root). Rows dated on/after the run date are
dropped (intraday partial bar). Episode = first fire day of a cluster whose
fires are separated by > 10 trading days.

Run from repo root:  python3 research/p0_rotation_shakeout.py
"""
import sys, json
import numpy as np
import pandas as pd

RUN_DATE = sys.argv[1] if len(sys.argv) > 1 else "2026-11-11"
d = pd.read_csv("flow_history.csv", parse_dates=["date"])
d = d[d.date < RUN_DATE].reset_index(drop=True)
spy = d.spy.values
n = len(d)

def pct(s, k):
    return (s / s.shift(k) - 1) * 100

d["smh10"] = pct(d.smh_spy, 10)
d["rsp10"] = pct(d.rsp_spy, 10)
d["hygief10"] = pct(d.hyg_ief, 10)
d["defcyc10"] = pct(d.defensive_cyclical, 10)
d["spy10"] = pct(d.spy, 10)
d["dd_high"] = (d.spy / d.spy.rolling(60, min_periods=1).max() - 1) * 100

for h in (5, 10, 20):
    d[f"fwd{h}"] = (d.spy.shift(-h) / d.spy - 1) * 100
    mins = [np.nan] * n
    for i in range(n - h):
        mins[i] = (spy[i + 1:i + h + 1].min() / spy[i] - 1) * 100
    d[f"mae{h}"] = mins
d["dip3_10"] = d.mae10 <= -3

def era(dt):
    y = dt.year
    return "2003-09" if y < 2010 else ("2010-17" if y < 2018 else "2018+")
d["era"] = d.date.apply(era)

valid = d.smh10.notna() & d.rsp10.notna()   # both legs exist: 2003-05+
U = d[valid & d.fwd20.notna()]

def episodes(mask, gap=10):
    idx = list(d.index[mask])
    out, last = [], -10**9
    for i in idx:
        if i - last > gap:
            out.append(i)
        last = i
    return out

def stats(rows):
    r = rows.dropna(subset=["fwd20"])
    if len(r) == 0:
        return dict(n=0)
    return dict(
        n=int(len(r)),
        dip3_10=round(100 * r.dip3_10.mean(), 1),
        hit10=round(100 * (r.fwd10 > 0).mean(), 1), fwd10=round(r.fwd10.mean(), 2),
        hit20=round(100 * (r.fwd20 > 0).mean(), 1), fwd20=round(r.fwd20.mean(), 2),
        med20=round(r.fwd20.median(), 2),
        mae10=round(r.mae10.mean(), 2), mae20=round(r.mae20.mean(), 2),
        p_mae20_le5=round(100 * (r.mae20 <= -5).mean(), 1),
    )

def fmt(tag, s):
    if s.get("n", 0) == 0:
        return f"{tag:38s} n=0"
    return (f"{tag:38s} n={s['n']:5d} dip3%10d={s['dip3_10']:5.1f}% "
            f"hit10={s['hit10']:5.1f}% fwd10={s['fwd10']:+6.2f} "
            f"hit20={s['hit20']:5.1f}% fwd20={s['fwd20']:+6.2f} (med {s['med20']:+.2f}) "
            f"MAE10={s['mae10']:+6.2f} MAE20={s['mae20']:+6.2f} P(MAE20<=-5)={s['p_mae20_le5']:4.1f}%")

res = {}
print(f"flow_history rows used: {len(d)} ({d.date.iloc[0].date()} .. {d.date.iloc[-1].date()}); "
      f"both legs valid from {d.date[valid].iloc[0].date()}\n")

# ---------- 1. Rule R ----------
R = valid & (d.smh10 <= -6) & (d.rsp10 >= 2.5)
print("=== 1. Rule R: SMH/SPY10d<=-6 & RSP/SPY10d>=+2.5 ===")
for e in ["all", "2003-09", "2010-17", "2018+"]:
    m = (U.index if e == "all" else U.index[U.era == e])
    base = stats(U.loc[m])
    fire = stats(d.loc[[i for i in d.index[R] if i in set(m)]])
    print(fmt(f"[{e}] base", base))
    print(fmt(f"[{e}] R day-level", fire))
    res[f"R_{e}"] = dict(base=base, fire=fire)
eps = episodes(R)
print(f"\nR fire days: {int(R.sum())} ({100*R.sum()/valid.sum():.2f}% of valid days); episodes: {len(eps)}")
print(fmt("R episode-level (first day)", stats(d.loc[eps])))
print("\nEpisodes: date, SPY, smh10, rsp10, hygief10, defcyc10, dd60, fwd5/10/20, MAE10/MAE20")
ep_rows = []
for i in eps:
    r = d.loc[i]
    line = (f"  {r.date.date()} {r.spy:8.2f} smh10={r.smh10:+6.2f} rsp10={r.rsp10:+5.2f} "
            f"hygief10={r.hygief10:+5.2f} defcyc10={r.defcyc10:+5.2f} dd60={r.dd_high:+6.2f} "
            f"fwd={r.fwd5:+6.2f}/{r.fwd10:+6.2f}/{r.fwd20:+6.2f} MAE={r.mae10:+6.2f}/{r.mae20:+6.2f}")
    print(line)
    ep_rows.append({k: (None if pd.isna(r[k]) else (str(r[k].date()) if k == "date" else round(float(r[k]), 2)))
                    for k in ["date", "spy", "smh10", "rsp10", "hygief10", "defcyc10", "dd_high",
                              "fwd5", "fwd10", "fwd20", "mae10", "mae20"]})
res["R_episodes"] = ep_rows

# ---------- 2. Sensitivity ----------
print("\n=== 2. Threshold sensitivity (episode-level, gap 10d) ===")
print("smh_thr rsp_thr  days  eps  dip3%10d  hit20  fwd20  med20  MAE20  | base: "
      f"dip3={100*U.dip3_10.mean():.1f}% hit20={100*(U.fwd20>0).mean():.1f}% fwd20={U.fwd20.mean():+.2f}")
sens = []
for st_ in (-4, -5, -6, -7):
    for rt in (None, 1.5, 2.5, 3.5):
        m = valid & (d.smh10 <= st_) & (True if rt is None else (d.rsp10 >= rt))
        e = episodes(m)
        s = stats(d.loc[e])
        sd = stats(d[m])
        if s.get("n", 0) == 0:
            continue
        print(f"{st_:6} {str(rt):>7} {int(m.sum()):5d} {s['n']:4d}   {s['dip3_10']:5.1f}%  {s['hit20']:5.1f}% "
              f"{s['fwd20']:+6.2f} {s['med20']:+6.2f} {s['mae20']:+6.2f}  | day: dip3={sd['dip3_10']}% hit20={sd['hit20']}% fwd20={sd['fwd20']:+.2f}")
        sens.append(dict(smh=st_, rsp=rt, days=int(m.sum()), ep=s, day=sd))
# SMH weakness alone 2018+
res["sensitivity"] = sens

# ---------- 3. Separators ----------
print("\n=== 3. Separators within the broader family (SMH/SPY10d<=-5 & RSP/SPY10d>=+1.5), episode-level ===")
F = valid & (d.smh10 <= -5) & (d.rsp10 >= 1.5)
fe = episodes(F)
FE = d.loc[fe].dropna(subset=["fwd20"])
for name, cond in [("HYG/IEF10d <= -1 (credit selling)", FE.hygief10 <= -1),
                   ("HYG/IEF10d >  -1", FE.hygief10 > -1),
                   ("HYG/IEF missing (pre-2007-04)", FE.hygief10.isna()),
                   ("def/cyc10d >= +3", FE.defcyc10 >= 3),
                   ("def/cyc10d <  +3", FE.defcyc10 < 3),
                   ("SPY already -5% off 60d high", FE.dd_high <= -5),
                   ("SPY within 5% of 60d high", FE.dd_high > -5),
                   ("SPY 10d <= -3%", FE.spy10 <= -3),
                   ("SPY 10d > -3%", FE.spy10 > -3)]:
    print(fmt(name, stats(FE[cond])))
print("\nFamily episodes (worst first by MAE20):")
for _, r in FE.sort_values("mae20").iterrows():
    print(f"  {r.date.date()} smh10={r.smh10:+6.2f} rsp10={r.rsp10:+5.2f} hygief10={r.hygief10:+5.2f} "
          f"defcyc10={r.defcyc10:+5.2f} dd60={r.dd_high:+6.2f} fwd20={r.fwd20:+6.2f} MAE20={r.mae20:+6.2f}")
res["family_n_episodes"] = len(FE)

# ---------- 4. Heads-up then confirmation ----------
print("\n=== 4. Heads-up, then wait for confirmation (family episodes) ===")
# Confirmation definitions (decided before looking at results):
#  C1 'semis back': first day after flag where SMH/SPY 5d change > 0 (whales return to semis)
#  C2 'trend back': first day SPY closes above its 10-day SMA
#  C3 'dip then turn': first day after SPY has been >=2% below flag close that SPY closes up
#     >=1% on the day (buy the shakeout, not the start of it); else none
d["sma10"] = d.spy.rolling(10).mean()
d["smh5"] = pct(d.smh_spy, 5)
WIN, END = 20, 30
rows4 = []
for i in fe:
    if i + END >= n:
        continue
    p0 = spy[i]
    out = dict(date=str(d.date[i].date()), early_end=(spy[i + END] / p0 - 1) * 100,
               early_mae=(spy[i + 1:i + END + 1].min() / p0 - 1) * 100)
    for cname in ("C1", "C2", "C3"):
        j = None
        for k in range(i + 1, i + WIN + 1):
            if cname == "C1" and d.smh5[k] > 0: j = k; break
            if cname == "C2" and spy[k] > d.sma10[k]: j = k; break
            if cname == "C3" and spy[i + 1:k + 1].min() <= p0 * 0.98 and spy[k] / spy[k - 1] - 1 >= 0.01: j = k; break
        if j is None:
            out[cname] = None
            continue
        out[cname] = dict(lag=j - i, entry_vs_flag=(spy[j] / p0 - 1) * 100,
                          to_end=(spy[i + END] / spy[j] - 1) * 100,
                          mae_after=(spy[j + 1:i + END + 1].min() / spy[j] - 1) * 100 if j < i + END else 0.0)
    rows4.append(out)
print(f"episodes with {END}d of future data: {len(rows4)}; window to confirm: {WIN}d; common endpoint: flag+{END}d")
print(f"EARLY (enter flag close): to_end avg {np.mean([r['early_end'] for r in rows4]):+.2f} "
      f"med {np.median([r['early_end'] for r in rows4]):+.2f}, MAE avg {np.mean([r['early_mae'] for r in rows4]):+.2f}, "
      f"P(MAE<=-5) {100*np.mean([r['early_mae']<=-5 for r in rows4]):.1f}%")
summ4 = {}
for c in ("C1", "C2", "C3"):
    rr = [r for r in rows4 if r[c]]
    if not rr:
        print(c, "never confirmed"); continue
    early_same = [r["early_end"] for r in rr]
    early_mae_same = [r["early_mae"] for r in rr]
    s = dict(confirmed=len(rr), of=len(rows4),
             lag_med=float(np.median([r[c]["lag"] for r in rr])),
             entry_vs_flag=round(float(np.mean([r[c]["entry_vs_flag"] for r in rr])), 2),
             late_to_end=round(float(np.mean([r[c]["to_end"] for r in rr])), 2),
             early_to_end_same=round(float(np.mean(early_same)), 2),
             late_mae=round(float(np.mean([r[c]["mae_after"] for r in rr])), 2),
             early_mae_same=round(float(np.mean(early_mae_same)), 2),
             late_p_mae5=round(100 * float(np.mean([r[c]["mae_after"] <= -5 for r in rr])), 1),
             early_p_mae5_same=round(100 * float(np.mean([m <= -5 for m in early_mae_same])), 1))
    summ4[c] = s
    print(f"{c}: confirmed {s['confirmed']}/{s['of']}, median lag {s['lag_med']}d, entry vs flag {s['entry_vs_flag']:+.2f}% | "
          f"to end: late {s['late_to_end']:+.2f} vs early {s['early_to_end_same']:+.2f} | "
          f"MAE: late {s['late_mae']:+.2f} vs early {s['early_mae_same']:+.2f} | "
          f"P(MAE<=-5): late {s['late_p_mae5']}% vs early {s['early_p_mae5_same']}%")
res["confirmation"] = summ4
res["confirmation_rows"] = rows4

# ---------- live ----------
print("\n=== Live: last 30 rows ===")
for _, r in d.tail(30).iterrows():
    flag = "R" if (r.smh10 <= -6 and r.rsp10 >= 2.5) else ("F" if (r.smh10 <= -5 and r.rsp10 >= 1.5) else " ")
    print(f"  {r.date.date()} {flag} spy={r.spy:8.2f} smh10={r.smh10:+6.2f} rsp10={r.rsp10:+5.2f} "
          f"hygief10={r.hygief10:+5.2f} defcyc10={r.defcyc10:+5.2f} smh5={r.smh5:+5.2f} sma10={r.sma10:7.2f}")

json.dump(res, open("research/p0_rotation_shakeout_results.json", "w"), indent=1, default=str)

# ---------- 5. Credit-split robustness (added after section 3) ----------
print("\n=== 5. Credit split robustness: family (-5/+1.5) DAY-level, and credit alone ===")
H = d.hyg_ief.notna() & d.fwd20.notna() & valid
for thr in (-0.5, -1.0, -1.5):
    a = d[F & H & (d.hygief10 <= thr)]; b = d[F & H & (d.hygief10 > thr)]
    print(fmt(f"family & hygief10<={thr} (days)", stats(a)))
    print(fmt(f"family & hygief10> {thr} (days)", stats(b)))
    print(fmt(f"ANY day hygief10<={thr} (2007+)", stats(d[H & (d.hygief10 <= thr)])))
print(fmt("base 2007-04+", stats(d[H])))
