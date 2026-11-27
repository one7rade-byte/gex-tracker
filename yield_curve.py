"""
yield_curve.py — 2-year / 10-year Treasury curve regime.

Data: FRED daily constant-maturity yields DGS2, DGS10, DGS3MO (free, no key,
1976+ for 2y). Writes yield_curve.csv (date, y3m, y2, y10, spread_10_2,
spread_10_3m, and the regime over the last 20 trading days).

Regime (20-session change; "moving" = the 10y-2y spread changed 10bp+):
  BULL STEEPENER   yields falling, 2y falls faster: the market expects Fed cuts
  BULL FLATTENER   yields falling, 10y falls faster: growth fears, flight to safety
  BEAR STEEPENER   yields rising, 10y rises faster: inflation / fiscal / term-premium worry
  BEAR FLATTENER   yields rising, 2y rises faster: the Fed is actively tightening
  (TWIST / FLAT when yields move in opposite directions or the spread barely moves)
"Yields falling/rising" uses the average of the 2y and 10y changes.

Runs daily in gex_daily.yml. Fails soft: if FRED is unreachable the old file
is kept.
"""
import csv
import io
import os
import sys

import requests

OUT = "yield_curve.csv"
SERIES = {"y3m": "DGS3MO", "y2": "DGS2", "y10": "DGS10"}
WIN, MOVE = 20, 0.10  # sessions, percentage points (10bp)


def fetch(sid):
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
    r = requests.get(url, timeout=60, headers={"User-Agent": "Mozilla/5.0 gex-tracker"})
    r.raise_for_status()
    out = {}
    for row in csv.reader(io.StringIO(r.text)):
        if len(row) < 2 or row[0][:2] not in ("19", "20"):
            continue
        try:
            out[row[0]] = float(row[1])
        except ValueError:
            pass  # FRED uses "." for holidays
    return out


def regime(d2, d10):
    level = (d2 + d10) / 2
    dspread = d10 - d2
    if abs(dspread) < MOVE:
        return "FLAT"
    if d2 < 0 and d10 < 0:
        return "BULL STEEPENER" if dspread > 0 else "BULL FLATTENER"
    if d2 > 0 and d10 > 0:
        return "BEAR STEEPENER" if dspread > 0 else "BEAR FLATTENER"
    # opposite directions: name it by the overall level move
    if level < 0:
        return "BULL STEEPENER" if dspread > 0 else "BULL FLATTENER"
    return "BEAR STEEPENER" if dspread > 0 else "BEAR FLATTENER"


def main():
    try:
        data = {k: fetch(v) for k, v in SERIES.items()}
    except Exception as e:
        print(f"FRED unavailable ({e}); keeping existing {OUT}")
        sys.exit(0 if os.path.exists(OUT) else 1)
    dates = sorted(d for d in data["y2"] if d in data["y10"])
    rows = []
    for i, d in enumerate(dates):
        y2, y10 = data["y2"][d], data["y10"][d]
        y3m = data["y3m"].get(d)
        row = {"date": d, "y3m": y3m, "y2": y2, "y10": y10,
               "spread_10_2": round(y10 - y2, 3), "spread_10_3m": round(y10 - y3m, 3) if y3m is not None else None}
        if i >= WIN:
            p = dates[i - WIN]
            d2, d10 = y2 - data["y2"][p], y10 - data["y10"][p]
            row.update({"chg2_20d": round(d2, 3), "chg10_20d": round(d10, 3),
                        "spread_chg_20d": round(d10 - d2, 3), "regime": regime(d2, d10)})
        rows.append(row)
    fields = ["date", "y3m", "y2", "y10", "spread_10_2", "spread_10_3m", "chg2_20d", "chg10_20d", "spread_chg_20d", "regime"]
    with open(OUT, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    last = rows[-1]
    print(f"Wrote {OUT}: {len(rows)} rows {rows[0]['date']} -> {last['date']} | 2y {last['y2']} 10y {last['y10']} "
          f"spread {last['spread_10_2']} | {last.get('regime')}")


if __name__ == "__main__":
    main()
