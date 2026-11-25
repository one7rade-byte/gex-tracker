"""
derisk_study.py — which warning patterns would have helped reduce risk
BEFORE a big drop, without costing too much in normal markets?

Window: 2007-04 → today (every series exists from then: HYG, VIX3M, SMH,
RSP, IWM). That window has 4 drops of 20%+ (2007-09, 2018, 2020, 2022) plus
2025's -19%.

Candidate warnings (each evaluated daily, using only data known that day):
  W1 semis_lead      SMH lags SPY by 10%+ over 60 sessions while SPY is within 5% of its high
  W2 narrow_rally    equal weight (RSP) lags SPY by 4%+ over 60 sessions while SPY is within 5% of its high
  W3 smallcap_lag    IWM lags SPY by 8%+ over 60 sessions while SPY is within 5% of its high
  W4 credit_lead     HYG/IEF down 2%+ over 20 sessions while SPY is within 5% of its high
  W5 vol_creep       VIX/VIX3M at 0.95+ (curve flattening) while SPY is within 3% of its high
  W6 below_200       SPY closes below its 200-day average (classic trend rule; a "late" control)
  W7 two_or_more     any 2 of W1-W5 on the same day
For each: how often it is on, the chance of a 10%+ / 20%+ drop starting
within the next 120 sessions vs the base rate on all days near highs, the
false-alarm rate, and a simple test: hold 50% instead of 100% SPY while the
warning is on (rebalanced daily, no costs) vs buy-and-hold, with CAGR and
max drawdown.

Writes research/derisk/derisk_study.json and prints the table.
"""
import csv, json, math, os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
START = "2007-04-12"


def f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def load():
    with open(os.path.join(ROOT, "flow_history.csv"), newline="") as fh:
        rows = [r for r in csv.DictReader(fh) if r["date"] >= "2006-01-01" and f(r.get("spy"))]
    return rows


def signals(rows):
    """Daily warning flags; usable live (see forward_test.py)."""
    S = [f(r["spy"]) for r in rows]
    get = lambda k: [f(r.get(k)) for r in rows]
    smh, rsp, iwm, hie, vix, v3 = get("smh"), get("rsp"), get("iwm"), get("hyg_ief"), get("vix"), get("vix3m")
    out = []
    for i in range(len(rows)):
        hi = max(S[max(0, i - 251):i + 1])
        near5 = S[i] >= 0.95 * hi
        near3 = S[i] >= 0.97 * hi

        def rel(x, h):
            if i < h or not x[i] or not x[i - h] or not S[i - h]:
                return None
            return (x[i] / x[i - h]) / (S[i] / S[i - h]) - 1
        r_smh, r_rsp, r_iwm = rel(smh, 60), rel(rsp, 60), rel(iwm, 60)
        c20 = (hie[i] / hie[i - 20] - 1) if i >= 20 and hie[i] and hie[i - 20] else None
        vt = vix[i] / v3[i] if vix[i] and v3[i] else None
        ma200 = sum(S[i - 199:i + 1]) / 200 if i >= 199 else None
        w = {
            "semis_lead": bool(near5 and r_smh is not None and r_smh <= -0.10),
            "narrow_rally": bool(near5 and r_rsp is not None and r_rsp <= -0.04),
            "smallcap_lag": bool(near5 and r_iwm is not None and r_iwm <= -0.08),
            "credit_lead": bool(near5 and c20 is not None and c20 <= -0.02),
            "vol_creep": bool(near3 and vt is not None and vt >= 0.95),
            "below_200": bool(ma200 and S[i] < ma200),
        }
        w["two_or_more"] = sum(w[k] for k in ("semis_lead", "narrow_rally", "smallcap_lag", "credit_lead", "vol_creep")) >= 2
        out.append(w)
    return out


