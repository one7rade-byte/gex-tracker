"""
fit_dip_quality.py — learn which factors separate a temporary news dip
(buyable) from one that keeps underperforming, and validate out of sample.

Input:  research/news_shock/shock_events.csv (build_shock_dataset.py)
Output: dip_quality_model.json (repo root, read by score_dip_quality.py)
        research/news_shock/FINDINGS.md (human-readable results)

Two models, both logistic regression on standardized features:
  t0  decided at the close of the shock day
  t3  decided 3 trading days later, adding follow-through (Simon's "don't be
      first": wait to see whether the low holds)
Target: the stock beats SPY over the next 60 trading days (from the decision
day's close). Trained on shocks from 2010-2018, graded ONLY on 2019+ shocks
the model never saw. Score = predicted probability x 100.

Run locally (needs numpy + scikit-learn): python research/news_shock/fit_dip_quality.py
"""

import csv
import json
import os
from datetime import datetime, timezone

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
DATA = os.path.join(HERE, "shock_events.csv")
MODEL = os.path.join(ROOT, "dip_quality_model.json")
FINDINGS = os.path.join(HERE, "FINDINGS.md")
SPLIT = "2019-01-01"

BASE = ["drop_pct", "excess_pct", "spy_day_pct", "vol_ratio", "gap_pct", "close_loc", "pre60_pct",
        "above_200ma", "off_52w_high_pct", "spy_20d_pct", "spy_above_200ma", "vix"]
CONFIRM = ["t3_pct", "new_low_3d"]
LABELS = {
    "drop_pct": "Size of the drop", "excess_pct": "Drop vs the market that day",
    "spy_day_pct": "Market's own move that day", "vol_ratio": "Volume vs normal",
    "gap_pct": "Opening gap", "close_loc": "Closed off the lows (buyers stepped in)",
    "pre60_pct": "Run-up in the 60 days before", "above_200ma": "Was in an uptrend (above 200-day)",
    "off_52w_high_pct": "Distance from 52-week high before", "spy_20d_pct": "Market's 20-day trend",
    "spy_above_200ma": "Market in an uptrend", "vix": "VIX (market fear)",
    "t3_pct": "Bounce in the 3 days after", "new_low_3d": "Undercut the shock-day low within 3 days",
}
CLIP = {"vol_ratio": (0, 15), "gap_pct": (-40, 10), "pre60_pct": (-60, 120), "off_52w_high_pct": (-90, 0),
        "drop_pct": (-60, 0), "excess_pct": (-60, 0), "t3_pct": (-40, 40), "vix": (8, 80)}


def load():
    with open(DATA, newline="") as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        for k in BASE + CONFIRM + ["ex20", "ex60", "ex120", "ex60_from_t3", "ex120_from_t3", "recovered60", "mdd20"]:
            try:
                r[k] = float(r[k])
            except (TypeError, ValueError, KeyError):
                r[k] = None
    return rows


def matrix(rows, feats, med):
    X = np.array([[r[f] if r[f] is not None else med[f] for f in feats] for r in rows], dtype=float)
    for j, f in enumerate(feats):
        if f in CLIP:
            X[:, j] = np.clip(X[:, j], *CLIP[f])
    return X


