"""Tests for MAE/MFE tracking in track_signal_performance.py.

Run from repo root:  python -m unittest tests/test_track_signal_performance.py
"""
import csv
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import track_signal_performance as tsp  # noqa: E402

# 26 trading days. Day 0 = STRONG_BUY at 100. Path dips to 96 on day 3, then
# recovers to finish +2% at day 5 / +5% at day 10 / +8% at day 20: a "winner
# that first dipped 4%", which a hit-rate-only summary hides.
PRICES = [100, 99, 98, 96, 99, 102, 103, 104, 103, 104, 105,
          104, 105, 106, 105, 106, 107, 106, 107, 107, 108,
          108, 109, 110, 109, 111]
DATES = [f"2026-01-{d:02d}" for d in range(1, 27)]


class MaeTrackingTest(unittest.TestCase):
    def setUp(self):
        self.cwd = os.getcwd()
        self.tmp = tempfile.mkdtemp()
        os.chdir(self.tmp)
        with open(tsp.GEX_LOG, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["date", "ticker", "spot_price"])
            for d, p in zip(DATES, PRICES):
                w.writerow([d, "SPY", p])
                w.writerow([d, "QQQ", p * 0.8])  # ignored: SPY rows only
        with open(tsp.REGIME_LOG, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["date", "regime_signal", "composite_score"])
            w.writerow([DATES[0], "STRONG_BUY", "4.7"])
            w.writerow([DATES[20], "BUY_WATCH", "1.0"])   # 20d window still open
            w.writerow([DATES[24], "STRONG_BUY", "2.0"])  # still open

    def tearDown(self):
        os.chdir(self.cwd)
        shutil.rmtree(self.tmp)

    def _log(self):
        with open(tsp.PERF_LOG, newline="") as f:
            return {(r["date"], int(r["horizon_days"])): r for r in csv.DictReader(f)}

    def test_new_rows_carry_mae_and_mfe(self):
        tsp.main()
        log = self._log()
        r5 = log[(DATES[0], 5)]
        self.assertEqual(float(r5["return_pct"]), 2.0)
        self.assertEqual(float(r5["mae_pct"]), -4.0)   # 96 on day 3
        self.assertEqual(float(r5["mfe_pct"]), 2.0)
        r20 = log[(DATES[0], 20)]
        self.assertEqual(float(r20["return_pct"]), 8.0)
        self.assertEqual(float(r20["mae_pct"]), -4.0)
        self.assertEqual(float(r20["mfe_pct"]), 8.0)

    def test_summary_exposes_hidden_drawdown(self):
        tsp.main()
        s = json.load(open(tsp.SUMMARY_JSON))
        b = s["by_regime_signal"]["STRONG_BUY"]["20"]
        self.assertEqual(b["hit_rate_pct"], 100.0)
        self.assertEqual(b["pct_mae_le_minus3"], 100.0)
        self.assertEqual(b["winners_that_first_dipped_le_minus2"], 1)
        self.assertEqual(b["worst_mae_pct"], -4.0)

    def test_open_windows_listed(self):
        tsp.main()
        s = json.load(open(tsp.SUMMARY_JSON))
        opens = {o["date"]: o for o in s["open_20d_windows"]}
        self.assertEqual(set(opens), {DATES[20], DATES[24]})
        o = opens[DATES[20]]  # entry 108, path 108,109,110,109,111
        self.assertEqual(o["days_elapsed"], 5)
        self.assertEqual(o["return_to_date_pct"], round((111 - 108) / 108 * 100, 2))
        self.assertEqual(o["mae_to_date_pct"], 0.0)
        self.assertEqual(opens[DATES[25 - 1]]["days_elapsed"], 1)

    def test_backfills_old_format_log_without_touching_logged_values(self):
        # An old-format log (no mae/mfe columns) with a deliberately odd exit
        # value, to prove existing logged fields are preserved, not recomputed.
        with open(tsp.PERF_LOG, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["date", "regime_signal", "composite_score", "entry_price",
                        "horizon_days", "exit_date", "exit_price", "return_pct"])
            w.writerow([DATES[0], "STRONG_BUY", "4.7", "100.0", 5, DATES[5], "102.0", "1.99"])
        tsp.main()
        log = self._log()
        r5 = log[(DATES[0], 5)]
        self.assertEqual(r5["return_pct"], "1.99")         # preserved
        self.assertEqual(float(r5["mae_pct"]), -4.0)       # backfilled
        self.assertIn((DATES[0], 10), log)                 # new horizons still added
        # Idempotent: a second run changes nothing.
        before = open(tsp.PERF_LOG).read()
        tsp.main()
        self.assertEqual(before, open(tsp.PERF_LOG).read())


if __name__ == "__main__":
    unittest.main()
