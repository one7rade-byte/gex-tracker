"""
backtest_signals.py
─────────────────────
Tests the documented GEX/VIX entry & exit rules against real accumulated
history in gex_log.csv, to see whether they actually identified good
entries historically, or whether the thresholds need adjusting.

Documented rules being tested (from project notes):
  ENTER: VIX 25-28 + deeply negative GEX + price holding above structural
         low (no new low on the most recent negative-GEX day)
  HOLD:  GEX positive + VIX falling or stable
  EXIT:  GEX flips negative + VIX rising simultaneously
  NOISE: negative GEX with low VIX -> treat as weekly expiry noise, ignore

For each day a rule condition fires, this looks forward N trading days
(5, 10, 20) and reports what SPY actually did — giving a rough, low-N
sanity check rather than a statistically rigorous backtest. With only
~54 days of history, treat results as directional signal, not proof.
"""

import csv
from datetime import datetime

INPUT_CSV = "gex_log.csv"
LOOKAHEAD_DAYS = [5, 10, 20]


def load_data():
    with open(INPUT_CSV, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    rows.sort(key=lambda r: r["date"])

    clean = []
    for r in rows:
        try:
            clean.append({
                "date": r["date"],
                "spot": float(r["spot_price"]),
                "gex": float(r["net_gex_b"]) if r.get("net_gex_b") else None,
                "vix": float(r["vix"]) if r.get("vix") else None,
            })
        except (ValueError, KeyError):
            continue
    return clean


def forward_return(data, idx, days):
    """% change in spot price `days` trading days after index `idx`."""
    target = idx + days
    if target >= len(data):
        return None
    start = data[idx]["spot"]
    end = data[target]["spot"]
    if start == 0:
        return None
    return round((end - start) / start * 100, 2)


def test_enter_rule(data):
    """
    ENTER: VIX 25-28 + deeply negative GEX (< -3) + price not making a new
    low vs the prior day. Reports forward returns at each lookahead.
    """
    print("\n" + "=" * 70)
    print("ENTER RULE: VIX 25-28 + GEX < -3B + no new low vs prior day")
    print("=" * 70)

    hits = []
    for i in range(1, len(data)):
        d = data[i]
        prev = data[i - 1]
        if d["vix"] is None or d["gex"] is None:
            continue
        vix_in_range = 25 <= d["vix"] <= 28
        gex_deeply_neg = d["gex"] < -3
        no_new_low = d["spot"] >= prev["spot"]

        if vix_in_range and gex_deeply_neg and no_new_low:
            hits.append(i)

    if not hits:
        print("No days matched all 3 conditions simultaneously in this dataset.")
        return

    print(f"Found {len(hits)} matching day(s): {[data[i]['date'] for i in hits]}\n")
    for i in hits:
        d = data[i]
        print(f"  {d['date']}  spot=${d['spot']:.2f}  VIX={d['vix']:.2f}  GEX={d['gex']:.2f}B")
        for days in LOOKAHEAD_DAYS:
            ret = forward_return(data, i, days)
            ret_str = f"{ret:+.2f}%" if ret is not None else "n/a (not enough future data)"
            print(f"    +{days}d: {ret_str}")


def test_exit_rule(data):
    """
    EXIT: GEX flips negative AND VIX rising vs prior day, simultaneously.
    Reports forward returns — if the rule works, we'd expect negative or
    flat forward returns (the rule should catch declines before they happen).
    """
    print("\n" + "=" * 70)
    print("EXIT RULE: GEX flips negative + VIX rising vs prior day")
    print("=" * 70)

    hits = []
    for i in range(1, len(data)):
        d = data[i]
        prev = data[i - 1]
        if d["vix"] is None or d["gex"] is None or prev["gex"] is None or prev["vix"] is None:
            continue
        gex_flipped_negative = prev["gex"] >= 0 and d["gex"] < 0
        vix_rising = d["vix"] > prev["vix"]

        if gex_flipped_negative and vix_rising:
            hits.append(i)

    if not hits:
        print("No days matched both conditions simultaneously in this dataset.")
        return

    print(f"Found {len(hits)} matching day(s): {[data[i]['date'] for i in hits]}\n")
    for i in hits:
        d = data[i]
        print(f"  {d['date']}  spot=${d['spot']:.2f}  VIX={d['vix']:.2f}  GEX={d['gex']:.2f}B")
        for days in LOOKAHEAD_DAYS:
            ret = forward_return(data, i, days)
            ret_str = f"{ret:+.2f}%" if ret is not None else "n/a (not enough future data)"
            print(f"    +{days}d: {ret_str}")


def test_noise_filter(data):
    """
    NOISE: negative GEX with low VIX (<19) — documented as something to
    ignore (weekly expiry noise, not a real regime change). Checks whether
    these days actually behaved like noise (small forward moves) or
    whether some of them were real signals being incorrectly filtered out.
    """
    print("\n" + "=" * 70)
    print("NOISE FILTER CHECK: negative GEX + VIX < 19 (should be low-impact)")
    print("=" * 70)

    hits = []
    for i in range(len(data)):
        d = data[i]
        if d["vix"] is None or d["gex"] is None:
            continue
        if d["gex"] < 0 and d["vix"] < 19:
            hits.append(i)

    if not hits:
        print("No days matched in this dataset.")
        return

    print(f"Found {len(hits)} matching day(s)\n")
    returns_5d = []
    for i in hits:
        ret = forward_return(data, i, 5)
        if ret is not None:
            returns_5d.append(ret)
        d = data[i]
        ret_str = f"{ret:+.2f}%" if ret is not None else "n/a"
        print(f"  {d['date']}  spot=${d['spot']:.2f}  VIX={d['vix']:.2f}  GEX={d['gex']:.2f}B  -> +5d: {ret_str}")

    if returns_5d:
        avg = sum(returns_5d) / len(returns_5d)
        max_move = max(returns_5d, key=abs)
        print(f"\n  Average +5d return on 'noise' days: {avg:+.2f}%")
        print(f"  Largest +5d move on a 'noise' day:   {max_move:+.2f}%")
        if abs(max_move) > 3:
            print("  -> At least one 'noise' day preceded a >3% move. Worth reviewing"
                  " whether the noise filter occasionally suppresses real signals.")


def main():
    data = load_data()
    print(f"Loaded {len(data)} days of history: {data[0]['date']} to {data[-1]['date']}")
    print("NOTE: with only ~50 days of data, treat all results below as")
    print("directional / exploratory, not statistically significant.")

    test_enter_rule(data)
    test_exit_rule(data)
    test_noise_filter(data)


if __name__ == "__main__":
    main()
