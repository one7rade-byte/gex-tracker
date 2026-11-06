"""
track_event.py — daily tracker for the 2026-11-05 black-swan-watch event
(AI/chip-led selloff: SPY -4.4%, QQQ -6.5%, VIX 16.6 -> 28.2).

Run from the repo root after the daily 6pm pull has landed on main:
    python research/event_2026_11_05/track_event.py

What it does (idempotent — re-running a day replaces that day's row):
  1. Appends one row per trading day since the trigger to tracking_log.csv
     with the metrics that matter for this event.
  2. Evaluates two checklists that were FIXED ON 2026-11-05, before any
     outcome was known (pre-registered, so no hindsight tuning):
       - ESCALATION (crash-path) conditions
       - STABILIZATION (add) conditions
  3. Maintains entry_ledger.csv: the first date each candidate entry rule
     fired, its entry price, and its result so far (return to latest close
     and worst drawdown after entry). This is the "when to add" dataset.

HYG 5-day change is computed here directly from gex_log.csv, NOT taken
from regime_log.csv — regime_analyzer.py's hyg_5d_change compares against
macro_history.csv, which stopped updating on 2026-08-17, so that field
(and its "HYG dropped $X in 5 days" warning) is wrong as of this event.
"""

import csv
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HERE = os.path.dirname(os.path.abspath(__file__))
GEX_LOG = os.path.join(ROOT, "gex_log.csv")
REGIME_LOG = os.path.join(ROOT, "regime_log.csv")
TRACK_LOG = os.path.join(HERE, "tracking_log.csv")
LEDGER = os.path.join(HERE, "entry_ledger.csv")

# ── Event constants (fixed 2026-11-05) ───────────────────────────────────────
TRIGGER_DATE = "2026-11-05"
TRIGGER_CLOSE = 734.40          # SPY close on trigger day
PRE_EVENT_HIGH = 781.50         # SPY 60-day closing high before trigger
TRIGGER_QQQ = 647.98            # QQQ close on trigger day
STRONG_BUY_ENTRY = 751.96       # SPY close on 2026-11-02 (mid-point of the Oct30–Nov3 STRONG_BUY run)
END_DATE = "2026-12-04"


