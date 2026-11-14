"""
P0b — QUICK ACTION tuning (quick_action.py).

Part A (live replay, gex_log/regime_log/flow_history, 2026-03-30+):
  re-run quick_action's decision for every SPY day using only data up to that
  day; count action flips; forward return / MAE by action; and test a 2-day
  persistence rule for entering/leaving DEFEND.

Part B (deep history, flow_history.csv 2007-04+ joined to
  deep_history_backtest_log.csv regime_signal through 2026-08-21):
  the DEFEND triggers that do not need GEX:
    T1 credit_breaking   HYG 5d <= -1.5%
    T2 backwardation 3+  VIX/VIX3M > 1 for >= 3 consecutive days
    T3 flow red          HYG/IEF 10d <= -1% AND defensive/cyclical 10d >= +3%
    T4 regime            deep regime_signal in DEFENSIVE/CRISIS
  For each trigger and the union: fire rate, fwd 5/10/20 return, hit rate,
  MAE, P(dip>=3% in 10d) vs base; by era. Then a "go to cash while DEFEND"
  overlay vs buy-and-hold: upside missed vs drawdown avoided, with
  persistence variants (enter after k consecutive DEFEND days, leave after
  k consecutive non-DEFEND days).

Run: python3 research/p0b_quick_action.py  (from repo root)
"""
import json
import numpy as np
import pandas as pd

OUT = {}
P = print


def fwd_stats(close, idx_mask, horizons=(5, 10, 20)):
    c = close.values
    n = len(c)
    res = {}
    idx = np.where(idx_mask)[0]
    for h in horizons:
        ii = idx[idx + h < n]
        if len(ii) == 0:
            res[h] = dict(n=0)
            continue
        fr = np.array([c[i + h] / c[i] - 1 for i in ii]) * 100
        mae = np.array([c[i + 1:i + h + 1].min() / c[i] - 1 for i in ii]) * 100
        res[h] = dict(n=int(len(ii)), hit=round(float((fr > 0).mean() * 100), 1),
                      fwd=round(float(fr.mean()), 2), med=round(float(np.median(fr)), 2),
                      mae=round(float(mae.mean()), 2),
                      p_dd3=round(float((mae <= -3).mean() * 100), 1),
                      p_dd5=round(float((mae <= -5).mean() * 100), 1))
    return res


def fmt(r, h):
    s = r[h]
    if s.get("n", 0) == 0:
        return "n=0"
    return (f"n={s['n']:5d} hit={s['hit']:5.1f}% fwd={s['fwd']:+6.2f} (med {s['med']:+6.2f}) "
            f"MAE={s['mae']:+6.2f} P(dd<=-3)={s['p_dd3']:5.1f}% P(dd<=-5)={s['p_dd5']:5.1f}%")


def episodes(mask, gap=10):
    idx = np.where(mask)[0]
    eps, last = [], -10 ** 9
    for i in idx:
        if i - last > gap:
            eps.append(i)
        last = i
    return eps


def persist(raw, k_on, k_off):
    """State machine: turn ON after k_on consecutive raw-ON days, OFF after k_off consecutive raw-OFF days."""
    out = np.zeros(len(raw), bool)
    on, run_on, run_off = False, 0, 0
    for i, r in enumerate(raw):
        if r:
            run_on += 1
            run_off = 0
        else:
            run_off += 1
            run_on = 0
        if not on and run_on >= k_on:
            on = True
        elif on and run_off >= k_off:
            on = False
        out[i] = on
    return out


