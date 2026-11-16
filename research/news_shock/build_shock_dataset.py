"""
build_shock_dataset.py — event study: when is bad news a buying opportunity?

Finds every stock-specific "shock" drop in current S&P 500 members since
2010, records what kind of event caused it and the context around it, and
measures what happened next. The output is the training/validation data for
the Dip Quality score (score_dip_quality.py / dip_quality_model.json).

Runs in GitHub Actions (news_shock_study.yml, workflow_dispatch). It needs
Yahoo Finance and SEC EDGAR, which are not reachable from Claude's sandbox.

SHOCK DAY (t0): stock close-to-close <= -6%, AND at least 5 points worse than
SPY that day (stock-specific, not just the market), AND volume >= 1.5x its
50-day average. One event per ticker per 20 trading days.

WHAT KIND OF NEWS: historical headline archives aren't free, so the event type
comes from SEC 8-K filings dated t0-1 .. t0+2 (calendar days). A company must
file an 8-K for material events, and the item codes say what kind:
  structural   1.03 bankruptcy, 3.01 delisting, 4.01 auditor change,
               4.02 restatement / non-reliance, 2.06 impairment
  earnings     2.02 results of operations
  leadership   5.02 officer/director departure or appointment
  deal         1.01 / 1.02 / 2.01 material agreement, termination, acquisition
  other_8k     only 7.01 / 8.01 (Reg FD, "other events": often legal/regulatory)
  no_8k        no 8-K at all: downgrades, outages, rumors, sector news, etc.

FEATURES (all known by the close of t0, or t0+3 for the confirmation fields):
  drop_pct, excess_pct, vol_ratio, gap_pct, close_loc (where the close sits in
  the day's range: near the high = buyers absorbed the selling), pre60_pct,
  above_200ma, off_52w_high_pct, spy_20d_pct, spy_above_200ma, vix,
  composite (macro regime score from deep_history_backtest_log.csv),
  rev_yoy_pct (latest quarterly revenue growth filed BEFORE t0, SEC XBRL),
  t3_pct (t0 -> t0+3 return), new_low_3d (undercut the t0 low within 3 days).

OUTCOMES (relative to SPY, from the t0 close and from the t0+3 close):
  ex20/ex60/ex120 and ex60_from_t3, ex120_from_t3; recovered60 (closed back at
  or above the PRE-shock close within 60 days); mdd20 (worst close in the next
  20 days vs t0); rev_yoy_next_pct (the next quarter's revenue growth, filed
  AFTER t0 — a diagnostic of whether fundamentals really changed, never a
  feature).

KNOWN BIAS: uses TODAY's S&P 500 members, so companies that collapsed and
left the index are missing. Recovery rates are biased upward. Comparisons
BETWEEN event types are less affected than the absolute rates.
"""

import csv
import json
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone

import requests

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from market_scanner import fetch_sp500_tickers  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
OUT = os.path.join(HERE, "shock_events.csv")
SUMMARY = os.path.join(HERE, "build_summary.json")

YH = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"}
# SEC asks automated clients to identify themselves. No personal email is sent.
SEC = {"User-Agent": "one7rade-gex-tracker research github.com/one7rade-byte/gex-tracker",
       "Accept-Encoding": "gzip, deflate"}

START = datetime(2009, 1, 1, tzinfo=timezone.utc)
STUDY_FROM = "2010-01-01"
DROP, EXCESS, VOLX, COOLDOWN = -0.06, -0.05, 1.5, 20

STRUCTURAL = {"1.03", "3.01", "4.01", "4.02", "2.06"}
DEAL = {"1.01", "1.02", "2.01"}

stats = {"tickers": 0, "price_ok": 0, "sec_ok": 0, "rev_ok": 0, "events": 0, "sec_errors": 0}


# ── Yahoo ────────────────────────────────────────────────────────────────────
def yahoo_ohlcv(tk):
    out = {}
    p1, now = int(START.timestamp()), int(time.time())
    step = 3 * 365 * 86400
    while p1 < now:
        p2 = min(p1 + step, now)
        for base in ("query1", "query2"):
            try:
                r = requests.get(f"https://{base}.finance.yahoo.com/v8/finance/chart/{tk}"
                                 f"?interval=1d&period1={p1}&period2={p2}", headers=YH, timeout=20)
                res = (r.json().get("chart") or {}).get("result")
                if not res:
                    continue
                q = res[0]["indicators"]["quote"][0]
                for i, t in enumerate(res[0].get("timestamp") or []):
                    vals = [q.get(k, [None])[i] if i < len(q.get(k) or []) else None
                            for k in ("open", "high", "low", "close", "volume")]
                    if vals[3] is None:
                        continue
                    d = datetime.fromtimestamp(t, tz=timezone.utc).date().isoformat()
                    out[d] = vals
                break
            except Exception:
                continue
        p1 = p2
        time.sleep(0.1)
    return [(d,) + tuple(out[d]) for d in sorted(out)]


