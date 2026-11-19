"""
track_drawdown.py — follow the 2026 drawdown from its first signs to full
recovery, so we can learn what it looked like at every stage.

Start: SPY's all-time-high close on 2026-10-06 (779.09). QQQ peaked the same
day. Semis (SMH) peaked earlier, on 2026-06-22. End: SPY closes at a new
all-time high above that peak. After that, FINAL_REPORT.md is written and
tracking stops.

Run from the repo root after the daily pull:
    python research/drawdown_2026/track_drawdown.py

Writes (idempotent, rebuilt from the data each run):
  research/drawdown_2026/drawdown_log.csv   one row per trading day since the peak
  research/drawdown_2026/ladder_ledger.csv  each buy-low tranche: date hit, price, return now, worst since
  research/drawdown_2026/stage.json         current stage + key dates (peak, lows, tiers)

Stages (descriptive, decided from the data each day):
  NEAR HIGH      within 3% of the peak and never more than 5% below it yet
  FALLING        SPY made a new closing low within the last 5 sessions
  BASING         no new low for 5+ sessions, still more than 5% below the high
  RECOVERING     back within 5% of the high
  RECOVERED      new all-time high: done
The "why" (catalysts, the AI-bubble question) is written by the daily
scheduled task into CAUSE_LOG.md; this script only does the numbers.
"""

import csv
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, ROOT)
from quick_action import LADDER  # noqa: E402  (single source of truth for the tranche plan)

PEAK_DATE = "2026-10-06"


