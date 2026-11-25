"""
forward_test.py — out-of-sample forward test of the de-risking warnings.

Rules were FROZEN on 2026-11-25 (see README.md in this folder). Do not edit
the thresholds in derisk_study.signals(): a forward test only counts if the
rules stay fixed. Runs daily in gex_daily.yml after flow_extras.py.

Every day it:
  1. appends today's warning flags (W1-W5, W7 and below_200) to
     research/derisk/forward_log.csv (idempotent by date);
  2. resolves rows that are 120+ sessions old: the worst close within the next
     120 sessions vs the 1-year high on the signal day (did a 10%+ / 20%+ drop
     follow?);
  3. writes research/derisk/forward_summary.json: for each warning, the hit
     rate so far vs the base rate on all logged days near a high. These are
     the same metrics as the backtest, so the two can be compared directly.
"""
import csv, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import derisk_study as D  # noqa: E402

FROZEN = "2026-11-25"
LOG = os.path.join(HERE, "forward_log.csv")
SUMMARY = os.path.join(HERE, "forward_summary.json")
FLAGS = ["semis_lead", "narrow_rally", "smallcap_lag", "credit_lead", "vol_creep", "two_or_more", "below_200"]


def main():
    rows = D.load()
    W = D.signals(rows)
    S = [D.f(r["spy"]) for r in rows]
    idx = {r["date"]: i for i, r in enumerate(rows)}
    log = {}
    if os.path.exists(LOG):
        with open(LOG, newline="") as fh:
            log = {r["date"]: r for r in csv.DictReader(fh)}
    # (1) log every session since the freeze date that isn't logged yet
    for i, r in enumerate(rows):
        if r["date"] < FROZEN:
            continue
        hi = max(S[max(0, i - 251):i + 1])
        row = log.get(r["date"], {"date": r["date"]})
        row.update({"spy": round(S[i], 2), "high_1y": round(hi, 2), "near_high": int(S[i] >= 0.95 * hi)})
        row.update({k: int(W[i][k]) for k in FLAGS})
        log[r["date"]] = row
    # (2) resolve outcomes after 120 sessions
    for d, row in log.items():
        i = idx.get(d)
        if i is None or i + 120 >= len(S) or row.get("worst_120d_vs_high_pct") not in (None, ""):
            continue
        w = min(S[i + 1:i + 121]) / float(row["high_1y"]) - 1
        row["worst_120d_vs_high_pct"] = round(100 * w, 2)
        row["drop10"], row["drop20"] = int(w <= -0.10), int(w <= -0.20)
    fields = ["date", "spy", "high_1y", "near_high"] + FLAGS + ["worst_120d_vs_high_pct", "drop10", "drop20"]
    out = [log[d] for d in sorted(log)]
    with open(LOG, "w", newline="") as fh:
        w_ = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w_.writeheader()
        w_.writerows(out)
    # (3) summary
    res = [r for r in out if r.get("drop10") not in (None, "")]
    near = [r for r in res if str(r["near_high"]) == "1"]
    summ = {"frozen": FROZEN, "logged_days": len(out), "resolved_days": len(res),
            "base_near_high": {"n": len(near), "drop10_pct": round(100 * sum(int(r["drop10"]) for r in near) / len(near), 1) if near else None},
            "today": {k: int(out[-1][k]) for k in FLAGS} if out else {}, "as_of": out[-1]["date"] if out else None, "flags": {}}
    for k in FLAGS:
        on = [r for r in res if str(r[k]) == "1"]
        summ["flags"][k] = {"days_on_resolved": len(on),
                            "drop10_pct": round(100 * sum(int(r["drop10"]) for r in on) / len(on), 1) if on else None,
                            "drop20_pct": round(100 * sum(int(r["drop20"]) for r in on) / len(on), 1) if on else None}
    with open(SUMMARY, "w") as fh:
        json.dump(summ, fh, indent=1)
    on_today = ", ".join(k for k, v in summ["today"].items() if v) or "no warnings"
    print(f"forward test: {len(out)} days logged since {FROZEN}, {len(res)} resolved; today: {on_today}")


if __name__ == "__main__":
    main()
