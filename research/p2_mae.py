"""
P2 (IDEA_BACKLOG, signal accuracy): maximum adverse excursion (MAE) after
regime_signal calls. track_signal_performance.py reports hit rate / avg return
only; a 100% hit rate can hide a -3% dip first.

Part A — LIVE: every regime_log.csv signal day (2026-03-30 ..), SPY closes from
  gex_log.csv (the same price series track_signal_performance.py uses).
  MAE_h = worst close in days t+1..t+h vs entry close; MFE_h = best close.
  Also: days-to-trough, share of eventual winners that first went <= -2/-3%,
  and a "-3% close stop" check (would honoring it have turned winners into
  losers?). Partial (still-open) windows are reported separately for the
  Oct 16 – Nov 18 cluster.
Part B — DEEP proxy (no GEX before 2026): deep_history_backtest_log.csv, the
  non-GEX STRONG_BUY legs (composite>=1, RSI<50, SKEW>138, VIX>17) and a
  BUY_WATCH-like proxy (composite>=0, RSI<57, not STRONG_BUY-proxy), vs base,
  by era. Closes only (no intraday lows) in both parts: MAE is understated.

Run from repo root:  python3 research/p2_mae.py
"""
import csv, json, os, statistics as st, sys
from collections import defaultdict

H = (5, 10, 20)
OUT = {}

def pct(a, b):
    return (b / a - 1) * 100

def summarize(xs, h):
    xs = [x for x in xs if h in x["fwd"]]
    if not xs:
        return None
    r = [x["fwd"][h] for x in xs]; m = [x["mae"][h] for x in xs]; u = [x["mfe"][h] for x in xs]
    win = [x for x in xs if x["fwd"][h] > 0]
    return dict(
        n=len(xs), hit=round(100 * len(win) / len(xs), 1), avg=round(st.mean(r), 2),
        med=round(st.median(r), 2), mae_avg=round(st.mean(m), 2), mae_med=round(st.median(m), 2),
        mae_worst=round(min(m), 2), mfe_avg=round(st.mean(u), 2),
        p_mae_le_m1=round(100 * sum(v <= -1 for v in m) / len(m), 1),
        p_mae_le_m2=round(100 * sum(v <= -2 for v in m) / len(m), 1),
        p_mae_le_m3=round(100 * sum(v <= -3 for v in m) / len(m), 1),
        winners_dipped_m2=(round(100 * sum(x["mae"][h] <= -2 for x in win) / len(win), 1) if win else None),
        # -3% close stop: exit at the first close <= -3% (at that close's return)
        stop3_avg=round(st.mean(x["stop3"][h] for x in xs), 2),
        stop3_hit=round(100 * sum(x["stop3"][h] > 0 for x in xs) / len(xs), 1),
        stop3_winners_killed=sum(1 for x in win if x["mae"][h] <= -3),
    )

def build(dates, closes, i):
    fwd, mae, mfe, stop3, ttm = {}, {}, {}, {}, {}
    for h in H:
        if i + h < len(closes):
            path = [pct(closes[i], c) for c in closes[i + 1:i + h + 1]]
            fwd[h] = path[-1]; mae[h] = min(path); mfe[h] = max(path)
            ttm[h] = path.index(min(path)) + 1
            hit = next((p for p in path if p <= -3), None)
            stop3[h] = hit if hit is not None else path[-1]
    part = [pct(closes[i], c) for c in closes[i + 1:i + 21]]
    return dict(fwd=fwd, mae=mae, mfe=mfe, stop3=stop3, ttm=ttm,
                open_days=len(part), open_ret=(part[-1] if part else None),
                open_mae=(min(part) if part else None))

# ---------------- Part A: live ----------------
spy = sorted((r["date"], float(r["spot_price"])) for r in csv.DictReader(open("gex_log.csv"))
             if r["ticker"] == "SPY" and r["spot_price"])
ldates = [d for d, _ in spy]; lcl = [c for _, c in spy]; lidx = {d: i for i, d in enumerate(ldates)}
sig = {r["date"]: r for r in csv.DictReader(open("regime_log.csv")) if r.get("regime_signal")}
live = []
for d in ldates:
    i = lidx[d]
    x = build(ldates, lcl, i)
    x.update(date=d, close=lcl[i], sig=(sig[d]["regime_signal"] if d in sig else None),
             comp=(sig[d]["composite_score"] if d in sig else None))
    live.append(x)