def overlay(close, defend, label):
    """Hold SPY except when DEFEND state (decided at close t) -> cash for day t+1. No costs, no cash yield."""
    c = close.values
    r = np.diff(c) / c[:-1]
    expo = (~defend[:-1]).astype(float)
    strat = r * expo
    eq_bh, eq_s = np.cumprod(1 + r), np.cumprod(1 + strat)

    def mdd(eq):
        return float((eq / np.maximum.accumulate(eq) - 1).min() * 100)

    switches = int(np.abs(np.diff(defend.astype(int))).sum())
    missed_up = float(r[expo == 0][r[expo == 0] > 0].sum() * 100)
    avoided_dn = float(-r[expo == 0][r[expo == 0] < 0].sum() * 100)
    yrs = len(r) / 252
    d = dict(label=label, pct_time_out=round(float((expo == 0).mean() * 100), 1), switches=switches,
             switches_per_yr=round(switches / yrs, 1),
             tot_bh=round(float(eq_bh[-1] - 1) * 100, 1), tot_s=round(float(eq_s[-1] - 1) * 100, 1),
             cagr_bh=round(float(eq_bh[-1] ** (1 / yrs) - 1) * 100, 2),
             cagr_s=round(float(eq_s[-1] ** (1 / yrs) - 1) * 100, 2),
             mdd_bh=round(mdd(eq_bh), 1), mdd_s=round(mdd(eq_s), 1),
             sum_up_days_missed=round(missed_up, 1), sum_down_days_avoided=round(avoided_dn, 1),
             net_out_of_mkt=round(float(r[expo == 0].sum() * 100), 1))
    return d


# ------------------------------------------------------------------ Part A
P("=" * 100)
P("PART A — live replay of quick_action.py")
P("=" * 100)
gex = pd.read_csv("gex_log.csv")
gex = gex[gex.ticker.fillna("SPY").str.strip() == "SPY"].reset_index(drop=True)
reg = pd.read_csv("regime_log.csv").set_index("date")
flow = pd.read_csv("flow_history.csv")
flow = flow.set_index("date")


def fnum(v):
    try:
        v = float(v)
        return None if np.isnan(v) else v
    except (TypeError, ValueError):
        return None


rows = []
for i in range(5, len(gex)):
    g = gex.iloc[i]
    date = g.date
    sig = str(reg.loc[date, "regime_signal"]).upper() if date in reg.index else ""
    spy, vix, gexb, zg = fnum(g.spot_price), fnum(g.vix), fnum(g.net_gex_b), fnum(g.zero_gamma)
    h0, h5 = fnum(g.hyg), fnum(gex.iloc[i - 5].hyg)
    hyg5 = (h0 / h5 - 1) * 100 if h0 and h5 else None
    term = str(g.vix_term_structure).strip()
    backw = 0
    for j in range(i, -1, -1):
        if str(gex.iloc[j].vix_term_structure).strip() != "backwardation":
            break
        backw += 1
    gex2 = all((fnum(gex.iloc[j].net_gex_b) or -1) > 0 for j in (i - 1, i))
    checks = [term == "contango", vix is not None and vix < 22, gex2,
              spy is not None and zg is not None and spy > zg, hyg5 is not None and hyg5 >= 0]
    fl = flow[flow.index <= date]
    red = amber = False
    dc = cr = None
    if len(fl) >= 11:
        cur, old = fl.iloc[-1], fl.iloc[-11]
        ch = lambda k: (cur[k] / old[k] - 1) * 100
        cr, dc, smh, rsp = ch("hyg_ief"), ch("defensive_cyclical"), ch("smh_spy"), ch("rsp_spy")
        red = cr <= -1 and dc >= 3
    credit_breaking = hyg5 is not None and hyg5 <= -1.5
    buy = sig in ("STRONG_BUY", "BUY_WATCH")
    n_conf = sum(checks)
    why = []
    if sig in ("DEFENSIVE", "CRISIS"): why.append("regime")
    if credit_breaking: why.append("credit5d")
    if backw >= 3: why.append("backw3")
    if red: why.append("flowred")
    if why:
        a = "DEFEND"
    elif buy and n_conf >= 3 and (checks[2] or checks[3]):
        a = "ADD"
    elif buy:
        a = "WAIT"
    elif sig == "CAUTION":
        a = "TIGHTEN"
    else:
        a = "HOLD"
    rows.append(dict(date=date, spy=spy, signal=sig, action=a, why="+".join(why), hyg5=hyg5,
                     hyg_ief10=cr, dc10=dc, backw=backw, n_conf=n_conf))
