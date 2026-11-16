"""
dip_quality.py — is this news-driven drop a buying opportunity or a real
change in the story? Scores stock-specific shock drops 0-100 using weights
learned from 6,000+ historical shocks (research/news_shock/, model in
dip_quality_model.json), validated on 2019+ shocks the model never saw.

What the history says (see research/news_shock/FINDINGS.md):
  - Bad news alone is a coin flip: ~50% of shocks beat SPY over 60 days.
  - Buyable: the market was also weak that day / in a downtrend, the stock
    was already beaten down before the news, the drop happened intraday.
  - Story-changing: a stock-specific overnight gap-down in a calm market
    near highs (typically earnings/guidance news). These kept lagging.

Used by:
  intelligence_engine.py  replaces the old "any negative headline = AVOID" rule for Mag 7
  gex_daily.yml           writes dip_quality.json (Mag 7 + any S&P 500 shock in the last 5 days)
  telegram_notify.py / index.html  show the read
"""

import json
import math
import os
import sys
import time
from datetime import datetime, timezone

import requests

ROOT = os.path.dirname(os.path.abspath(__file__))
MODEL = os.path.join(ROOT, "dip_quality_model.json")
OUT = os.path.join(ROOT, "dip_quality.json")
MAG7 = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA"]
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"}
DROP, EXCESS, VOLX, LOOKBACK = -0.06, -0.05, 1.5, 5  # same shock definition as the study

VERDICTS = {  # band -> (label, tone)
    5: ("BUYABLE NEWS DIP", "green"),
    4: ("LEANS BUYABLE", "green"),
    3: ("NEUTRAL", "gray"),
    2: ("LEANS WEAK", "amber"),
    1: ("WEAK SETUP: WAIT", "red"),
}


def load_model():
    with open(MODEL, encoding="utf-8") as fh:
        return json.load(fh)


def ohlcv(tk, rng="2y"):
    for base in ("query1", "query2"):
        try:
            r = requests.get(f"https://{base}.finance.yahoo.com/v8/finance/chart/{tk}?interval=1d&range={rng}",
                             headers=HEADERS, timeout=20)
            res = r.json()["chart"]["result"][0]
            q = res["indicators"]["quote"][0]
            out = []
            for i, t in enumerate(res["timestamp"]):
                c = q["close"][i]
                if c is None:
                    continue
                out.append((datetime.fromtimestamp(t, tz=timezone.utc).date().isoformat(),
                            q["open"][i], q["high"][i], q["low"][i], c, q["volume"][i]))
            return out
        except Exception:
            continue
    return []


class Market:
    """SPY + VIX history, fetched once and shared across tickers."""

    def __init__(self):
        spy = ohlcv("SPY")
        self.spy = {r[0]: r[4] for r in spy}
        self.dates = [r[0] for r in spy]
        self.idx = {d: i for i, d in enumerate(self.dates)}
        self.vix = {r[0]: r[4] for r in ohlcv("^VIX")}

    def ret(self, d0, d1):
        a, b = self.spy.get(d0), self.spy.get(d1)
        return b / a - 1 if a and b else None


def features(px, i, mkt):
    D = [p[0] for p in px]
    O, H, L, C, V = ([p[k] for p in px] for k in range(1, 6))
    d0 = D[i]
    r = C[i] / C[i - 1] - 1
    s = mkt.ret(D[i - 1], d0)
    vols = [v for v in V[i - 50:i] if v]
    si = mkt.idx.get(d0)
    ma200 = sum(C[i - 200:i]) / 200
    hi52 = max(C[max(0, i - 252):i])
    sd = mkt.dates
    return {
        "drop_pct": r * 100, "excess_pct": (r - s) * 100 if s is not None else None,
        "spy_day_pct": s * 100 if s is not None else None,
        "vol_ratio": V[i] / (sum(vols) / len(vols)) if vols and V[i] else None,
        "gap_pct": (O[i] / C[i - 1] - 1) * 100 if O[i] else None,
        "close_loc": (C[i] - L[i]) / (H[i] - L[i]) if H[i] and L[i] and H[i] > L[i] else None,
        "pre60_pct": (C[i - 1] / C[i - 61] - 1) * 100,
        "above_200ma": int(C[i - 1] > ma200),
        "off_52w_high_pct": (C[i - 1] / hi52 - 1) * 100,
        "spy_20d_pct": (mkt.spy[d0] / mkt.spy[sd[si - 20]] - 1) * 100 if si and si >= 20 else None,
        "spy_above_200ma": int(mkt.spy[d0] > sum(mkt.spy[x] for x in sd[si - 200:si]) / 200) if si and si >= 200 else None,
        "vix": mkt.vix.get(d0),
    }