print(f"LIVE: SPY closes {ldates[0]}..{ldates[-1]} ({len(ldates)} days); signals on {sum(1 for x in live if x['sig'])}")
OUT["live"] = {}
for lab in ["ALL_DAYS", "STRONG_BUY", "BUY_WATCH", "HOLD", "STRONG_HOLD"]:
    sel = live if lab == "ALL_DAYS" else [x for x in live if x["sig"] == lab]
    OUT["live"][lab] = {}
    for h in H:
        s = summarize(sel, h); OUT["live"][lab][h] = s
        if s:
            print(f"  {lab:11s} h={h:2d} n={s['n']:3d} hit {s['hit']:5.1f}% avg {s['avg']:+.2f} med {s['med']:+.2f} | "
                  f"MAE avg {s['mae_avg']:+.2f} med {s['mae_med']:+.2f} worst {s['mae_worst']:+.2f} | "
                  f"P(MAE<=-1/-2/-3) {s['p_mae_le_m1']}/{s['p_mae_le_m2']}/{s['p_mae_le_m3']}% | "
                  f"winners dipped<=-2: {s['winners_dipped_m2']}% | MFE {s['mfe_avg']:+.2f} | "
                  f"-3% stop: avg {s['stop3_avg']:+.2f} hit {s['stop3_hit']}% winners killed {s['stop3_winners_killed']}")

# days to trough for STRONG_BUY
sb = [x for x in live if x["sig"] == "STRONG_BUY"]
for h in H:
    t = [x["ttm"][h] for x in sb if h in x["ttm"]]
    if t:
        print(f"  STRONG_BUY days-to-trough h={h}: median {st.median(t)}, mean {st.mean(t):.1f} (n={len(t)})")

print("\nSTRONG_BUY / BUY_WATCH since 2026-10-01 (open windows shown to date):")
rows_recent = []
for x in live:
    if x["sig"] in ("STRONG_BUY", "BUY_WATCH") and x["date"] >= "2026-10-01":
        f = lambda h, k: (f"{x[k][h]:+.2f}" if h in x[k] else "  open")
        print(f"  {x['date']} {x['sig']:10s} comp {x['comp']:>4s} @ {x['close']:.2f} | "
              f"fwd5/10/20 {f(5,'fwd')}/{f(10,'fwd')}/{f(20,'fwd')} | MAE5/10/20 {f(5,'mae')}/{f(10,'mae')}/{f(20,'mae')} | "
              f"to-date ({x['open_days']}d) ret {x['open_ret'] if x['open_ret'] is None else round(x['open_ret'],2)} "
              f"MAE {x['open_mae'] if x['open_mae'] is None else round(x['open_mae'],2)}")
        rows_recent.append(dict(date=x["date"], sig=x["sig"], comp=x["comp"], close=x["close"],
                                **{f"fwd{h}": round(x["fwd"][h], 2) for h in H if h in x["fwd"]},
                                **{f"mae{h}": round(x["mae"][h], 2) for h in H if h in x["mae"]},
                                days_elapsed=x["open_days"],
                                ret_to_date=None if x["open_ret"] is None else round(x["open_ret"], 2),
                                mae_to_date=None if x["open_mae"] is None else round(x["open_mae"], 2)))
OUT["live_recent"] = rows_recent

# ---------------- Part B: deep proxy ----------------
sys.path.insert(0, os.getcwd())
rows = list(csv.DictReader(open("deep_history_backtest_log.csv")))
dd = [r["date"] for r in rows]; dc = [float(r["spy_close"]) for r in rows]

def calc_rsi(c, period=14):  # deep_history_backtest.calc_rsi replica (see p1_vol_gate.py)
    if len(c) < period + 1: return None
    g = [max(c[k] - c[k - 1], 0) for k in range(1, len(c))]
    l = [max(c[k - 1] - c[k], 0) for k in range(1, len(c))]
    ag, al = sum(g[-period:]) / period, sum(l[-period:]) / period
    return 100.0 if al == 0 else 100 - 100 / (1 + ag / al)

def fl(v):
    try: return float(v)
    except (TypeError, ValueError): return None