# ── SEC EDGAR ────────────────────────────────────────────────────────────────
def sec_get(url):
    for i in range(3):
        try:
            r = requests.get(url, headers=SEC, timeout=30)
            time.sleep(0.13)  # SEC fair-access limit is 10 requests/second
            if r.status_code == 200:
                return r.json()
            if r.status_code == 404:
                return None
        except Exception:
            pass
        time.sleep(1 + i)
    stats["sec_errors"] += 1
    return None


def cik_map():
    j = sec_get("https://www.sec.gov/files/company_tickers.json") or {}
    return {v["ticker"].upper().replace(".", "-"): int(v["cik_str"]) for v in j.values()}


def eightk_filings(cik):
    """[(filing_date, items_str)] for every 8-K / 8-K/A on record."""
    j = sec_get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json")
    if not j:
        return None
    blocks = [j.get("filings", {}).get("recent", {})]
    for f in j.get("filings", {}).get("files", []):
        b = sec_get(f"https://data.sec.gov/submissions/{f['name']}")
        if b:
            blocks.append(b)
    out = []
    for b in blocks:
        for form, fd, items in zip(b.get("form", []), b.get("filingDate", []), b.get("items", [])):
            if form in ("8-K", "8-K/A"):
                out.append((fd, items or ""))
    return out


REV_TAGS = ("RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet",
            "RevenueFromContractWithCustomerIncludingAssessedTax")


def quarterly_revenue(cik):
    """[(period_end, filed, value)] for ~3-month periods, merged across tags."""
    q = {}
    for tag in REV_TAGS:
        j = sec_get(f"https://data.sec.gov/api/xbrl/companyconcept/CIK{cik:010d}/us-gaap/{tag}.json")
        if not j:
            continue
        for u in j.get("units", {}).get("USD", []):
            try:
                s, e = date.fromisoformat(u["start"]), date.fromisoformat(u["end"])
            except (KeyError, ValueError):
                continue
            if 80 <= (e - s).days <= 100 and u.get("form") in ("10-Q", "10-K", "10-Q/A", "10-K/A"):
                key = u["end"]
                if key not in q or u["filed"] < q[key][0]:  # first-filed value (no hindsight restatements)
                    q[key] = (u["filed"], u["val"])
    return sorted((e, f, v) for e, (f, v) in q.items())


def rev_yoy(rev, cutoff, after=False):
    """YoY growth of the latest quarter filed before cutoff (or first filed after)."""
    if not rev:
        return None
    cands = [r for r in rev if (r[1] > cutoff if after else r[1] <= cutoff)]
    if not cands:
        return None
    e, _, v = min(cands, key=lambda r: r[1]) if after else max(cands, key=lambda r: r[1])
    ed = date.fromisoformat(e)
    prev = [r for r in rev if abs((date.fromisoformat(r[0]) - (ed - timedelta(days=365))).days) <= 20]
    if not prev or not prev[-1][2]:
        return None
    return round((v / prev[-1][2] - 1) * 100, 2)


def classify(items_list):
    codes = set()
    for it in items_list:
        codes.update(x.strip() for x in it.split(",") if x.strip())
    if codes & STRUCTURAL:
        return "structural", codes
    if "2.02" in codes:
        return "earnings", codes
    if "5.02" in codes:
        return "leadership", codes
    if codes & DEAL:
        return "deal", codes
    if codes:
        return "other_8k", codes
    return "no_8k", codes


# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    limit = int(os.environ.get("SHOCK_LIMIT", "0"))  # for quick test runs
    tickers = fetch_sp500_tickers()
    if limit:
        tickers = tickers[:limit]
    stats["tickers"] = len(tickers)
    print(f"{len(tickers)} tickers")

    spy = yahoo_ohlcv("SPY")
    vix = {r[0]: r[4] for r in yahoo_ohlcv("^VIX")}
    spy_c = {r[0]: r[4] for r in spy}
    spy_dates = [r[0] for r in spy]
    spy_idx = {d: i for i, d in enumerate(spy_dates)}
    comp = {}
    with open(os.path.join(ROOT, "deep_history_backtest_log.csv"), newline="") as fh:
        for r in csv.DictReader(fh):
            comp[r["date"]] = r.get("composite_score")
    ciks = cik_map()
    print(f"SPY {len(spy)} days, VIX {len(vix)}, CIK map {len(ciks)}")

    def spy_ret(d0, d1):
        a, b = spy_c.get(d0), spy_c.get(d1)
        return b / a - 1 if a and b else None

    rows = []
    for n, tk in enumerate(tickers, 1):
        px = yahoo_ohlcv(tk)
        if len(px) < 260:
            continue
        stats["price_ok"] += 1
        D = [p[0] for p in px]
        O, H, L, C, V = ([p[k] for p in px] for k in range(1, 6))
        events, last = [], -999
        for i in range(250, len(px)):
            if D[i] < STUDY_FROM or not C[i - 1] or i - last < COOLDOWN:
                continue
            r = C[i] / C[i - 1] - 1
            s = spy_ret(D[i - 1], D[i]) if D[i - 1] in spy_c else None
            vols = [v for v in V[i - 50:i] if v]
            if s is None or not vols or not V[i]:
                continue
            vr = V[i] / (sum(vols) / len(vols))
            if r <= DROP and r - s <= EXCESS and vr >= VOLX:
                events.append(i)
                last = i
        if not events:
            continue

        cik = ciks.get(tk)
        filings = eightk_filings(cik) if cik else None
        rev = quarterly_revenue(cik) if cik else []
        if filings is not None:
            stats["sec_ok"] += 1
        if rev:
            stats["rev_ok"] += 1

        for i in events:
            d0 = D[i]
            row = {"ticker": tk, "date": d0}
            r = C[i] / C[i - 1] - 1
            s = spy_ret(D[i - 1], d0)
            vols = [v for v in V[i - 50:i] if v]
            ma200 = sum(C[i - 200:i]) / 200
            hi52 = max(C[i - 252:i]) if i >= 252 else max(C[:i])
            si = spy_idx.get(d0)
            row.update({
                "drop_pct": round(r * 100, 2),
                "excess_pct": round((r - s) * 100, 2),
                "spy_day_pct": round(s * 100, 2),
                "vol_ratio": round(V[i] / (sum(vols) / len(vols)), 2),
                "gap_pct": round((O[i] / C[i - 1] - 1) * 100, 2) if O[i] else None,
                "close_loc": round((C[i] - L[i]) / (H[i] - L[i]), 3) if H[i] and L[i] and H[i] > L[i] else None,
                "pre60_pct": round((C[i - 1] / C[i - 61] - 1) * 100, 2),
                "above_200ma": int(C[i - 1] > ma200),
                "off_52w_high_pct": round((C[i - 1] / hi52 - 1) * 100, 2),
                "spy_20d_pct": round((spy_c[d0] / spy_c[spy_dates[si - 20]] - 1) * 100, 2) if si and si >= 20 else None,
                "spy_above_200ma": int(spy_c[d0] > sum(spy_c[x] for x in spy_dates[si - 200:si]) / 200) if si and si >= 200 else None,
                "vix": round(vix[d0], 2) if vix.get(d0) else None,
                "composite": comp.get(d0) or None,
            })
            # SEC event type
            if filings is not None:
                lo = (date.fromisoformat(d0) - timedelta(days=1)).isoformat()
                hi = (date.fromisoformat(d0) + timedelta(days=2)).isoformat()
                cls, codes = classify([it for fd, it in filings if lo <= fd <= hi])
                row["event_type"], row["items"] = cls, " ".join(sorted(codes))
            else:
                row["event_type"], row["items"] = "", ""
            row["rev_yoy_pct"] = rev_yoy(rev, d0)
            row["rev_yoy_next_pct"] = rev_yoy(rev, d0, after=True)
            # Confirmation window (t0 -> t0+3)
            if i + 3 < len(C):
                row["t3_pct"] = round((C[i + 3] / C[i] - 1) * 100, 2)
                row["new_low_3d"] = int(min(L[i + 1:i + 4]) < L[i]) if all(L[i + 1:i + 4]) else None
            # Outcomes
            def ex(a, h):
                if a + h >= len(C):
                    return None
                sr = spy_ret(D[a], D[a + h])
                return round(((C[a + h] / C[a] - 1) - sr) * 100, 2) if sr is not None else None
            row["ex20"], row["ex60"], row["ex120"] = ex(i, 20), ex(i, 60), ex(i, 120)
            row["ex60_from_t3"], row["ex120_from_t3"] = ex(i + 3, 60), ex(i + 3, 120)
            if i + 60 < len(C):
                row["recovered60"] = int(max(C[i + 1:i + 61]) >= C[i - 1])
            if i + 20 < len(C):
                row["mdd20"] = round((min(C[i + 1:i + 21]) / C[i] - 1) * 100, 2)
            rows.append(row)
        stats["events"] = len(rows)
        if n % 25 == 0:
            print(f"  {n}/{len(tickers)} tickers, {len(rows)} events, sec_errors {stats['sec_errors']}")

    fields = ["ticker", "date", "drop_pct", "excess_pct", "spy_day_pct", "vol_ratio", "gap_pct", "close_loc",
              "pre60_pct", "above_200ma", "off_52w_high_pct", "spy_20d_pct", "spy_above_200ma", "vix", "composite",
              "event_type", "items", "rev_yoy_pct", "t3_pct", "new_low_3d",
              "ex20", "ex60", "ex120", "ex60_from_t3", "ex120_from_t3", "recovered60", "mdd20", "rev_yoy_next_pct"]
    rows.sort(key=lambda r: (r["date"], r["ticker"]))
    with open(OUT, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    stats["built_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with open(SUMMARY, "w") as fh:
        json.dump(stats, fh, indent=1)
    print(json.dumps(stats))
    if not rows:
        sys.exit("no events built")


if __name__ == "__main__":
    main()
