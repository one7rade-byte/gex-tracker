"""
regime_analyzer.py
==================
Daily macro regime scoring and black swan detection.
Reads macro_history.csv + gex_log.csv, computes composite scores,
detects regime changes, and appends results to regime_log.csv.

Run after gex_tracker.py completes each day.

Composite score: -8 to +8
  +6 to +8 = strong bull       → hold and accumulate
  +3 to +5 = mild bull         → hold
   0 to +2 = neutral/caution   → reduce new positions
  -1 to -3 = stress building   → defensive positioning
  -4 to -8 = crisis            → maximum defense, wait for HYG to stabilize

Black swan watch triggers when 3+ early warning signals fire simultaneously.
"""

import csv
import os
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# ── Config ────────────────────────────────────────────────────────────────────
MACRO_CSV   = "macro_history.csv"
GEX_CSV     = "gex_log.csv"
REGIME_CSV  = "regime_log.csv"

REGIME_CSV_HEADERS = [
    "date",
    # Raw inputs
    "vix", "vix9d", "vix9d_ratio", "yield10y",
    "gold", "dxy", "tlt", "hyg", "copper", "oil", "eem", "xlre", "skew",
    "gex_b", "spy_rsi",
    # Computed scores
    "credit_score",       # 0-3: HYG-based credit health
    "vol_score",          # 0-3: VIX-based volatility regime
    "flow_score",         # 0-2: DXY/Gold flow signal
    "growth_score",       # 0-2: Copper/EEM global growth
    "skew_score",         # -1 to +1: SKEW contrarian signal
    "composite_score",    # -8 to +8: weighted total
    "flow_regime",        # plain-English regime label
    # Change signals
    "hyg_5d_change",      # HYG change over 5 days — early warning
    "vix_term_signal",    # contango/backwardation
    "skew_signal",        # panic_buy/normal/warning/black_swan_watch
    "gex_signal",         # positive/negative/deeply_negative
    # Combined signal
    "regime_signal",      # STRONG_BUY/BUY_WATCH/HOLD/CAUTION/DEFENSIVE/CRISIS
    "black_swan_watch",   # True/False
    "black_swan_reasons", # pipe-separated list of warning signals
    "brief",              # one-sentence plain English summary
]


# ── Scoring functions ─────────────────────────────────────────────────────────

def score_credit(hyg):
    """HYG-based credit health. Most important single indicator."""
    if hyg is None: return 1  # neutral if missing
    if hyg > 82:  return 3   # very healthy
    if hyg > 79:  return 2   # healthy
    if hyg > 76:  return 1   # mild stress
    if hyg > 72:  return 0   # real stress
    if hyg > 68:  return -2  # credit crisis brewing
    return -3                 # full credit crisis


def score_volatility(vix, vix9d, term_spread):
    """VIX-based volatility regime."""
    if vix is None: return 1
    s = 0
    if vix < 14:   s = 3
    elif vix < 17: s = 2
    elif vix < 20: s = 1
    elif vix < 25: s = 0
    elif vix < 30: s = -1
    elif vix < 40: s = -2
    else:          s = -3

    # VIX9D ratio modifier
    if vix9d and vix and vix > 0:
        ratio = vix9d / vix
        if ratio > 1.15:  s -= 1  # near-term fear spike
        elif ratio < 0.85: s += 1  # near-term calm

    # Term structure modifier
    if term_spread is not None:
        if term_spread < 0:   s -= 1  # backwardation = stress
        elif term_spread > 3: s += 1  # deep contango = calm

    return max(-3, min(3, s))


def score_flow(dxy, gold, tlt):
    """Dollar/Gold/Bond flow signal."""
    if dxy is None: return 0
    s = 0
    # DXY
    if dxy > 106:   s -= 2   # extreme dollar strength = cash hoarding/crisis
    elif dxy > 103: s -= 1   # mild dollar strength
    elif dxy < 100: s += 1   # dollar weakness = risk on
    elif dxy < 97:  s += 2   # strong dollar weakness = risk on

    # Gold confirmation
    if gold and dxy:
        if dxy > 103 and gold < 350: s -= 1  # DXY up, gold down = panic cash hoarding
        if dxy < 100 and gold > 380: s += 1  # DXY down, gold up = inflation/risk on

    return max(-2, min(2, s))


def score_growth(copper, eem):
    """Global growth proxy via copper and emerging markets."""
    s = 0
    if copper:
        if copper > 38:   s += 2
        elif copper > 30: s += 1
        elif copper < 22: s -= 1
        elif copper < 18: s -= 2

    if eem:
        if eem > 55:   s += 1
        elif eem < 36: s -= 1

    return max(-2, min(2, s))