def fit(rows, feats, target):
    rows = [r for r in rows if r[target] is not None]
    tr = [r for r in rows if r["date"] < SPLIT]
    te = [r for r in rows if r["date"] >= SPLIT]
    med = {f: float(np.median([r[f] for r in tr if r[f] is not None])) for f in feats}
    Xtr, Xte = matrix(tr, feats, med), matrix(te, feats, med)
    mu, sd = Xtr.mean(0), Xtr.std(0) + 1e-9
    ytr = np.array([r[target] > 0 for r in tr])
    yte = np.array([r[target] > 0 for r in te])
    m = LogisticRegression(C=0.5, max_iter=2000).fit((Xtr - mu) / sd, ytr)
    ptr = m.predict_proba((Xtr - mu) / sd)[:, 1]
    pte = m.predict_proba((Xte - mu) / sd)[:, 1]
    # Grade the 2019+ test set by score band (bands fixed from training quintiles).
    cuts = list(np.quantile(ptr, [0.2, 0.4, 0.6, 0.8]))
    band = np.digitize(pte, cuts)
    tab = []
    for b in range(5):
        sel = band == b
        ex = np.array([te[i][target] for i in np.where(sel)[0]])
        mdd = [te[i]["mdd20"] for i in np.where(sel)[0] if te[i]["mdd20"] is not None]
        tab.append({"band": b + 1, "n": int(sel.sum()),
                    "beat_spy_pct": round(float((ex > 0).mean() * 100), 1) if len(ex) else None,
                    "median_excess_pct": round(float(np.median(ex)), 2) if len(ex) else None,
                    "median_worst_20d_pct": round(float(np.median(mdd)), 2) if mdd else None})
    # Year-by-year stability of the top vs bottom band on the test set.
    years = {}
    for i, r in enumerate(te):
        y = r["date"][:4]
        years.setdefault(y, {"top": [], "bottom": []})
        if band[i] == 4:
            years[y]["top"].append(r[target] > 0)
        elif band[i] == 0:
            years[y]["bottom"].append(r[target] > 0)
    by_year = {y: {"top_beat_pct": round(100 * sum(v["top"]) / len(v["top"]), 1) if v["top"] else None,
                   "bottom_beat_pct": round(100 * sum(v["bottom"]) / len(v["bottom"]), 1) if v["bottom"] else None,
                   "n_top": len(v["top"]), "n_bottom": len(v["bottom"])} for y, v in sorted(years.items())}
    return {
        "features": feats, "target": target, "median_fill": med,
        "mean": mu.tolist(), "std": sd.tolist(), "coef": m.coef_[0].tolist(), "intercept": float(m.intercept_[0]),
        "band_cuts": [float(c) for c in cuts],
        "n_train": len(tr), "n_test": len(te),
        "base_rate_train_pct": round(float(ytr.mean() * 100), 1), "base_rate_test_pct": round(float(yte.mean() * 100), 1),
        "auc_train": round(float(roc_auc_score(ytr, ptr)), 3), "auc_test": round(float(roc_auc_score(yte, pte)), 3),
        "test_by_band": tab, "test_by_year": by_year,
    }


def univariate(rows, f, target="ex60"):
    rows = [r for r in rows if r[f] is not None and r[target] is not None]
    if not rows:
        return []
    vals = sorted(r[f] for r in rows)
    if len(set(vals)) <= 2:
        groups = {v: [r for r in rows if r[f] == v] for v in sorted(set(vals))}
        names = {v: str(int(v)) for v in groups}
    else:
        q = [vals[int(len(vals) * p)] for p in (0.2, 0.4, 0.6, 0.8)]
        groups, names = {}, {}
        for b in range(5):
            lo, hi = (q[b - 1] if b else -1e18), (q[b] if b < 4 else 1e18)
            groups[b] = [r for r in rows if lo <= r[f] < hi]
            names[b] = f"{'≤' if b == 0 else ''}{(q[b] if b < 4 else q[3]):.2f}{'+' if b == 4 else ''}" if b in (0, 4) else f"{q[b-1]:.2f}–{q[b]:.2f}"
    out = []
    for k, g in groups.items():
        ex = [r[target] for r in g]
        out.append((names[k], len(g), round(100 * sum(e > 0 for e in ex) / len(ex), 1), round(float(np.median(ex)), 2)))
    return out