def main():
    rows = load()
    W = signals(rows)
    k0 = next(i for i, r in enumerate(rows) if r["date"] >= START)
    D = [r["date"] for r in rows]; S = [f(r["spy"]) for r in rows]; n = len(S)
    # drawdown episode starts: the peak before each 10%+ / 20%+ drawdown
    peaks10, peaks20, ath, ai, cur = [], [], S[0], 0, None
    for i, c in enumerate(S):
        if c >= ath:
            if cur:
                (peaks20 if cur["b"] <= -0.20 else peaks10).append(cur["p"]) if cur["b"] <= -0.10 else None
                cur = None
            ath, ai = c, i
            continue
        b = c / ath - 1
        if cur is None:
            cur = {"p": ai, "b": b}
        cur["b"] = min(cur["b"], b)
    if cur and cur["b"] <= -0.10:
        (peaks20 if cur["b"] <= -0.20 else peaks10).append(cur["p"])
    big = sorted(peaks10 + peaks20)

    def drop_within(i, lvl, h=120):
        w = S[i + 1:i + 1 + h]
        if len(w) < h:
            return None
        hi = max(S[max(0, i - 251):i + 1])
        return min(w) / hi - 1 <= lvl  # 10%/20% below the high on the signal day

    near_hi = [i for i in range(k0, n) if S[i] >= 0.95 * max(S[max(0, i - 251):i + 1])]
    base10 = [drop_within(i, -0.10) for i in near_hi]; base10 = [x for x in base10 if x is not None]
    base20 = [drop_within(i, -0.20) for i in near_hi]; base20 = [x for x in base20 if x is not None]
    res = {"window": [D[k0], D[-1]], "base_near_high": {"days": len(near_hi), "p10_120d": round(100 * sum(base10) / len(base10), 1),
                                                        "p20_120d": round(100 * sum(base20) / len(base20), 1)},
           "peaks_10_20": [D[p] for p in peaks10], "peaks_20plus": [D[p] for p in peaks20], "signals": {}}

    def backtest(flag):
        eq_bh = eq = 1.0; pk_bh = pk = 1.0; mdd_bh = mdd = 0.0
        for i in range(k0 + 1, n):
            r = S[i] / S[i - 1] - 1
            expo = 0.5 if W[i - 1][flag] else 1.0  # act on yesterday's close
            eq_bh *= 1 + r; eq *= 1 + expo * r
            pk_bh = max(pk_bh, eq_bh); pk = max(pk, eq)
            mdd_bh = min(mdd_bh, eq_bh / pk_bh - 1); mdd = min(mdd, eq / pk - 1)
        yrs = (n - 1 - k0) / 252
        return {"cagr": round(100 * (eq ** (1 / yrs) - 1), 2), "maxdd": round(100 * mdd, 1),
                "bh_cagr": round(100 * (eq_bh ** (1 / yrs) - 1), 2), "bh_maxdd": round(100 * mdd_bh, 1)}

    for flag in ("semis_lead", "narrow_rally", "smallcap_lag", "credit_lead", "vol_creep", "below_200", "two_or_more"):
        on = [i for i in range(k0, n) if W[i][flag]]
        p10 = [drop_within(i, -0.10) for i in on]; p10 = [x for x in p10 if x is not None]
        p20 = [drop_within(i, -0.20) for i in on]; p20 = [x for x in p20 if x is not None]
        # warned before each big drop? (on at least once in the 120 sessions before its peak)
        caught = [D[p] for p in big if any(W[j][flag] for j in range(max(k0, p - 120), p + 1))]
        # distinct episodes (first day after 20+ quiet days)
        eps = [i for i in on if not any(W[j][flag] for j in range(max(0, i - 20), i))]
        res["signals"][flag] = {
            "days_on_pct": round(100 * len(on) / (n - k0), 1), "episodes": len(eps),
            "p10_120d": round(100 * sum(p10) / len(p10), 1) if p10 else None,
            "p20_120d": round(100 * sum(p20) / len(p20), 1) if p20 else None,
            "caught_peaks": f"{len(caught)}/{len(big)}", "caught": caught,
            "half_exposure_test": backtest(flag),
            "last_on": D[on[-1]] if on else None, "on_today": W[-1][flag],
        }
    with open(os.path.join(HERE, "derisk_study.json"), "w") as fh:
        json.dump(res, fh, indent=1)
    b = res["base_near_high"]
    print(f"window {res['window']} | base (days within 5% of high): 10%+ drop within 120d {b['p10_120d']}%, 20%+ {b['p20_120d']}%")
    print("big drops (peak dates):", res["peaks_10_20"], "| 20%+:", res["peaks_20plus"])
    for k, v in res["signals"].items():
        t = v["half_exposure_test"]
        print(f"{k:13s} on {v['days_on_pct']:5.1f}% of days, {v['episodes']:3d} episodes | 10%+ drop next 120d {v['p10_120d']}% | 20%+ {v['p20_120d']}% "
              f"| caught {v['caught_peaks']} | 50%-when-on: CAGR {t['cagr']} vs {t['bh_cagr']}, maxDD {t['maxdd']} vs {t['bh_maxdd']} | last on {v['last_on']}")


if __name__ == "__main__":
    main()