deep = []
for i, r in enumerate(rows):
    x = build(dd, dc, i)
    rsi = calc_rsi(dc[max(0, i - 14):i + 1]) if i >= 14 else None
    comp, vix, skew = fl(r["composite_score"]), fl(r["vix"]), fl(r["skew"])
    sbp = (comp is not None and comp >= 1 and rsi is not None and rsi < 50 and skew is not None
           and skew > 138 and vix is not None and vix > 17)
    bwp = (not sbp and comp is not None and comp >= 0 and rsi is not None and rsi < 57)
    x.update(date=r["date"], sbp=sbp, bwp=bwp, rsi=rsi, vix=vix)
    deep.append(x)

ERAS = {"full": ("0000", "9999"), "pre_2010": ("0000", "2009-12-31"),
        "2010_2017": ("2010-01-01", "2017-12-31"), "2018+": ("2018-01-01", "9999")}

def episodes(sel, gap=10):
    out, last = [], None
    pos = {x["date"]: k for k, x in enumerate(deep)}
    for x in sel:
        k = pos[x["date"]]
        if last is None or k - last > gap:
            out.append(x)
        last = k
    return out

print(f"\nDEEP: {dd[0]}..{dd[-1]} ({len(dd)} days). Proxy STRONG_BUY = comp>=1 & RSI<50 & SKEW>138 & VIX>17 (no GEX).")
OUT["deep"] = {}
for era, (a, b) in ERAS.items():
    E = [x for x in deep if a <= x["date"] <= b]
    OUT["deep"][era] = {}
    for lab, sel in [("base", E), ("SB_proxy_days", [x for x in E if x["sbp"]]),
                     ("SB_proxy_episodes", episodes([x for x in E if x["sbp"]])),
                     ("BW_proxy_days", [x for x in E if x["bwp"]])]:
        OUT["deep"][era][lab] = {}
        for h in (10, 20):
            s = summarize(sel, h); OUT["deep"][era][lab][h] = s
            if s:
                print(f"  {era:9s} {lab:18s} h={h:2d} n={s['n']:4d} ({100*s['n']/max(1,len([y for y in E if h in y['fwd']])):.1f}% of days) "
                      f"hit {s['hit']:5.1f}% avg {s['avg']:+.2f} | MAE avg {s['mae_avg']:+.2f} worst {s['mae_worst']:+.2f} | "
                      f"P(MAE<=-2/-3) {s['p_mae_le_m2']}/{s['p_mae_le_m3']}% | winners dipped<=-2 {s['winners_dipped_m2']}% | "
                      f"-3% stop avg {s['stop3_avg']:+.2f} (hit {s['stop3_hit']}%, winners killed {s['stop3_winners_killed']})")

# MAE as a predictor: among SB-proxy days 2010+, does an early -2% MAE5 forecast a bad 20d?
sbx = [x for x in deep if x["sbp"] and x["date"] >= "2010-01-01" and 20 in x["fwd"]]
grp = defaultdict(list)
for x in sbx:
    grp["MAE5<=-2" if x["mae"][5] <= -2 else "MAE5>-2"].append(x["fwd"][20])
print("\n  SB proxy 2010+: fwd20 split by first-5d MAE")
OUT["deep_mae5_split"] = {}
for k, v in grp.items():
    print(f"    {k:9s} n={len(v)} hit20 {100*sum(r>0 for r in v)/len(v):.1f}% avg20 {st.mean(v):+.2f}")
    OUT["deep_mae5_split"][k] = dict(n=len(v), hit20=round(100 * sum(r > 0 for r in v) / len(v), 1), avg20=round(st.mean(v), 2))

# worst SB proxy episodes by MAE20
eps = sorted([x for x in episodes([x for x in deep if x["sbp"]]) if 20 in x["mae"]], key=lambda x: x["mae"][20])[:8]
print("  Worst SB-proxy episodes by MAE20 (date, fwd20, MAE20, MFE20):")
OUT["deep_worst_sb_episodes"] = []
for x in eps:
    print(f"    {x['date']} {x['fwd'][20]:+.2f} {x['mae'][20]:+.2f} {x['mfe'][20]:+.2f}")
    OUT["deep_worst_sb_episodes"].append(dict(date=x["date"], fwd20=round(x["fwd"][20], 2),
                                              mae20=round(x["mae"][20], 2), mfe20=round(x["mfe"][20], 2)))

