"""
signal_tiers.py
────────────────
A symmetric buy/sell tier + position-sizing framework, layered ON TOP of
the existing opportunity_score system in market_scanner.py / mag7_tracker.py
without changing it — that score is deliberately one-directional (0-10,
"how good a dip-buying opportunity is this"), so it has no way to say
"this looks bad, stay away" versus just "not oversold." This module adds
that missing bearish end, plus a sizing multiplier, as new columns.

IMPORTANT ASSUMPTIONS — read before trusting the SELL-side output:
  - This assumes a long/cash account with no shorting. The bottom two
    tiers (REDUCE / STRONG AVOID) mean "don't open new longs here, and
    consider trimming or tightening stops on existing ones" — NOT "this
    is a good short entry." A real short-setup score would need different
    (asymmetric) logic, since a good short isn't just the mirror image of
    a good long. If you do trade short, treat the bottom tiers only as
    "avoid going long," not as a short signal, until this gets extended.
  - size_multiplier is a MULTIPLE of whatever you already use as your
    normal position size (e.g. "1.5x my normal size"), never a dollar
    amount or % of your account — this code has no idea what your account
    size or risk tolerance is, and isn't trying to guess.
  - Like everything else in this repo right now, the inputs feeding this
    (RSI, IV percentile, GEX regime, 200MA) come from a system with only
    ~98 days of history in one rising-market regime — see
    track_signal_performance.py's caveats. A tier label is a structured
    summary of today's inputs, not a validated prediction.

conviction_score: a NEW signed score, roughly -10 (worst) to +10 (best),
built from the same per-ticker inputs market_scanner.py already computes:
  - RSI (oversold -> positive, overbought -> negative), symmetric around 50
  - IV percentile (cheap options -> positive, expensive -> negative)
  - GEX regime (dealer-supportive positive GEX -> positive, unstable
    negative GEX -> negative)
  - Trend vs 200MA (above -> positive, below -> negative)
Any missing input just contributes 0 rather than breaking the calculation,
so this works fine even for tickers that never got the expensive stage-2
GEX fetch (technical-only conviction, weaker signal, still directional).
"""

TIER_STRONG_BUY = "STRONG BUY"
TIER_BUY = "BUY"
TIER_HOLD = "HOLD / NEUTRAL"
TIER_REDUCE = "REDUCE / AVOID NEW"
TIER_STRONG_AVOID = "STRONG AVOID / EXIT"


def compute_conviction_score(rsi_raw=None, rsi_pct=None, iv_pct=None, gex_regime=None, above_200ma=None):
    """Signed score, clamped to [-10, +10]. Prefers rsi_pct (percentile vs.
    the ticker's own history) once it exists; falls back to the raw RSI
    level otherwise — same bootstrap pattern as compute_opportunity_score."""
    score = 0.0

    if rsi_pct is not None:
        score += (50 - rsi_pct) / 12.5        # rsi_pct 0 -> +4, 100 -> -4
    elif rsi_raw is not None:
        score += (50 - rsi_raw) / 12.5        # rsi 0 -> +4, 100 -> -4

    if iv_pct is not None:
        score += (50 - iv_pct) / 16.7         # iv_pct 0 -> +3, 100 -> -3

    if gex_regime == "strongly_positive":
        score += 3
    elif gex_regime == "positive":
        score += 2
    elif gex_regime == "deeply_negative":
        score -= 1   # amplifies moves either direction — only mildly bearish on its own
    elif gex_regime == "negative":
        score -= 2

    if above_200ma is True:
        score += 1
    elif above_200ma is False:
        score -= 1

    return max(-10.0, min(10.0, round(score, 2)))


def classify(conviction_score):
    """(tier, base_size_multiplier, note) for a given conviction_score."""
    s = conviction_score
    if s >= 7:
        return (TIER_STRONG_BUY, 1.5,
                "Highest-conviction reading this system produces — still one system's "
                "read on one day, not a guarantee.")
    if s >= 3:
        return TIER_BUY, 1.0, "Standard-conviction buy setup."
    if s > -3:
        return TIER_HOLD, 0.0, "No real edge either direction — hold what you have, no new entries."
    if s > -7:
        return (TIER_REDUCE, 0.0,
                "Conditions deteriorating — avoid new longs; consider trimming or "
                "tightening stops on existing ones.")
    return (TIER_STRONG_AVOID, 0.0,
            "Worst-conviction reading this system produces — avoid new longs and "
            "review existing exposure closely.")


def size_for_volatility(base_multiplier, iv_pct):
    """Scales a buy-side size_multiplier down as options get more expensive /
    uncertain (higher IV percentile) — same conviction, smaller size when the
    potential swing is bigger. No-ops for HOLD/REDUCE/STRONG AVOID (already 0)
    or when iv_pct isn't known yet."""
    if base_multiplier <= 0 or iv_pct is None:
        return base_multiplier
    if iv_pct >= 80:
        return round(base_multiplier * 0.5, 2)
    if iv_pct >= 60:
        return round(base_multiplier * 0.75, 2)
    return base_multiplier


def classify_and_size(rsi_raw=None, rsi_pct=None, iv_pct=None, gex_regime=None, above_200ma=None):
    """Full pipeline: raw inputs -> (conviction_score, tier, size_multiplier, note)."""
    score = compute_conviction_score(rsi_raw, rsi_pct, iv_pct, gex_regime, above_200ma)
    tier, base_mult, note = classify(score)
    size_mult = size_for_volatility(base_mult, iv_pct)
    return score, tier, size_mult, note
