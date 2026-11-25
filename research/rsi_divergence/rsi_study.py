"""
rsi_study.py — tests the "RSI bear divergence → oversold" pattern from the
StockCharts SPX chart Simon shared (2026-11-24), on SPY (1995+) and QQQ (1999+).

1. CRASH WARNING: RSI bear divergence at a high.
   Day t qualifies when the close is a 60-day high and within 2% of the
   252-day high, RSI(14) at t is below 70, and in the prior 15-120 sessions
   there was an earlier 60-day-high close at or below today's close whose
   RSI was 70+, with today's RSI at least 5 points lower. First signal per
   40 sessions. Compared with all other days at similar highs (the baseline).
   Outcome: worst close in the next 60 / 120 sessions vs the signal close.
   Also: of the drops that reached -10% / -20% from an all-time high, how
   many had a divergence signal in the 120 sessions before the peak (catch
   rate), and how early.

2. BOTTOM / LOADING: the first RSI < 30 after 60+ sessions without one.
   Outcomes: forward 20/60/120/250-session returns, whether the price
   undercut that close within 60 sessions (a "retest") and by how much, and
   how far the final low was. Split by whether a bear divergence came first
   (the chart's sequence), and by whether VIX was above 30.

Writes research/rsi_divergence/rsi_study.json and prints the tables.
"""
import csv, json, os, statistics as st

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))


def load():
    spy, vix = {}, {}
    with open(os.path.join(ROOT, "deep_history_backtest_log.csv")) as fh:
        for r in csv.DictReader(fh):
            if r.get("spy_close"): spy[r["date"]] = float(r["spy_close"])
            if r.get("vix"): vix[r["date"]] = float(r["vix"])
    qqq = {}
    with open(os.path.join(ROOT, "flow_history.csv")) as fh:
        for r in csv.DictReader(fh):
            if r.get("spy"): spy[r["date"]] = float(r["spy"])
            if r.get("qqq"): qqq[r["date"]] = float(r["qqq"])
            if r.get("vix"): vix[r["date"]] = float(r["vix"])
    return spy, qqq, vix


def rsi(c, n=14):
    out = [None] * len(c)
    g = l = 0.0
    for i in range(1, n + 1):
        d = c[i] - c[i - 1]; g += max(d, 0); l += max(-d, 0)
    g /= n; l /= n
    out[n] = 100 - 100 / (1 + g / l) if l else 100
    for i in range(n + 1, len(c)):
        d = c[i] - c[i - 1]
        g = (g * (n - 1) + max(d, 0)) / n
        l = (l * (n - 1) + max(-d, 0)) / n
        out[i] = 100 - 100 / (1 + g / l) if l else 100
    return out


def worst(c, i, h):
    w = c[i + 1:i + 1 + h]
    return (min(w) / c[i] - 1) * 100 if len(w) == h else None


def fwd(c, i, h):
    return (c[i + h] / c[i] - 1) * 100 if i + h < len(c) else None


def pct(xs, cond):
    xs = [x for x in xs if x is not None]
    return round(100 * sum(1 for x in xs if cond(x)) / len(xs), 1) if xs else None


def med(xs):
    xs = [x for x in xs if x is not None]
    return round(st.median(xs), 2) if xs else None