def score(feat, model, which="t0"):
    m = model[which]
    z = m["intercept"]
    for f, mu, sd, c in zip(m["features"], m["mean"], m["std"], m["coef"]):
        v = feat.get(f)
        if v is None:
            v = m["median_fill"][f]
        lo_hi = model.get("clip", {}).get(f)
        if lo_hi:
            v = min(max(v, lo_hi[0]), lo_hi[1])
        z += c * (v - mu) / sd
    p = 1 / (1 + math.exp(-z))
    band = 1 + sum(p > c for c in m["band_cuts"])
    hist = next((b for b in m["test_by_band"] if b["band"] == band), {})
    return round(p * 100), band, hist


def reasons(f):
    """Plain-English drivers, from the patterns that held up in the study."""
    out = []
    mkt_weak = (f.get("spy_day_pct") is not None and f["spy_day_pct"] <= -1.0) or f.get("spy_above_200ma") == 0
    beaten = f["pre60_pct"] <= -10 or f["off_52w_high_pct"] <= -25
    gap = f.get("gap_pct")
    if mkt_weak:
        out.append(("+", "Market was also weak, so part of the drop isn't about the company"))
    if beaten:
        out.append(("+", f"Stock was already beaten down before the news ({f['pre60_pct']:+.0f}% over 60 days, {f['off_52w_high_pct']:.0f}% off its high)"))
    if not mkt_weak and not beaten and gap is not None and gap <= -5:
        out.append(("−", f"Overnight gap of {gap:.0f}% on company news in a calm market near highs: the pattern where bad news kept drifting lower"))
    elif gap is not None and gap > -2:
        out.append(("+", "Most of the drop happened during the day, not as an overnight gap"))
    if f.get("vol_ratio") and f["vol_ratio"] >= 5:
        out.append(("·", f"Very heavy volume ({f['vol_ratio']:.1f}x normal)"))
    if not out:
        out.append(("·", "No strong pattern either way"))
    return out


def scan(tk, mkt, model, px=None):
    """Latest shock in the last LOOKBACK sessions, scored; else a status row."""
    px = px or ohlcv(tk)
    if len(px) < 262:
        return {"ticker": tk, "status": "no_data"}
    C, V = [p[4] for p in px], [p[5] for p in px]
    last = px[-1]
    day_chg = (C[-1] / C[-2] - 1) * 100
    five = (C[-1] / C[-1 - LOOKBACK] - 1) * 100
    for i in range(len(px) - 1, len(px) - 1 - LOOKBACK, -1):
        r = C[i] / C[i - 1] - 1
        s = mkt.ret(px[i - 1][0], px[i][0])
        vols = [v for v in V[i - 50:i] if v]
        if s is None or not vols or not V[i]:
            continue
        if r <= DROP and r - s <= EXCESS and V[i] / (sum(vols) / len(vols)) >= VOLX:
            f = features(px, i, mkt)
            sc, band, hist = score(f, model)
            label, tone = VERDICTS[band]
            if tk in MAG7 and model.get("mag7"):
                # The score doesn't rank Mag 7 shocks; use their own track record.
                mg = model["mag7"]
                label, tone = "MAG 7 NEWS DIP: HISTORICALLY BUYABLE", "green"
                hist = {"beat_spy_pct": mg["beat_spy_60d_pct"], "median_excess_pct": mg["median_excess_60d_pct"]}
            return {
                "ticker": tk, "status": "shock", "shock_date": px[i][0], "date": last[0],
                "drop_pct": round(f["drop_pct"], 1), "excess_pct": round(f["excess_pct"], 1),
                "since_shock_pct": round((C[-1] / C[i] - 1) * 100, 1),
                "score": sc, "band": band, "verdict": label, "tone": tone,
                "hist_beat_spy_pct": hist.get("beat_spy_pct"), "hist_median_excess_pct": hist.get("median_excess_pct"),
                "reasons": [{"sign": s_, "text": t} for s_, t in reasons(f)],
                "features": {k: (round(v, 3) if isinstance(v, float) else v) for k, v in f.items()},
            }
    return {"ticker": tk, "status": "no_shock", "date": last[0],
            "day_pct": round(day_chg, 1), "five_day_pct": round(five, 1)}