def score_skew(skew, vix):
    """
    SKEW contrarian signal.
    Key finding: High SKEW during selloff = panic hedging = buy signal.
    Low SKEW during prolonged decline = structural bear = stay out.
    """
    if skew is None or vix is None: return 0
    if skew > 148 and vix > 20:
        return 1    # panic hedging during selloff = contrarian buy
    if skew < 120 and vix > 25:
        return -1   # low hedging during stress = structural bear
    return 0


def compute_composite(credit, vol, flow, growth, skew_s):
    """Weighted composite score."""
    # Credit is most important (weight 3x)
    # Vol is second (weight 2x)
    # Others equal weight
    raw = (credit * 1.5) + (vol * 1.2) + flow + growth + skew_s
    return round(max(-8, min(8, raw)), 1)


def get_flow_regime(composite, hyg, dxy, vix):
    """Plain English regime label."""
    if hyg and hyg < 68:          return "credit_crisis"
    if composite >= 6:             return "risk_on"
    if composite >= 3:             return "mild_risk_on"
    if composite >= 0:
        if dxy and dxy > 104:     return "cash_hoarding"
        return "neutral"
    if composite >= -2:
        if dxy and dxy > 104:     return "cash_hoarding"
        if vix and vix > 25:      return "recession_fear"
        return "mild_risk_off"
    if composite >= -5:            return "recession_fear"
    return "risk_off"


def get_regime_signal(composite, hyg, gex, rsi, skew, vix):
    """
    Final combined signal combining macro regime + GEX + RSI + SKEW.
    """
    # Crisis override
    if hyg and hyg < 68:
        return "CRISIS"

    # Defensive zone
    if composite <= -3 or (hyg and hyg < 74):
        return "DEFENSIVE"

    # Strong buy: macro healthy + GEX deeply negative + oversold + panic hedging
    if (composite >= 1 and
        gex is not None and gex < -10 and
        rsi is not None and rsi < 50 and
        skew is not None and skew > 138 and
        vix is not None and vix > 17):
        return "STRONG_BUY"

    # Buy watch: macro OK + negative GEX + RSI not overbought
    if (composite >= 0 and
        gex is not None and gex < -5 and
        rsi is not None and rsi < 57):
        return "BUY_WATCH"

    # Overbought caution: negative GEX but RSI elevated
    if gex is not None and gex < 0 and rsi is not None and rsi > 70:
        return "CAUTION"

    # Caution: macro score declining
    if composite <= -1:
        return "CAUTION"

    # Normal hold
    if composite >= 3:
        return "HOLD"

    return "HOLD"


def detect_black_swan(today_row, history_rows):
    """
    Black swan early warning — detects the Jan 2022 pattern:
    institutions buying massive protection while market still near highs.

    Triggers when 3+ early warning signals fire simultaneously.
    Returns (is_watch, reasons_list)
    """
    warnings = []

    hyg = today_row.get('hyg')
    skew = today_row.get('skew')
    vix = today_row.get('vix')
    dxy = today_row.get('dxy')
    composite = today_row.get('composite_score', 0)
    vix_term = today_row.get('vix_term_signal')
    hyg_5d = today_row.get('hyg_5d_change')

    # Signal 1: SKEW extremely elevated while VIX still low (smart money hedging quietly)
    if skew and vix and skew > 150 and vix < 20:
        warnings.append(f"SKEW {skew:.0f} elevated while VIX {vix:.1f} low — institutions hedging before move")

    # Signal 2: HYG weakening meaningfully over 5 days
    if hyg_5d is not None and hyg_5d < -1.5:
        warnings.append(f"HYG dropped ${abs(hyg_5d):.2f} in 5 days — credit slowly weakening")

    # Signal 3: VIX term structure flipping to backwardation
    if vix_term == 'backwardation':
        warnings.append("VIX term structure in backwardation — near-term fear exceeding long-term")

    # Signal 4: Composite score dropping fast
    if len(history_rows) >= 10:
        old_score = float(history_rows[-10].get('composite_score', 0) or 0)
        curr_score = float(composite or 0)
        if curr_score - old_score <= -3:
            warnings.append(f"Composite score dropped {curr_score-old_score:+.0f} in 10 days — rapid regime deterioration")

    # Signal 5: DXY rising while stocks still near highs (pre-crash dollar bid)
    if dxy and dxy > 105 and composite >= 2:
        warnings.append(f"DXY {dxy:.2f} elevated while macro still positive — dollar bid in bull market")

    # Signal 6: HYG below 76 (meaningful credit stress)
    if hyg and hyg < 76:
        warnings.append(f"HYG ${hyg:.2f} below $76 — credit stress building")

    is_watch = len(warnings) >= 3
    return is_watch, warnings