def study(name, px, vix):
    D = sorted(px); C = [px[d] for d in D]; R = rsi(C)
    n = len(C)
    hi60 = [max(C[max(0, i - 59):i + 1]) for i in range(n)]
    hi252 = [max(C[max(0, i - 251):i + 1]) for i in range(n)]
    at_high = [i for i in range(260, n) if C[i] >= hi60[i] and C[i] >= 0.98 * hi252[i] and R[i] is not None]

    # 1. Divergence signals
    div, last = [], -999
    for i in at_high:
        if i - last < 40 or R[i] >= 70:
            continue
        prior = [s for s in at_high if i - 120 <= s <= i - 15 and R[s] >= 70 and C[s] <= C[i] and R[i] <= R[s] - 5]
        if prior:
            div.append(i); last = i
    divset = set(div)
    base = [i for i in at_high if i not in divset]
    res = {"name": name, "from": D[0], "to": D[-1]}
    for lab, idx in (("divergence", div), ("baseline_at_highs", base)):
        w60 = [worst(C, i, 60) for i in idx]; w120 = [worst(C, i, 120) for i in idx]
        res[lab] = {"n": len(idx), "dip5_in_60d_pct": pct(w60, lambda x: x <= -5), "dip10_in_60d_pct": pct(w60, lambda x: x <= -10),
                    "dip10_in_120d_pct": pct(w120, lambda x: x <= -10), "dip20_in_120d_pct": pct(w120, lambda x: x <= -20),
                    "median_worst_60d": med(w60), "median_fwd_60d": med([fwd(C, i, 60) for i in idx]),
                    "median_fwd_120d": med([fwd(C, i, 120) for i in idx])}
    res["divergence_dates"] = [D[i] for i in div]

    # Catch rate: drawdowns of 10%+ / 20%+ from an all-time high
    eps, ath, ath_i, cur = [], C[0], 0, None
    for i, c in enumerate(C):
        if c >= ath:
            if cur: eps.append(cur); cur = None
            ath, ath_i = c, i
            continue
        dd = (c / ath - 1) * 100
        if dd <= -10 and cur is None:
            cur = {"peak_i": ath_i, "bottom": dd}
        if cur and dd < cur["bottom"]:
            cur["bottom"] = dd
    if cur: eps.append(cur)
    catch = []
    for e in eps:
        if e["peak_i"] < 260: continue
        before = [i for i in div if e["peak_i"] - 120 <= i <= e["peak_i"] + 5]
        catch.append({"peak": D[e["peak_i"]], "bottom_pct": round(e["bottom"], 1),
                      "divergence_before_peak": D[before[-1]] if before else None,
                      "sessions_before_peak": (e["peak_i"] - before[-1]) if before else None})
    res["drawdowns_10pct"] = catch
    res["catch_rate_10pct"] = f"{sum(1 for x in catch if x['divergence_before_peak'])}/{len(catch)}"
    big = [x for x in catch if x["bottom_pct"] <= -20]
    res["catch_rate_20pct"] = f"{sum(1 for x in big if x['divergence_before_peak'])}/{len(big)}"

    # 2. First oversold
    os_, last_os = [], -999
    for i in range(260, n):
        if R[i] is not None and R[i] < 30:
            if i - last_os >= 60:
                os_.append(i)
            last_os = i
    rows = []
    for i in os_:
        w = C[i + 1:i + 61]
        under = min(w) < C[i] if w else None
        low_after = [C[k] for k in range(i, min(n, i + 252))]
        rows.append({"date": D[i], "rsi": round(R[i], 1), "vix": vix.get(D[i]),
                     "dd_from_252d_high": round((C[i] / hi252[i] - 1) * 100, 1),
                     "after_divergence": any(i - 120 <= j < i for j in div),
                     "undercut_60d": under, "further_drop_60d": round((min(w) / C[i] - 1) * 100, 1) if w else None,
                     "final_low_12m": round((min(low_after) / C[i] - 1) * 100, 1),
                     "f20": fwd(C, i, 20), "f60": fwd(C, i, 60), "f120": fwd(C, i, 120), "f250": fwd(C, i, 250)})

    def summ(g):
        return {"n": len(g), "undercut_within_60d_pct": pct([r["undercut_60d"] for r in g], lambda x: x),
                "median_further_drop_60d": med([r["further_drop_60d"] for r in g]),
                "median_final_low_12m": med([r["final_low_12m"] for r in g]),
                "median_f20": med([r["f20"] for r in g]), "median_f60": med([r["f60"] for r in g]),
                "median_f120": med([r["f120"] for r in g]), "median_f250": med([r["f250"] for r in g]),
                "f250_positive_pct": pct([r["f250"] for r in g], lambda x: x > 0)}
    res["oversold_all"] = summ(rows)
    res["oversold_after_divergence"] = summ([r for r in rows if r["after_divergence"]])
    res["oversold_no_divergence"] = summ([r for r in rows if not r["after_divergence"]])
    res["oversold_vix_over_30"] = summ([r for r in rows if r["vix"] and r["vix"] > 30])
    res["oversold_vix_under_30"] = summ([r for r in rows if r["vix"] and r["vix"] <= 30])
    res["oversold_events"] = rows
    res["current"] = {"date": D[-1], "close": C[-1], "rsi": round(R[-1], 1),
                      "dd_from_ath": round((C[-1] / max(C) - 1) * 100, 1),
                      "last_divergence": D[div[-1]] if div else None,
                      "last_first_oversold": D[os_[-1]] if os_ else None,
                      "rsi_last_10": [round(x, 1) for x in R[-10:]]}
    return res


def show(r):
    print(f"\n==== {r['name']} {r['from']} → {r['to']} ====")
    for lab in ("divergence", "baseline_at_highs"):
        x = r[lab]
        print(f"{lab:18s} n={x['n']:4d} | -5% within 60d {x['dip5_in_60d_pct']}% | -10% in 60d {x['dip10_in_60d_pct']}% | -10% in 120d {x['dip10_in_120d_pct']}% "
              f"| -20% in 120d {x['dip20_in_120d_pct']}% | med worst 60d {x['median_worst_60d']} | med fwd 60d {x['median_fwd_60d']} 120d {x['median_fwd_120d']}")
    print("divergence dates:", r["divergence_dates"][-12:])
    print(f"catch rate: 10%+ drops {r['catch_rate_10pct']}, 20%+ drops {r['catch_rate_20pct']}")
    for x in r["drawdowns_10pct"]:
        print(f"   peak {x['peak']} bottom {x['bottom_pct']}% | divergence {x['divergence_before_peak']} ({x['sessions_before_peak']} sessions before peak)")
    for lab in ("oversold_all", "oversold_after_divergence", "oversold_no_divergence", "oversold_vix_over_30", "oversold_vix_under_30"):
        x = r[lab]
        print(f"{lab:26s} n={x['n']:3d} | undercut in 60d {x['undercut_within_60d_pct']}% (med {x['median_further_drop_60d']}%) | med 12m low {x['median_final_low_12m']}% "
              f"| fwd 20d {x['median_f20']} 60d {x['median_f60']} 120d {x['median_f120']} 250d {x['median_f250']} (+ {x['f250_positive_pct']}%)")
    print("current:", r["current"])


def main():
    spy, qqq, vix = load()
    out = {"spy": study("SPY", spy, vix), "qqq": study("QQQ", qqq, vix)}
    for k in out: show(out[k])
    with open(os.path.join(HERE, "rsi_study.json"), "w") as fh:
        json.dump(out, fh, indent=1)


if __name__ == "__main__":
    main()