L = pd.DataFrame(rows)
L.to_csv("research/p0b_live_replay.csv", index=False)
P(f"days {len(L)}  {L.date.iloc[0]} .. {L.date.iloc[-1]}")
P(L.action.value_counts().to_string())
P("DEFEND triggers:", L[L.action == "DEFEND"].why.value_counts().to_dict())
flips = int((L.action != L.action.shift()).sum() - 1)
P(f"action changes: {flips} over {len(L)} days")
P("\nDEFEND days:")
P(L[L.action == "DEFEND"][["date", "spy", "signal", "why", "hyg5", "hyg_ief10", "dc10", "backw"]].round(2).to_string(index=False))
close = L.spy.reset_index(drop=True)
OUT["live"] = {"counts": L.action.value_counts().to_dict(), "flips": flips}
P("\nForward stats by action (live, close-to-close on gex_log spot):")
for a in ["HOLD", "WAIT", "ADD", "DEFEND", "TIGHTEN"]:
    m = (L.action == a).values
    if m.sum() == 0:
        continue
    r = fwd_stats(close, m)
    OUT["live"][a] = r
    for h in (5, 10):
        P(f"  {a:7s} {h:2d}d  {fmt(r, h)}")
base = fwd_stats(close, np.ones(len(L), bool))
for h in (5, 10):
    P(f"  base    {h:2d}d  {fmt(base, h)}")
OUT["live"]["base"] = base

raw = (L.action == "DEFEND").values
P("\nPersistence variants on live DEFEND (state ON after k_on consecutive raw days, OFF after k_off):")
for kon, koff in [(1, 1), (2, 1), (1, 2), (2, 2), (1, 3)]:
    st = persist(raw, kon, koff)
    sw = int(np.abs(np.diff(st.astype(int))).sum())
    r = fwd_stats(close, st)
    on_dates = [L.date.iloc[i] for i in np.where(np.diff(np.r_[0, st.astype(int)]) == 1)[0]]
    P(f"  k_on={kon} k_off={koff}: days={st.sum():3d} switches={sw:2d} starts={on_dates}")
    P(f"     10d {fmt(r, 10)}")
    o = overlay(close, st, f"live k_on={kon} k_off={koff}")
    P(f"     overlay: out {o['pct_time_out']}% | tot B&H {o['tot_bh']}% vs {o['tot_s']}% | MDD {o['mdd_bh']} vs {o['mdd_s']}")
    OUT["live"][f"persist_{kon}_{koff}"] = dict(days=int(st.sum()), switches=sw, starts=on_dates, fwd=r, overlay=o)

# ------------------------------------------------------------------ Part B
P("\n" + "=" * 100)
P("PART B — deep history DEFEND triggers (flow_history 2007-04-11+; regime from deep log to 2026-08-21)")
P("=" * 100)
F = pd.read_csv("flow_history.csv")
F = F[F.date <= "2026-11-13"]
D = pd.read_csv("deep_history_backtest_log.csv")[["date", "regime_signal"]]
F = F.merge(D, on="date", how="left")
F = F[F.date >= "2007-04-11"].reset_index(drop=True)
F["hyg5"] = F.hyg.pct_change(5) * 100
F["hyg_ief10"] = F.hyg_ief.pct_change(10) * 100
F["dc10"] = F.defensive_cyclical.pct_change(10) * 100
bk = (F.vix_vix3m > 1).astype(int)
F["backw_run"] = bk.groupby((bk != bk.shift()).cumsum()).cumsum() * bk
F["T1"] = F.hyg5 <= -1.5
F["T2"] = F.backw_run >= 3
F["T3"] = (F.hyg_ief10 <= -1) & (F.dc10 >= 3)
F["T4"] = F.regime_signal.isin(["DEFENSIVE", "CRISIS"])
F["T4_known"] = F.regime_signal.notna()
F["ANY"] = F[["T1", "T2", "T3", "T4"]].any(axis=1)
F["ANY_noT4"] = F[["T1", "T2", "T3"]].any(axis=1)
c = F.spy.reset_index(drop=True)
P(f"rows {len(F)}  {F.date.iloc[0]} .. {F.date.iloc[-1]}; regime known through {F[F.T4_known].date.max()}")
eras = {"full": np.ones(len(F), bool),
        "2007-09": (F.date < "2010-01-01").values,
        "2010-17": ((F.date >= "2010-01-01") & (F.date < "2018-01-01")).values,
        "2018+": (F.date >= "2018-01-01").values}
