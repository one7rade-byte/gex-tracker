"""Tests for quick_action.py DEFEND 2-day persistence. Run: python test_quick_action.py"""
import csv
import json
import os
import tempfile

import quick_action as qa

GEX_COLS = ["date", "ticker", "spot_price", "net_gex_b", "vix", "zero_gamma", "hyg", "vix_term_structure"]


def run(hyg_series, signals=None):
    """Write synthetic gex_log/regime_log into a temp dir, run quick_action.main(), return the JSON."""
    cwd = os.getcwd()
    with tempfile.TemporaryDirectory() as d:
        os.chdir(d)
        try:
            with open("gex_log.csv", "w", newline="") as fh:
                w = csv.writer(fh)
                w.writerow(GEX_COLS)
                for i, h in enumerate(hyg_series):
                    w.writerow([f"2026-01-{i + 1:02d}", "SPY", 700, 5, 15, 690, h, "contango"])
            with open("regime_log.csv", "w", newline="") as fh:
                w = csv.writer(fh)
                w.writerow(["date", "regime_signal"])
                for i in range(len(hyg_series)):
                    sig = (signals or {}).get(i, "HOLD")
                    w.writerow([f"2026-01-{i + 1:02d}", sig])
            qa.main()
            with open("quick_action.json") as fh:
                return json.load(fh)
        finally:
            os.chdir(cwd)


def test_one_day_credit_trigger_is_heads_up_only():
    # HYG flat, then -2% on the last day only: 5d change <= -1.5 today, not yesterday.
    q = run([80] * 9 + [78.4])
    assert q["action"] == "HOLD", q
    assert q["defend_triggers_today"] and not q["defend_triggers_yesterday"]
    assert "Heads-up" in q["headline"]


def test_two_day_credit_trigger_defends():
    q = run([80] * 8 + [78.4, 78.3])
    assert q["action"] == "DEFEND", q
    assert "Not a sell signal" in q["headline"]


def test_regime_crisis_two_days_defends_and_one_day_does_not():
    assert run([80] * 10, {8: "CRISIS", 9: "CRISIS"})["action"] == "DEFEND"
    assert run([80] * 10, {9: "CRISIS"})["action"] == "HOLD"


def test_no_trigger_no_heads_up():
    q = run([80] * 10)
    assert q["action"] == "HOLD" and "Heads-up" not in q["headline"]


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
