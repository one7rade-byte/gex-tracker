"""
backfill_scores.py
──────────────────
One-time script to add fear_score, bull_score, score_label
to every existing row in gex_log.csv.

Run once via GitHub Actions workflow_dispatch.
Safe to re-run — already-scored rows are skipped.
"""

import csv
import os

CSV_PATH = "gex_log.csv"

ALL_COLS = [
    "date", "ticker", "spot_price", "net_gex_b", "vix",
    "zero_gamma", "call_wall", "put_wall", "peak_gex_strike", "max_pain", "pc_ratio",
    "spy_200ma", "spy_above_200ma", "spy_rsi_14",
    "vix_3m", "vix_term_spread", "vix_term_structure",
    "skew_index",
    "fear_score", "bull_score", "score_label",
    "signal", "l1_context",
]


def compute_scores(gex, vix, rsi, term_structure, skew, above_200ma):
    fear = 0
    bull = 0

    if gex is not None:
        if gex < -10:   fear += 3
        elif gex < -5:  fear += 2
        elif gex < 0:   fear += 1
        if gex > 10:    bull += 3
        elif gex > 5:   bull += 2
        elif gex > 0:   bull += 1

    if vix is not None:
        if vix > 28:    fear += 2
        elif vix > 22:  fear += 1
        if vix < 15:    bull += 2
        elif vix < 18:  bull += 1

    if term_structure == "backwardation":
        fear += 1
    elif term_structure == "contango":
        bull += 1

    if skew is not None:
        if skew > 145:   fear += 2
        elif skew > 135: fear += 1
        if skew < 115:   bull += 1

    if rsi is not None:
        if rsi < 30:             fear += 1
        if rsi > 55 and rsi <= 70: bull += 2
        elif rsi > 45:           bull += 1

    if above_200ma is False:
        fear += 1
    elif above_200ma is True:
        bull += 1

    fear = min(10, fear)
    bull = min(10, bull)

    if fear >= 8:       label = "HIGH CONVICTION BUY ZONE"
    elif fear >= 6:     label = "Fear building — watch for entry"
    elif fear >= 4:     label = "Moderate fear — monitor"
    elif bull >= 8:     label = "Strong bull regime — hold"
    elif bull >= 6:     label = "Positive regime — hold"
    elif bull >= 4:     label = "Mild bull — neutral"
    else:               label = "Mixed — no edge"

    return fear, bull, label


def safe_float(v):
    try:
        f = float(v)
        return None if (f != f) else f  # NaN check
    except:
        return None


def safe_bool(v):
    if v == "True":  return True
    if v == "False": return False
    return None


def main():
    print("=" * 50)
    print("  Confluence Score Backfill")
    print("=" * 50)

    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    print(f"Loaded {len(rows)} rows")

    already = sum(1 for r in rows if r.get("fear_score") not in (None, ""))
    print(f"Already scored: {already}")
    if already == len(rows):
        print("All rows already scored. Nothing to do.")
        return

    filled = 0
    for row in rows:
        if row.get("fear_score") not in (None, ""):
            continue

        gex       = safe_float(row.get("net_gex_b"))
        vix       = safe_float(row.get("vix"))
        rsi       = safe_float(row.get("spy_rsi_14"))
        skew      = safe_float(row.get("skew_index"))
        term      = row.get("vix_term_structure") or None
        above_200 = safe_bool(row.get("spy_above_200ma"))

        fear, bull, label = compute_scores(gex, vix, rsi, term, skew, above_200)

        row["fear_score"]  = fear
        row["bull_score"]  = bull
        row["score_label"] = label
        filled += 1

    print(f"Scored {filled} rows")

    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=ALL_COLS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    print(f"Done. {CSV_PATH} updated.")


if __name__ == "__main__":
    main()
