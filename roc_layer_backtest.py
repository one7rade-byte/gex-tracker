"""
roc_layer_backtest.py — offline re-test of the ROC early-warning layer
(composite_5d_chg, hyg_5d_pct) on deep_history_backtest_log.csv.
Reports firing rate, forward-drawdown hit rate vs base rate, by era, and
lead time vs the 2020 and 2025 SPY peaks. No network needed.
"""
import json
import pandas as pd

df = pd.read_csv("deep_history_backtest_log.csv", parse_dates=["date"]).set_index("date")
df = df[df.spy_close.notna()].copy()
df["composite_5d_chg"] = df.composite_score.diff(5)
df["hyg_5d_pct"] = df.hyg.pct_change(5) * 100
c = df.spy_close
# forward 20d max drawdown (worst close in next 20 days vs today)
fwd_min = pd.concat([c.shift(-k) for k in range(1, 21)], axis=1).min(axis=1)
df["fwd20_dd"] = (fwd_min / c - 1) * 100
df.loc[c.shift(-20).isna(), "fwd20_dd"] = float("nan")
df["fwd20_ret"] = (c.shift(-20) / c - 1) * 100
d = df[df.hyg.notna() & df.fwd20_dd.notna()].copy()  # HYG era, complete forward window

def stats(mask, label, sub):
    s = sub[mask]
    return {"rule": label, "n_fire": int(len(s)), "fire_rate_pct": round(100 * len(s) / len(sub), 2),
            "hit_dd5_pct": round(100 * (s.fwd20_dd <= -5).mean(), 1) if len(s) else None,
            "hit_dd10_pct": round(100 * (s.fwd20_dd <= -10).mean(), 1) if len(s) else None,
            "avg_fwd20_ret": round(s.fwd20_ret.mean(), 2) if len(s) else None}

base = {"n": len(d), "base_dd5_pct": round(100 * (d.fwd20_dd <= -5).mean(), 1),
        "base_dd10_pct": round(100 * (d.fwd20_dd <= -10).mean(), 1), "base_fwd20_ret": round(d.fwd20_ret.mean(), 2)}
eras = {"2007-2012": ("2007-04-01", "2012-12-31"), "2013-2019": ("2013-01-01", "2019-12-31"), "2020-2026": ("2020-01-01", "2026-12-31")}
rules = {
  "hyg_5d_pct<=-1.5": lambda x: x.hyg_5d_pct <= -1.5,
  "hyg_5d_pct<=-2.5": lambda x: x.hyg_5d_pct <= -2.5,
  "composite_5d_chg<=-3": lambda x: x.composite_5d_chg <= -3,
  "composite_5d_chg<=-5": lambda x: x.composite_5d_chg <= -5,
  "either(hyg<=-1.5, comp<=-3)": lambda x: (x.hyg_5d_pct <= -1.5) | (x.composite_5d_chg <= -3),
  "both(hyg<=-1.5, comp<=-3)": lambda x: (x.hyg_5d_pct <= -1.5) & (x.composite_5d_chg <= -3),
}
out = {"base_rates": base, "pooled": [], "by_era": {}}
for k, f in rules.items():
    out["pooled"].append(stats(f(d), k, d))
for e, (a, b) in eras.items():
    sub = d[a:b]
    out["by_era"][e] = {"base_dd5_pct": round(100 * (sub.fwd20_dd <= -5).mean(), 1), "n": len(sub),
                        "rules": [stats(f(sub), k, sub) for k, f in rules.items()]}
# risk-on turn: strong upward ROC after stress
up = {"composite_5d_chg>=+4": lambda x: x.composite_5d_chg >= 4, "hyg_5d_pct>=+2": lambda x: x.hyg_5d_pct >= 2}
out["risk_on_turn"] = [{**stats(f(d), k, d), "base_fwd20_ret": base["base_fwd20_ret"]} for k, f in up.items()]
# conditional on being in a drawdown >=10% from 252d high (bottom-turn test)
dd = (c / c.rolling(252, min_periods=60).max() - 1) * 100
d2 = d[dd.reindex(d.index) <= -10]
out["risk_on_turn_in_drawdown"] = {"n_days_in_dd10": len(d2), "base_fwd20_ret": round(d2.fwd20_ret.mean(), 2),
    "rules": [stats(f(d2), k, d2) for k, f in up.items()]}
# lead time vs peaks
ep = {"covid_2020": ("2020-01-15", "2020-04-30"), "selloff_2025": ("2025-01-15", "2025-04-30")}
out["episodes"] = {}
for name, (a, b) in ep.items():
    w = df[a:b]; pk = w.spy_close.idxmax(); tr = w.loc[pk:].spy_close.idxmin()
    r = {"peak": str(pk.date()), "peak_to_trough_pct": round((w.spy_close[tr] / w.spy_close[pk] - 1) * 100, 1), "trough": str(tr.date())}
    for k, f in rules.items():
        fired = w.loc[pk - pd.Timedelta(days=45):tr][f(w.loc[pk - pd.Timedelta(days=45):tr])]
        fired = fired[fired.index >= pk - pd.Timedelta(days=45)]
        r[k] = {"first_fire": str(fired.index[0].date()) if len(fired) else None,
                "cal_days_vs_peak": int((fired.index[0] - pk).days) if len(fired) else None}
    out["episodes"][name] = r
    # bottom turn
    for k, f in up.items():
        post = w.loc[tr - pd.Timedelta(days=3):]
        fr = post[f(post)]
        r["turn_" + k] = {"first_fire": str(fr.index[0].date()), "cal_days_vs_trough": int((fr.index[0] - tr).days)} if len(fr) else None
json.dump(out, open("roc_layer_backtest_summary.json", "w"), indent=1)
print(json.dumps(out, indent=1))