OUT["deep"] = {}
for name, m in eras.items():
    P(f"\n--- era {name} ---")
    b = fwd_stats(c, m)
    P(f"  base     10d {fmt(b, 10)}")
    P(f"  base     20d {fmt(b, 20)}")
    OUT["deep"][f"{name}_base"] = b
    for t in ["T1", "T2", "T3", "T4", "ANY_noT4", "ANY"]:
        mm = m & F[t].values
        r = fwd_stats(c, mm)
        ne = len(episodes(mm))
        OUT["deep"][f"{name}_{t}"] = dict(days=int(mm.sum()), eps=ne, pct=round(mm.sum() / m.sum() * 100, 2), fwd=r)
        P(f"  {t:8s} days={mm.sum():4d} ({mm.sum() / m.sum() * 100:4.1f}%) eps={ne:3d}")
        P(f"           10d {fmt(r, 10)}")
        P(f"           20d {fmt(r, 20)}")

# episode list for T3 (the flow-red rule) since 2007
P("\nT3 'Leaving stocks' (flow red) episodes, gap>10d: first day, SPY, fwd10/fwd20, MAE20")
cv = c.values
for i in episodes(F.T3.values):
    f10 = (cv[i + 10] / cv[i] - 1) * 100 if i + 10 < len(cv) else np.nan
    f20 = (cv[i + 20] / cv[i] - 1) * 100 if i + 20 < len(cv) else np.nan
    m20 = (cv[i + 1:i + 21].min() / cv[i] - 1) * 100 if i + 1 < len(cv) else np.nan
    P(f"  {F.date[i]}  {cv[i]:8.2f}  {f10:+6.2f} {f20:+6.2f}  {m20:+6.2f}")

# overlays
P("\nCash-while-DEFEND overlay vs buy & hold (no costs, no cash yield). Period A: 2007-04-11..2026-11-13 using T1|T2|T3;")
P("Period B: same + T4 regime, 2007-04-11..2026-08-21 (regime known).")
OUT["overlay"] = []
for lab, mask, lim in [("T1|T2|T3", F.ANY_noT4.values, len(F)),
                       ("T1|T2|T3|T4", F.ANY.values, int(F.T4_known.values.nonzero()[0].max()) + 1),
                       ("T1 only", F.T1.values, len(F)), ("T2 only", F.T2.values, len(F)),
                       ("T3 only", F.T3.values, len(F))]:
    for kon, koff in [(1, 1), (2, 1), (1, 2), (2, 2), (1, 3)]:
        st = persist(mask[:lim], kon, koff)
        for era, lo, hi in [("all", "2007-04-11", "2099"), ("2018+", "2018-01-01", "2099"), ("2010-17", "2010-01-01", "2018-01-01")]:
            sel = ((F.date[:lim] >= lo) & (F.date[:lim] < hi)).values
            o = overlay(c[:lim][sel].reset_index(drop=True), st[sel], f"{lab} k_on={kon} k_off={koff} {era}")
            OUT["overlay"].append(o)
            P(f"  {o['label']:34s} out={o['pct_time_out']:5.1f}% sw/yr={o['switches_per_yr']:5.1f} "
              f"CAGR {o['cagr_bh']:+5.2f}->{o['cagr_s']:+5.2f}  MDD {o['mdd_bh']:6.1f}->{o['mdd_s']:6.1f}  "
              f"up-missed {o['sum_up_days_missed']:6.1f} dn-avoided {o['sum_down_days_avoided']:6.1f} net {o['net_out_of_mkt']:+6.1f}")

# 2-day whipsaw: how often does a raw DEFEND day stand alone?
for t in ["T1", "T2", "T3", "ANY_noT4"]:
    v = F[t].values
    runs = np.diff(np.r_[0, v.astype(int), 0])
    starts, ends = np.where(runs == 1)[0], np.where(runs == -1)[0]
    lens = ends - starts
    P(f"run lengths {t}: runs={len(lens)} 1-day={int((lens == 1).sum())} ({(lens == 1).mean() * 100:.0f}%) median={np.median(lens):.0f}")
    OUT[f"runs_{t}"] = dict(runs=int(len(lens)), one_day=int((lens == 1).sum()))