def get_brief(signal, composite, hyg, vix, gex, skew, flow_regime, bs_watch):
    """One-sentence plain English summary."""
    if bs_watch:
        return f"⚠️ BLACK SWAN WATCH — multiple early warning signals active. Review positions and tighten stops."
    if signal == "CRISIS":
        return f"CREDIT CRISIS — HYG ${hyg:.2f} in stress zone. Reduce all long exposure and wait for credit to stabilize."
    if signal == "STRONG_BUY":
        return f"Strong buy setup — macro healthy (HYG ${hyg:.2f}), GEX {gex:.1f}B deeply negative, RSI oversold, SKEW {skew:.0f} shows panic hedging. Best entry conditions."
    if signal == "BUY_WATCH":
        return f"Buy watch — setup building. GEX negative with healthy credit (HYG ${hyg:.2f}). Scale in cautiously."
    if signal == "DEFENSIVE":
        return f"Defensive positioning — HYG ${hyg:.2f} showing credit stress. No new longs until HYG recovers above $76."
    if signal == "CAUTION":
        return f"Caution — composite score {composite:+.1f}, VIX {vix:.1f}. Reduce new positions, tighten stops."
    if composite >= 5:
        return f"Maximum bull regime — composite {composite:+.1f}, HYG ${hyg:.2f} healthy. Hold all positions."
    return f"Positive regime — composite {composite:+.1f}, HYG ${hyg:.2f}, VIX {vix:.1f}. Hold existing positions."


# ── Data loading ──────────────────────────────────────────────────────────────

