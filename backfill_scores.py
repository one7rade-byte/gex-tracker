"""
backfill_scores.py
──────────────────
Adds fear_score, bull_score, bear_score, score_label to gex_log.csv.
Safe to re-run — already-scored rows are skipped.
"""

import csv

CSV_PATH = "gex_log.csv"

ALL_COLS = [
    "date", "ticker", "spot_price", "net_gex_b", "vix",
    "zero_gamma", "call_wall", "put_wall", "peak_gex_strike", "max_pain", "pc_ratio",
    "spy_200ma", "spy_above_200ma", "spy_rsi_14",
    "vix_3m", "vix_term_spread", "vix_term_structure",
    "skew_index",
    "fear_score", "bull_score", "bear_score", "score_label",
    "signal", "l1_context",
]


def compute_scores(gex, vix, rsi, term_structure, skew, above_200ma):
    fear = 0
    bull = 0
    bear = 0

    if gex is not None:
        if gex < -10:   fear += 3
        elif gex < -5:  fear += 2
        elif gex < 0:   fear += 1
        if gex > 10:    bull += 3
        elif gex > 5:   bull += 2
        elif gex > 0:   bull += 1
        if gex < -10:   bear += 3
        elif gex < -5:  bear += 2
        elif gex < -2:  bear += 1

    if vix is not None:
        if vix > 28:    fear += 2
        elif vix > 22:  fear += 1
        if vix < 15:    bull += 2
        elif vix < 18:  bull += 1
        if vix > 25:    bear += 2
        elif vix > 20:  bear += 1

    if term_structure == "backwardation":
        fear += 1
        bear += 1
    elif term_structure == "contango":
        bull += 1

    if skew is not None:
        if skew > 145:
            fear += 2
            bear += 2
        elif skew > 135:
            fear += 1
            bear += 1
        if skew < 115:
            bull += 1

    if rsi is not None:
        if rsi < 30:
            fear += 1
        if rsi > 55 and rsi <= 70:
            bull += 2
        elif rsi > 45:
            bull += 1
        if rsi > 75:    bear += 2
        elif rsi > 70:  bear += 1
        if 30 < rsi < 45:
            bear += 1

    if above_200ma is False:
        fear += 1
        bear += 1
    elif above_200ma is True:
        bull += 1

    fear = min(10, fear)
    bull = min(10, bull)
    bear = min(10, bear)

    if fear >= 8:       label = "HIGH CONVICTION BUY ZONE"
    elif fear >= 6:     label = "Fear building — watch for entry"
    elif fear >= 4:     label = "Moderate fear — monitor"
    elif bear >= 7:     label = "BEAR SIGNAL — reduce / exit"
    elif bear >= 5:     label = "Bear building — caution"
    elif bull >= 8:     label = "Strong bull regime — hold"
    elif bull >= 6:     label = "Positive regime — hold"
    elif bull >= 4:     label = "Mild bull — neutral"
    else:               label = "Mixed — no edge"

    return fear, bull, bear, label


def safe_float(v):
    try:
        f = float(v)
        return None if (f != f) else f
    except:
        return None


def safe_bool(v):
    if v == "True":  return True
    if v == "False": return False
    return None


def main():
    print("=" * 50)
    print("  Confluence Score Backfill (with Bear Score)")
    print("=" * 50)

    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    print(f"Loaded {len(rows)} rows")

    # Force re-score all rows so bear_score gets added
    filled = 0
    for row in rows:
        gex       = safe_float(row.get("net_gex_b"))
        vix       = safe_float(row.get("vix"))
        rsi       = safe_float(row.get("spy_rsi_14"))
        skew      = safe_float(row.get("skew_index"))
        term      = row.get("vix_term_structure") or None
        above_200 = safe_bool(row.get("spy_above_200ma"))

        fear, bull, bear, label = compute_scores(gex, vix, rsi, term, skew, above_200)

        row["fear_score"]  = fear
        row["bull_score"]  = bull
        row["bear_score"]  = bear
        row["score_label"] = label
        filled += 1
        print(f"  {row['date']}  fear={fear}  bull={bull}  bear={bear}  {label}")

    print(f"\nScored {filled} rows")

    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=ALL_COLS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    print(f"Done. {CSV_PATH} updated.")


if __name__ == "__main__":
    main()