def headline_read(tk, news_dominant, dq):
    """Decision text for intelligence_engine: weigh the headline against the price evidence."""
    if dq.get("status") == "shock" and tk in MAG7:
        return (f"{tk} {dq['verdict']}: down {dq['drop_pct']}% on {dq['shock_date']}. "
                f"Past Mag 7 news drops beat SPY over 60 days {dq['hist_beat_spy_pct']}% of the time "
                f"(median {dq['hist_median_excess_pct']:+}%). Not a reason to avoid on its own; wait for Quick Action confirmations to add.")
    if dq.get("status") == "shock":
        return (f"{tk} {dq['verdict']}: down {dq['drop_pct']}% on {dq['shock_date']} "
                f"(Dip Quality {dq['score']}/100; this band beat SPY over 60 days "
                f"{dq['hist_beat_spy_pct']}% of the time historically). {dq['reasons'][0]['text']}.")
    if dq.get("status") == "no_shock" and news_dominant == "company_negative" and (dq.get("five_day_pct") or 0) <= -5:
        tail = ""
        if tk in MAG7:
            try:
                mg = load_model()["mag7"]
                tail = (f" Past Mag 7 news drops beat SPY over 60 days {mg['beat_spy_60d_pct']}% of the time "
                        f"(median {mg['median_excess_60d_pct']:+}%).")
            except Exception:
                pass
        return (f"{tk} NEWS-DRIVEN SLIDE: down {dq['five_day_pct']:.1f}% over 5 days across several sessions "
                f"(no single shock day, so the shock score doesn't apply).{tail} Not a reason to avoid on its own; "
                f"wait for Quick Action confirmations to add.")
    if dq.get("status") == "no_shock" and news_dominant == "company_negative":
        return (f"{tk} HEADLINE NOISE: negative headlines, but the stock moved only {dq['five_day_pct']:+.1f}% "
                f"over 5 days. That's no shock-sized reaction, so not a reason to avoid on its own.")
    return None


def main():
    model = load_model()
    mkt = Market()
    universe = list(MAG7)
    if "--mag7-only" not in sys.argv:
        try:
            from market_scanner import fetch_sp500_tickers
            universe += [t for t in fetch_sp500_tickers() if t not in universe]
        except Exception as e:
            print(f"  S&P list unavailable ({e}); Mag 7 only")
    rows = []
    for n, tk in enumerate(universe, 1):
        rows.append(scan(tk, mkt, model))
        time.sleep(0.05)
        if n % 100 == 0:
            print(f"  {n}/{len(universe)}")
    mag7 = {r["ticker"]: r for r in rows if r["ticker"] in MAG7}
    shocks = sorted([r for r in rows if r.get("status") == "shock" and r["ticker"] not in MAG7],
                    key=lambda r: -r["score"])
    date = max((r.get("date") or "" for r in rows), default="")
    out = {"date": date, "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "model_built_at": model.get("built_at"), "model_test_auc": model["t0"]["auc_test"],
           "lookback_sessions": LOOKBACK, "mag7": mag7, "sp500_shocks": shocks,
           "note": "Dip Quality ranks news-driven drops by how similar past drops behaved. "
                   "It is a modest edge (top band beat SPY ~55% vs ~39% for the bottom band, 2019+ out of sample), not a guarantee."}
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1)
    print(f"{date}: scanned {len(rows)}, Mag 7 shocks {sum(1 for r in mag7.values() if r.get('status') == 'shock')}, "
          f"S&P shocks {len(shocks)}")
    for r in list(mag7.values()) + shocks[:10]:
        if r.get("status") == "shock":
            print(f"  {r['ticker']}: {r['verdict']} {r['score']}/100 ({r['drop_pct']}% on {r['shock_date']})")


def telegram_lines(max_items=4):
    """Plain text for the Telegram summary; empty string when nothing to report."""
    try:
        with open(OUT, encoding="utf-8") as fh:
            d = json.load(fh)
    except (OSError, ValueError):
        return ""
    items = [r for r in d.get("mag7", {}).values() if r.get("status") == "shock"] + d.get("sp500_shocks", [])
    if not items:
        return ""
    icon = {"green": "🟢", "gray": "⚪", "amber": "🟡", "red": "🔴"}
    lines = ["NEWS DIPS (Dip Quality, 0-100):"]
    for r in items[:max_items]:
        lines.append(f"{icon.get(r['tone'], '⚪')} {r['ticker']} {r['score']}/100 {r['verdict']}: "
                     f"{r['drop_pct']}% on {r['shock_date']}")
    return "\n".join(lines).replace("*", "").replace("_", " ").replace("`", "")


if __name__ == "__main__":
    main()