def main():
    rows = load()
    m0 = fit(rows, BASE, "ex60")
    m3 = fit(rows, BASE + CONFIRM, "ex60_from_t3")
    # Mag 7 get their own track record: the general score does not rank their
    # shocks (AUC ~0.5 when tested), and they have recovered more often overall.
    M7 = {"AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "GOOG", "META", "TSLA"}
    g = [r for r in rows if r["ticker"] in M7 and r["ex60"] is not None]
    g120 = [r["ex120"] for r in g if r["ex120"] is not None]
    mdd = [r["mdd20"] for r in g if r["mdd20"] is not None]
    mag7 = {"n": len(g), "beat_spy_60d_pct": round(100 * float(np.mean([r["ex60"] > 0 for r in g])), 1),
            "median_excess_60d_pct": round(float(np.median([r["ex60"] for r in g])), 2),
            "beat_spy_120d_pct": round(100 * float(np.mean([x > 0 for x in g120])), 1),
            "median_excess_120d_pct": round(float(np.median(g120)), 2),
            "median_worst_20d_pct": round(float(np.median(mdd)), 2)}
    Xg = matrix(g, BASE, m0["median_fill"])
    pg = 1 / (1 + np.exp(-(((Xg - np.array(m0["mean"])) / np.array(m0["std"])) @ np.array(m0["coef"]) + m0["intercept"])))
    mag7["score_auc_within_mag7"] = round(float(roc_auc_score([r["ex60"] > 0 for r in g], pg)), 3)
    model = {"built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "split": SPLIT, "mag7": mag7,
             "labels": LABELS, "clip": CLIP, "t0": m0, "t3": m3,
             "events_total": len(rows), "event_type_available": any(r.get("event_type") for r in rows)}
    with open(MODEL, "w") as fh:
        json.dump(model, fh, indent=1)

    L = ["# News shock study — findings", "",
         f"Built {model['built_at']} from `shock_events.csv` ({len(rows)} shock days in current S&P 500 members since 2010).",
         "Shock day = stock down ≥6% close-to-close, ≥5 points worse than SPY, volume ≥1.5x its 50-day average.",
         "Outcome = stock return minus SPY return over the next 60 trading days. \"Beat SPY\" = that number > 0.",
         f"Weights learned on shocks before {SPLIT}; every result below is graded on {SPLIT[:4]}+ shocks the model never saw.",
         "Survivorship bias: only TODAY's index members are included, so companies that collapsed and dropped out are missing. "
         "Absolute recovery rates are too optimistic; the comparisons between factors are more trustworthy.", ""]
    for name, m in (("At the shock-day close (t0)", m0), ("After waiting 3 days for confirmation (t3)", m3)):
        L += [f"## {name}", "",
              f"Train n={m['n_train']}, test n={m['n_test']}. Beat-SPY base rate: train {m['base_rate_train_pct']}%, test {m['base_rate_test_pct']}%. "
              f"AUC train {m['auc_train']}, **test {m['auc_test']}** (0.5 = coin flip).", "",
              "| Score band (test set) | n | Beat SPY over 60d | Median excess return | Median worst point, next 20d |", "|---|---|---|---|---|"]
        for b in m["test_by_band"]:
            L.append(f"| {b['band']} {'(lowest)' if b['band']==1 else '(highest)' if b['band']==5 else ''} | {b['n']} | {b['beat_spy_pct']}% | {b['median_excess_pct']}% | {b['median_worst_20d_pct']}% |")
        L += ["", "Weights (standardized; + means more likely to recover):", "", "| Factor | Weight |", "|---|---|"]
        for f, c in sorted(zip(m["features"], m["coef"]), key=lambda x: -abs(x[1])):
            L.append(f"| {LABELS.get(f, f)} | {c:+.3f} |")
        L += ["", "Top vs bottom band by year (test set, % that beat SPY):", "", "| Year | Top band | Bottom band |", "|---|---|---|"]
        for y, v in m["test_by_year"].items():
            L.append(f"| {y} | {v['top_beat_pct']}% (n={v['n_top']}) | {v['bottom_beat_pct']}% (n={v['n_bottom']}) |")
        L.append("")
    mg = model["mag7"]
    L += ["## Mag 7 (AAPL, MSFT, NVDA, AMZN, GOOGL/GOOG, META, TSLA)", "",
          f"{mg['n']} shocks. Beat SPY over 60 days {mg['beat_spy_60d_pct']}% (median {mg['median_excess_60d_pct']:+}%), "
          f"over 120 days {mg['beat_spy_120d_pct']}% (median {mg['median_excess_120d_pct']:+}%). Median worst point in the next 20 days "
          f"{mg['median_worst_20d_pct']}%. The general score does **not** rank Mag 7 shocks (AUC {mg['score_auc_within_mag7']} within Mag 7), "
          "so they are judged on this track record instead. Survivorship bias is strongest here: these are, by definition, today's biggest winners.", ""]
    L += ["## Each factor on its own (all years, quintiles)", ""]
    for f in BASE + CONFIRM:
        t = univariate(rows, f, "ex60" if f in BASE else "ex60_from_t3")
        if not t:
            continue
        L += [f"**{LABELS.get(f, f)}** (`{f}`)", "", "| Bucket | n | Beat SPY 60d | Median excess |", "|---|---|---|---|"]
        L += [f"| {a} | {b} | {c}% | {d}% |" for a, b, c, d in t]
        L.append("")
    if model["event_type_available"]:
        L += ["## By SEC 8-K event type", "", "| Event type | n | Beat SPY 60d | Median excess |", "|---|---|---|---|"]
        for et in sorted({r["event_type"] for r in rows if r.get("event_type")}):
            g = [r["ex60"] for r in rows if r.get("event_type") == et and r["ex60"] is not None]
            if g:
                L.append(f"| {et} | {len(g)} | {100*sum(x>0 for x in g)/len(g):.1f}% | {np.median(g):.2f}% |")
    else:
        L += ["## SEC 8-K event type: not yet available",
              "", "SEC blocks requests from GitHub Actions servers, so event type (earnings / leadership / restatement / no filing) "
              "and revenue trend are not in this build. See README for how to add them.", ""]
    with open(FINDINGS, "w") as fh:
        fh.write("\n".join(L) + "\n")
    print("\n".join(L[:40]))


if __name__ == "__main__":
    main()