def f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def read(name):
    with open(os.path.join(ROOT, name), newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def main():
    flow = {r["date"]: r for r in read("flow_history.csv")}
    gex = {r["date"]: r for r in read("gex_log.csv") if r.get("ticker", "SPY").strip() == "SPY"}
    reg = {r["date"]: r for r in read("regime_log.csv")}
    dates = sorted(d for d in flow if d >= PEAK_DATE and f(flow[d].get("spy")))
    if not dates:
        sys.exit("no data since peak")

    peak = {k: f(flow[PEAK_DATE].get(k)) for k in ("spy", "qqq", "smh", "iwm", "rsp")}
    # SMH and IWM peaked earlier; measure them from their own highs too.
    own_hi = {}
    for k in ("smh", "iwm"):
        vals = [(d, f(r.get(k))) for d, r in flow.items() if f(r.get(k))]
        own_hi[k] = max(vals, key=lambda x: x[1])

    rows, low, low_date, hyg_hist = [], peak["spy"], PEAK_DATE, []
    for i, d in enumerate(dates):
        r, g, rg = flow[d], gex.get(d, {}), reg.get(d, {})
        spy = f(r["spy"])
        if spy < low:
            low, low_date = spy, d
        hie = f(r.get("hyg_ief"))
        hyg_hist.append(hie)
        prev20 = hyg_hist[-21] if len(hyg_hist) > 20 else hyg_hist[0]
        row = {
            "date": d, "day": i,
            "spy": spy, "spy_dd_pct": round((spy / peak["spy"] - 1) * 100, 2),
            "qqq_dd_pct": round((f(r["qqq"]) / peak["qqq"] - 1) * 100, 2) if f(r.get("qqq")) else None,
            "smh_dd_from_own_high_pct": round((f(r["smh"]) / own_hi["smh"][1] - 1) * 100, 2) if f(r.get("smh")) else None,
            "iwm_dd_from_own_high_pct": round((f(r["iwm"]) / own_hi["iwm"][1] - 1) * 100, 2) if f(r.get("iwm")) else None,
            "rsp_dd_pct": round((f(r["rsp"]) / peak["rsp"] - 1) * 100, 2) if f(r.get("rsp")) else None,
            "spy_low_so_far": round(low, 2), "low_date": low_date,
            "days_since_low": sum(1 for x in dates[:i + 1] if x > low_date),
            "vix": f(r.get("vix")), "vix_vix3m": f(r.get("vix_vix3m")), "vvix": f(r.get("vvix")), "move": f(r.get("move")),
            "hyg_ief": hie, "hyg_ief_20d_pct": round((hie / prev20 - 1) * 100, 2) if hie and prev20 else None,
            "yield_10y": f(g.get("yield_10y")), "usdjpy": f(r.get("usdjpy")), "btc": f(r.get("btc")),
            "smh_spy": f(r.get("smh_spy")), "rsp_spy": f(r.get("rsp_spy")), "defensive_cyclical": f(r.get("defensive_cyclical")),
            "spy_vol_ratio20": f(r.get("spy_vol_ratio20")),
            "net_gex_b": f(g.get("net_gex_b")), "rsi": f(g.get("spy_rsi_14")), "pc_ratio": f(g.get("pc_ratio")),
            "regime_signal": rg.get("regime_signal", ""), "composite": f(rg.get("composite_score")),
        }
        dd = row["spy_dd_pct"]
        if spy > peak["spy"] and i > 0:
            stage = "RECOVERED"
        elif dd > -5 and low_date != d and (low / peak["spy"] - 1) * 100 <= -5:
            stage = "RECOVERING"
        elif dd > -3 and (low / peak["spy"] - 1) * 100 > -5:
            stage = "NEAR HIGH"
        elif row["days_since_low"] < 5:
            stage = "FALLING"
        else:
            stage = "BASING"
        row["stage"] = stage
        rows.append(row)

    with open(os.path.join(HERE, "drawdown_log.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    # Ladder ledger: what each tranche would have done.
    last = rows[-1]
    ledger = []
    for t, wt in LADDER:
        price = round(peak["spy"] * (1 + t / 100), 2)
        k = next((j for j, r in enumerate(rows) if r["spy"] <= price), None)
        if k is None:
            ledger.append({"tier": t, "price": price, "weight_pct": wt, "hit_date": "", "ret_now_pct": "",
                           "worst_since_pct": "", "days_held": ""})
            continue
        after = [r["spy"] for r in rows[k:]]
        ledger.append({"tier": t, "price": price, "weight_pct": wt, "hit_date": rows[k]["date"],
                       "ret_now_pct": round((last["spy"] / price - 1) * 100, 2),
                       "worst_since_pct": round((min(after) / price - 1) * 100, 2),
                       "days_held": len(rows) - 1 - k})
    with open(os.path.join(HERE, "ladder_ledger.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(ledger[0]))
        w.writeheader()
        w.writerows(ledger)
    hit = [x for x in ledger if x["hit_date"]]
    if hit:
        wsum = sum(x["weight_pct"] for x in hit)
        blended = sum(x["weight_pct"] * x["ret_now_pct"] for x in hit) / wsum
    else:
        blended = None

    stage = {"as_of": last["date"], "stage": last["stage"], "day": last["day"],
             "peak": {"date": PEAK_DATE, "spy": peak["spy"]},
             "spy_dd_pct": last["spy_dd_pct"], "qqq_dd_pct": last["qqq_dd_pct"],
             "smh_dd_from_own_high_pct": last["smh_dd_from_own_high_pct"],
             "low": {"date": last["low_date"], "spy": last["spy_low_so_far"],
                     "dd_pct": round((last["spy_low_so_far"] / peak["spy"] - 1) * 100, 2)},
             "tranches_hit": len(hit), "ladder_blended_return_pct": round(blended, 2) if blended is not None else None,
             "recovered": last["stage"] == "RECOVERED"}
    with open(os.path.join(HERE, "stage.json"), "w") as fh:
        json.dump(stage, fh, indent=1)

    print(f"{last['date']} day {last['day']}: {last['stage']} | SPY {last['spy']} ({last['spy_dd_pct']:+}% from {peak['spy']}) "
          f"| QQQ {last['qqq_dd_pct']:+}% | SMH {last['smh_dd_from_own_high_pct']:+}% from its own high")
    print(f"  low so far {last['spy_low_so_far']} on {last['low_date']} ({stage['low']['dd_pct']:+}%), {last['days_since_low']} sessions ago")
    print(f"  VIX {last['vix']} (VIX/VIX3M {last['vix_vix3m']}), VVIX {last['vvix']}, MOVE {last['move']}, 10y {last['yield_10y']}, "
          f"HYG/IEF 20d {last['hyg_ief_20d_pct']}%")
    for x in ledger:
        print(f"  tranche {x['tier']}% @ {x['price']}: " + (f"hit {x['hit_date']}, now {x['ret_now_pct']:+}%, worst {x['worst_since_pct']:+}%"
                                                          if x["hit_date"] else "not yet"))
    if stage["recovered"]:
        print("RECOVERED: SPY closed at a new all-time high. Write FINAL_REPORT.md.")


if __name__ == "__main__":
    main()