def f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def read(path):
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def write(path, rows, fields):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def main():
    gex = read(GEX_LOG)
    reg = {r["date"]: r for r in read(REGIME_LOG)}
    dates = [r["date"] for r in gex]
    if TRIGGER_DATE not in dates:
        sys.exit("trigger date not in gex_log.csv")
    t0 = dates.index(TRIGGER_DATE)

    rows = []
    streak_backw = 0
    streak_deep_neg = 0
    for i in range(t0, len(gex)):
        g = gex[i]
        r = reg.get(g["date"], {})
        spy, qqq = f(g["spot_price"]), f(g["qqq_spot"])
        vix, v9 = f(g["vix"]), f(g["vix9d"])
        gexb, hyg = f(g["net_gex_b"]), f(g["hyg"])
        hyg_prev5 = f(gex[i - 5]["hyg"]) if i >= 5 else None
        hyg5 = round((hyg / hyg_prev5 - 1) * 100, 2) if hyg and hyg_prev5 else None
        term = (g.get("vix_term_structure") or "").strip()
        ma200 = f(g["spy_200ma"])
        zg = f(g["zero_gamma"])
        streak_backw = streak_backw + 1 if term == "backwardation" else 0
        streak_deep_neg = streak_deep_neg + 1 if (gexb is not None and gexb < -10 and vix and vix > 25) else 0

        # ESCALATION — conditions that separated real declines (2008-06,
        # 2020-02) from the shallow near-high shocks in the analog set.
        esc = {
            "credit_breaking": hyg5 is not None and hyg5 <= -1.5,
            "backwardation_3d": streak_backw >= 3,
            "below_trigger_close": spy is not None and spy < TRIGGER_CLOSE,
            "below_200ma": spy is not None and ma200 is not None and spy < ma200,
            "deep_neg_gex_3d_vix25": streak_deep_neg >= 3,
            "qqq_new_low": qqq is not None and qqq < TRIGGER_QQQ,
        }
        # STABILIZATION — conditions that mark fear unwinding.
        stab = {
            "contango_restored": term == "contango",
            "vix_below_22": vix is not None and vix < 22,
            "vix9d_below_vix": v9 is not None and vix is not None and v9 < vix,
            "credit_holding": hyg5 is not None and hyg5 >= 0,
            "gex_positive": gexb is not None and gexb > 0,
            "above_zero_gamma": spy is not None and zg is not None and spy > zg,
        }
        n_esc, n_stab = sum(esc.values()), sum(stab.values())
        if n_esc >= 3:
            state = "ESCALATING"
        elif n_stab >= 4 and n_esc <= 1:
            state = "STABILIZING"
        else:
            state = "UNRESOLVED"

        rows.append({
            "date": g["date"],
            "day": i - t0,
            "spy": spy, "qqq": qqq,
            "spy_vs_trigger_pct": round((spy / TRIGGER_CLOSE - 1) * 100, 2) if spy else None,
            "spy_dd_from_high_pct": round((spy / PRE_EVENT_HIGH - 1) * 100, 2) if spy else None,
            "qqq_vs_trigger_pct": round((qqq / TRIGGER_QQQ - 1) * 100, 2) if qqq else None,
            "strong_buy_entry_pct": round((spy / STRONG_BUY_ENTRY - 1) * 100, 2) if spy else None,
            "vix": vix, "vix9d": v9, "term": term, "net_gex_b": gexb,
            "zero_gamma": zg, "put_wall": f(g["put_wall"]), "spy_200ma": ma200,
            "rsi": f(g["spy_rsi_14"]), "skew": f(g["skew_index"]),
            "hyg": hyg, "hyg_5d_pct_true": hyg5,
            "copper": f(g["copper"]), "yield_10y": f(g["yield_10y"]),
            "gex_signal": (g.get("signal") or "")[:50],
            "regime_signal": r.get("regime_signal", ""),
            "composite": f(r.get("composite_score")),
            "escalation_hits": ";".join(k for k, v in esc.items() if v),
            "stabilization_hits": ";".join(k for k, v in stab.items() if v),
            "n_escalation": n_esc, "n_stabilization": n_stab,
            "state": state,
        })

    write(TRACK_LOG, rows, list(rows[0].keys()))

    # ── Entry ledger: first firing date per candidate add rule ───────────────
    rules = {
        "A_trigger_day_close": lambda x: x["day"] == 0,
        "B_first_contango_after_trigger": lambda x: x["day"] > 0 and x["term"] == "contango",
        "C_first_vix_below_22": lambda x: x["vix"] is not None and x["vix"] < 22,
        "D_first_gex_positive": lambda x: x["net_gex_b"] is not None and x["net_gex_b"] > 0,
        "E_first_close_above_zero_gamma": lambda x: x["zero_gamma"] and x["spy"] > x["zero_gamma"],
        "F_first_STABILIZING_state": lambda x: x["state"] == "STABILIZING",
        "G_spy_minus_5pct_from_high": lambda x: x["spy_dd_from_high_pct"] <= -5,
        "H_spy_minus_10pct_from_high": lambda x: x["spy_dd_from_high_pct"] <= -10,
        "I_rsi_below_30": lambda x: x["rsi"] is not None and x["rsi"] < 30,
    }
    last = rows[-1]
    ledger = []
    for name, cond in rules.items():
        hit = next((k for k, x in enumerate(rows) if cond(x)), None)
        if hit is None:
            ledger.append({"rule": name, "fired_date": "", "entry_spy": "",
                           "ret_to_latest_pct": "", "max_dd_after_pct": "", "days_held": ""})
            continue
        e = rows[hit]["spy"]
        after = [x["spy"] for x in rows[hit:]]
        ledger.append({
            "rule": name, "fired_date": rows[hit]["date"], "entry_spy": e,
            "ret_to_latest_pct": round((last["spy"] / e - 1) * 100, 2),
            "max_dd_after_pct": round((min(after) / e - 1) * 100, 2),
            "days_held": len(rows) - 1 - hit,
        })
    write(LEDGER, ledger, list(ledger[0].keys()))

    # ── Console summary (the scheduled task reads this) ───────────────────────
    prev = rows[-2]["state"] if len(rows) > 1 else None
    print(f"{last['date']} (day {last['day']}) state={last['state']}"
          + (f" (changed from {prev})" if prev and prev != last["state"] else ""))
    print(f"  SPY {last['spy']} ({last['spy_vs_trigger_pct']:+}% vs trigger, "
          f"{last['spy_dd_from_high_pct']:+}% from high) | QQQ {last['qqq_vs_trigger_pct']:+}% vs trigger")
    print(f"  VIX {last['vix']} {last['term']} | GEX {last['net_gex_b']}B | HYG 5d {last['hyg_5d_pct_true']}% "
          f"| RSI {last['rsi']} | 200MA {last['spy_200ma']} | regime {last['regime_signal']}")
    print(f"  escalation [{last['n_escalation']}/6]: {last['escalation_hits'] or '-'}")
    print(f"  stabilization [{last['n_stabilization']}/6]: {last['stabilization_hits'] or '-'}")
    print("  entry ledger:")
    for L in ledger:
        if L["fired_date"]:
            print(f"    {L['rule']}: {L['fired_date']} @ {L['entry_spy']} -> {L['ret_to_latest_pct']:+}% "
                  f"(worst {L['max_dd_after_pct']:+}%)")
        else:
            print(f"    {L['rule']}: not yet")
    if last["date"] >= END_DATE:
        print("END_DATE reached — write the final report.")


if __name__ == "__main__":
    main()