json.dump(OUT, open("research/p2_mae_results.json", "w"), indent=1, default=str)

# ---------------- Part C: the -2%-within-5d breach, as a decision point ----------------
# At the first close <= entry-2% within days 1..5 after a SB-proxy day, what does holding from
# that breach close to entry+20 return? (This is the information actually available at the time.)
print("\nPart C: SB proxy days whose close breached -2% within 5d; return from breach close to entry+20")
OUT["breach"] = {}
pos = {x["date"]: k for k, x in enumerate(deep)}
def breach_stats(sel, label):
    res = []
    for x in sel:
        k = pos[x["date"]]
        if k + 20 >= len(dc): continue
        b = next((j for j in range(k + 1, k + 6) if pct(dc[k], dc[j]) <= -2), None)
        if b is None: continue
        hold = pct(dc[b], dc[k + 20]); further = min(pct(dc[b], c) for c in dc[b + 1:k + 21]) if b < k + 20 else 0.0
        res.append(dict(date=x["date"], lag=b - k, entry_to_end=pct(dc[k], dc[k + 20]), breach_to_end=hold, further_mae=further))
    if not res:
        print(f"  {label}: none"); return
    ep = episodes([deep[pos[r['date']]] for r in res])
    s = dict(n_days=len(res), n_episodes=len(ep),
             hit_from_breach=round(100 * sum(r["breach_to_end"] > 0 for r in res) / len(res), 1),
             avg_from_breach=round(st.mean(r["breach_to_end"] for r in res), 2),
             med_from_breach=round(st.median(r["breach_to_end"] for r in res), 2),
             avg_further_mae=round(st.mean(r["further_mae"] for r in res), 2),
             p_further_le_m3=round(100 * sum(r["further_mae"] <= -3 for r in res) / len(res), 1),
             avg_entry_to_end=round(st.mean(r["entry_to_end"] for r in res), 2))
    OUT["breach"][label] = s
    print(f"  {label}: {s}")
    return res
for era, (a, b) in [("2010+", ("2010-01-01", "9999")), ("2018+", ("2018-01-01", "9999")), ("full", ("0000", "9999"))]:
    breach_stats([x for x in deep if x["sbp"] and a <= x["date"] <= b], f"SB_proxy {era}")
# base comparison: any day whose close breached -2% within 5d
for era, (a, b) in [("2010+", ("2010-01-01", "9999")), ("2018+", ("2018-01-01", "9999"))]:
    breach_stats([x for x in deep if a <= x["date"] <= b], f"ALL days {era}")

# first fire vs re-fire (SB proxy, 2018+)
print("\nFirst fire vs re-fire (SB proxy, cluster gap >10 trading days)")
for era, (a, b) in [("2010+", ("2010-01-01", "9999")), ("2018+", ("2018-01-01", "9999"))]:
    S = [x for x in deep if x["sbp"] and a <= x["date"] <= b]
    first = {x["date"] for x in episodes(S)}
    for lab, sel in [("first", [x for x in S if x["date"] in first]), ("refire", [x for x in S if x["date"] not in first])]:
        s = summarize(sel, 20); OUT.setdefault("first_vs_refire", {})[f"{era}_{lab}"] = s
        print(f"  {era} {lab:6s} n={s['n']} hit20 {s['hit']}% avg {s['avg']:+.2f} MAE20 {s['mae_avg']:+.2f} P(MAE<=-3) {s['p_mae_le_m3']}%")

# live breach check
print("\nLive STRONG_BUY breach check (close <= entry-2% within 5d):")
for x in live:
    if x["sig"] != "STRONG_BUY": continue
    i = lidx[x["date"]]
    b = next((j for j in range(i + 1, min(i + 6, len(lcl))) if pct(lcl[i], lcl[j]) <= -2), None)
    end = min(i + 20, len(lcl) - 1)
    print(f"  {x['date']} @ {lcl[i]:.2f}: breach {'none' if b is None else ldates[b]+f' ({lcl[b]:.2f})'}; "
          f"entry->{ldates[end]} {pct(lcl[i], lcl[end]):+.2f}" + ("" if b is None else f"; breach->{ldates[end]} {pct(lcl[b], lcl[end]):+.2f}")
          + ("" if i + 20 < len(lcl) else " [open]"))
json.dump(OUT, open("research/p2_mae_results.json", "w"), indent=1, default=str)