with open("research/p0b_quick_action_results.json", "w") as fh:
    json.dump(OUT, fh, indent=1, default=str)

# ------------------------------------------------------------------ Part C
P("\n" + "=" * 100)
P("PART C — 'no new adds while DEFEND': buy at DEFEND start vs wait until DEFEND clears")
P("=" * 100)
P("Episodes = starts of the persisted DEFEND state (T1|T2|T3). Early = close on the start day.")
P("Late = close on the day the state turns OFF. Common endpoint = OFF day + 20. MAE = worst close from entry to endpoint.")
OUT["wait"] = {}
for kon, koff in [(1, 1), (2, 1), (2, 2)]:
    st = persist(F.ANY_noT4.values, kon, koff)
    d = np.diff(np.r_[0, st.astype(int), 0])
    s_idx, e_idx = np.where(d == 1)[0], np.where(d == -1)[0]  # e = first OFF day
    for era, lo, hi in [("all", "2007", "2099"), ("2018+", "2018-01-01", "2099"), ("2010-17", "2010-01-01", "2018-01-01")]:
        rec = []
        for s, e in zip(s_idx, e_idx):
            end = e + 20
            if end >= len(cv) or not (lo <= F.date[s] < hi):
                continue
            early, late = cv[end] / cv[s] - 1, cv[end] / cv[e] - 1
            mae_e, mae_l = cv[s + 1:end + 1].min() / cv[s] - 1, cv[e + 1:end + 1].min() / cv[e] - 1
            rec.append((early, late, mae_e, mae_l, cv[e] / cv[s] - 1, e - s))
        a = np.array(rec) * np.array([100, 100, 100, 100, 100, 1])
        r = dict(n=len(a), early=round(a[:, 0].mean(), 2), late=round(a[:, 1].mean(), 2),
                 early_med=round(float(np.median(a[:, 0])), 2), late_med=round(float(np.median(a[:, 1])), 2),
                 mae_early=round(a[:, 2].mean(), 2), mae_late=round(a[:, 3].mean(), 2),
                 p5_early=round(float((a[:, 2] <= -5).mean() * 100), 1), p5_late=round(float((a[:, 3] <= -5).mean() * 100), 1),
                 entry_gap=round(a[:, 4].mean(), 2), entry_gap_med=round(float(np.median(a[:, 4])), 2),
                 late_better=round(float((a[:, 1] > a[:, 0]).mean() * 100), 1), days_med=float(np.median(a[:, 5])))
        OUT["wait"][f"{kon}_{koff}_{era}"] = r
        P(f"  k_on={kon} k_off={koff} {era:7s} eps={r['n']:3d} wait-days med {r['days_med']:.0f} | "
          f"end ret early {r['early']:+.2f} (med {r['early_med']:+.2f}) vs late {r['late']:+.2f} (med {r['late_med']:+.2f}) | "
          f"late entry vs early price {r['entry_gap']:+.2f} (med {r['entry_gap_med']:+.2f}) | "
          f"MAE early {r['mae_early']:+.2f} vs late {r['mae_late']:+.2f} | P(MAE<=-5) {r['p5_early']}% vs {r['p5_late']}% | late better {r['late_better']}%")

P("\nLive single-day DEFENDs that k_on=2 would drop (fwd from gex_log spot):")
for dt in ["2026-09-29", "2026-11-02"]:
    i = int(np.where(L.date.values == dt)[0][0])
    sp = close.values
    out = [f"{(sp[i + h] / sp[i] - 1) * 100:+.2f}" if i + h < len(sp) else "n/a" for h in (5, 10)]
    mae = (sp[i + 1:i + 11].min() / sp[i] - 1) * 100
    P(f"  {dt} SPY {sp[i]:.2f}: fwd5 {out[0]} fwd10 {out[1]} MAE10 {mae:+.2f}")

with open("research/p0b_quick_action_results.json", "w") as fh:
    json.dump(OUT, fh, indent=1, default=str)