def load_macro_history():
    if not os.path.exists(MACRO_CSV):
        print(f"  {MACRO_CSV} not found")
        return []
    with open(MACRO_CSV, newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def load_gex_latest():
    """Load the most recent SPY row from gex_log.csv."""
    if not os.path.exists(GEX_CSV):
        return None
    with open(GEX_CSV, newline='', encoding='utf-8') as f:
        rows = [r for r in csv.DictReader(f) if r.get('ticker','').strip() == 'SPY']
    return rows[-1] if rows else None


def load_regime_history():
    if not os.path.exists(REGIME_CSV):
        return []
    with open(REGIME_CSV, newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def save_regime_row(row):
    exists = os.path.exists(REGIME_CSV)
    # Remove existing row for same date then append
    if exists:
        with open(REGIME_CSV, newline='', encoding='utf-8') as f:
            existing = list(csv.DictReader(f))
        existing = [r for r in existing if r.get('date') != row['date']]
        existing.append(row)
        with open(REGIME_CSV, 'w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=REGIME_CSV_HEADERS, extrasaction='ignore')
            w.writeheader()
            w.writerows(existing)
    else:
        with open(REGIME_CSV, 'w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=REGIME_CSV_HEADERS, extrasaction='ignore')
            w.writeheader()
            w.writerow(row)
    print(f"  Saved regime row for {row['date']}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    today = datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")
    print("=" * 60)
    print(f"  Regime Analyzer  |  {today}")
    print("=" * 60)

    # Load data
    macro_hist = load_macro_history()
    gex_row    = load_gex_latest()
    regime_hist = load_regime_history()

    print(f"\n  Macro history: {len(macro_hist)} rows")
    print(f"  GEX latest: {gex_row.get('date') if gex_row else 'none'}")
    print(f"  Regime history: {len(regime_hist)} rows")

    if not gex_row:
        print("  No GEX data — run gex_tracker.py first")
        return

    # Get today's values — prefer gex_log (most recent) over macro_history
    def n(v):
        try: return float(v) if v else None
        except: return None

    date      = gex_row.get('date', today)
    vix       = n(gex_row.get('vix'))
    vix9d     = n(gex_row.get('vix9d'))
    yield10y  = n(gex_row.get('yield_10y'))
    gold      = n(gex_row.get('gold'))
    dxy       = n(gex_row.get('dxy'))
    tlt       = n(gex_row.get('tlt'))
    hyg       = n(gex_row.get('hyg'))
    copper    = n(gex_row.get('copper'))
    oil       = n(gex_row.get('oil'))
    eem       = n(gex_row.get('eem'))
    xlre      = n(gex_row.get('xlre'))
    skew      = n(gex_row.get('skew_index'))
    gex       = n(gex_row.get('net_gex_b'))
    rsi       = n(gex_row.get('spy_rsi_14'))
    term_spread = n(gex_row.get('vix_term_spread'))
    vix_term  = gex_row.get('vix_term_structure', '')

    # VIX9D ratio
    vix9d_ratio = round(vix9d / vix, 3) if vix9d and vix and vix > 0 else None

    # HYG 5-day change — look back in macro history
    hyg_5d_change = None
    if hyg and macro_hist:
        # Find rows from 5-7 trading days ago
        old_rows = [r for r in macro_hist[-10:] if r.get('hyg')]
        if len(old_rows) >= 5:
            old_hyg = n(old_rows[-5].get('hyg'))
            if old_hyg:
                hyg_5d_change = round(hyg - old_hyg, 3)

    # SKEW signal
    if skew and vix:
        if skew > 150 and vix < 20:
            skew_signal = "black_swan_watch"
        elif skew > 145 and vix > 20:
            skew_signal = "panic_buy"
        elif skew > 135:
            skew_signal = "elevated"
        elif skew < 120:
            skew_signal = "low_hedging"
        else:
            skew_signal = "normal"
    else:
        skew_signal = "unknown"

    # GEX signal
    if gex is None:
        gex_signal = "unknown"
    elif gex < -15:
        gex_signal = "extremely_negative"
    elif gex < -10:
        gex_signal = "deeply_negative"
    elif gex < -5:
        gex_signal = "negative"
    elif gex < 0:
        gex_signal = "mildly_negative"
    elif gex < 5:
        gex_signal = "mildly_positive"
    elif gex < 12:
        gex_signal = "positive"
    else:
        gex_signal = "strongly_positive"

    # Compute scores
    credit_s  = score_credit(hyg)
    vol_s     = score_volatility(vix, vix9d, term_spread)
    flow_s    = score_flow(dxy, gold, tlt)
    growth_s  = score_growth(copper, eem)
    skew_s    = score_skew(skew, vix)
    composite = compute_composite(credit_s, vol_s, flow_s, growth_s, skew_s)
    flow_reg  = get_flow_regime(composite, hyg, dxy, vix)
    signal    = get_regime_signal(composite, hyg, gex, rsi, skew, vix)

    # Build today's row for black swan detection
    today_data = {
        'hyg': hyg, 'skew': skew, 'vix': vix, 'dxy': dxy,
        'composite_score': composite, 'vix_term_signal': vix_term,
        'hyg_5d_change': hyg_5d_change,
    }
    bs_watch, bs_reasons = detect_black_swan(today_data, regime_hist)

    brief = get_brief(signal, composite, hyg, vix, gex, skew, flow_reg, bs_watch)

    # Print summary
    print(f"\n{'='*60}")
    print(f"  DATE:       {date}")
    print(f"  SIGNAL:     {signal}")
    print(f"  COMPOSITE:  {composite:+.1f}/8")
    print(f"  FLOW:       {flow_reg}")
    print(f"  CREDIT:     HYG=${hyg} (score={credit_s})")
    print(f"  VOLATILITY: VIX={vix} (score={vol_s})")
    print(f"  FLOW:       DXY={dxy} Gold=${gold} (score={flow_s})")
    print(f"  GROWTH:     Copper={copper} EEM={eem} (score={growth_s})")
    print(f"  SKEW:       {skew} signal={skew_signal} (score={skew_s})")
    print(f"  GEX:        {gex}B signal={gex_signal}")
    print(f"  HYG 5D CHG: {hyg_5d_change}")
    print(f"  BS WATCH:   {bs_watch}")
    if bs_reasons:
        for r in bs_reasons:
            print(f"    ⚠️  {r}")
    print(f"\n  BRIEF: {brief}")
    print('='*60)

    # Save row
    row = {
        'date': date,
        'vix': vix, 'vix9d': vix9d, 'vix9d_ratio': vix9d_ratio,
        'yield10y': yield10y, 'gold': gold, 'dxy': dxy, 'tlt': tlt,
        'hyg': hyg, 'copper': copper, 'oil': oil, 'eem': eem,
        'xlre': xlre, 'skew': skew, 'gex_b': gex, 'spy_rsi': rsi,
        'credit_score': credit_s, 'vol_score': vol_s,
        'flow_score': flow_s, 'growth_score': growth_s,
        'skew_score': skew_s, 'composite_score': composite,
        'flow_regime': flow_reg,
        'hyg_5d_change': hyg_5d_change,
        'vix_term_signal': vix_term,
        'skew_signal': skew_signal,
        'gex_signal': gex_signal,
        'regime_signal': signal,
        'black_swan_watch': bs_watch,
        'black_swan_reasons': ' | '.join(bs_reasons) if bs_reasons else '',
        'brief': brief,
    }
    save_regime_row(row)
    print("\n  ✅ Done")


if __name__ == "__main__":
    main()
