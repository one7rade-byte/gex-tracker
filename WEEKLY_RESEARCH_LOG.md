# Weekly Research Log

## 2026-08-30

**Housekeeping note first:** this is the first run of the weekly research cycle that
actually produced `claude/gex-tracker-notes.md`, `IDEA_BACKLOG.md`, and this file — none
existed before today, in either branch or any prior commit (checked `git log --all`
across `main` and `claude/beautiful-goodall-d1odxv`, and a fresh GitHub clone). The
research prompt referenced a "validated 2026-08-25" ROC early-warning layer as prior
context; that validation is not in this repo anywhere. Treated as not-done and re-derived
from scratch below rather than assumed. See `claude/gex-tracker-notes.md` → Known open
items for the full note.

**Idea tested (backlog #8, seed list):** Wire a rate-of-change (ROC) early-warning layer
into `regime_analyzer.py` — specifically, does the 5-day change in `composite_score`
(`composite_5d_chg`) or in HYG (`hyg_5d_pct`) give earlier and/or more reliable crash
warning than the current production `composite_score` LEVEL threshold?

**Data source:** `deep_history_backtest_log.csv`, restricted to 2007-04-11 → 2026-08-21
(4,873 rows) — the point HYG (iShares High Yield Corp Bond ETF) actually started trading;
before that, `hyg` is null in this file and any signal using it is meaningless. This range
covers all four episodes tested. No live network fetch was needed or attempted for this
one — the data already existed in the repo.

**Network note:** confirmed today that `fred.stlouisfed.org`, `www.cftc.gov`, and
`query1.finance.yahoo.com` are all blocked (403) from the research sandbox's egress
proxy. This ruled out testing backlog items #1 (COT) and #3 (net liquidity/FRED) this
week — see `IDEA_BACKLOG.md`, both marked BLOCKED rather than tested.

### Method

Script: `research_composite_5d_chg_backtest.py` (committed alongside this log, rerunnable).
- `composite_5d_chg = composite_score.diff(5)`, `hyg_5d_pct = hyg.pct_change(5) * 100`.
- Forward SPY drawdown metric: minimum close over the next 20 trading days relative to
  the signal day (`fwd_maxdd_20d`), not just the point-in-time 20d return — a V-shaped
  bounce can make a real warning look wrong if you only check the endpoint.
- "Hit" = SPY draws down ≥5% at any point in the next 20 trading days.
- Four known crash episodes, defined by actual SPY peak→trough: 2008 GFC
  (2007-10-09→2009-03-09), 2020 COVID (2020-02-19→2020-03-23), 2022 bear
  (2022-01-03→2022-10-13), 2025 tariff selloff (2025-02-19→2025-04-08, -19%, found this
  run by scanning `spy_close` directly — not previously documented anywhere in the repo).
- Cross-checked by era (2007-2012 / 2013-2019 / 2020-2026) per this project's own
  discipline (the by_era/recency_windows correction already in `deep_history_backtest.py`).

### Results — downside (early warning)

**Lead time to first signal, vs. each crash's actual market peak:**

| Episode | `hyg_5d_pct≤-3%` | `composite_5d_chg≤-3` | current prod. `composite_score≤-1` |
|---|---|---|---|
| 2008 GFC | +9 trading days | **+22 trading days** | +235 trading days (10+ months late) |
| 2020 COVID | +6 trading days | **+3 trading days** | +16 trading days |
| 2022 bear | +68 trading days | **+12 trading days** | +79 trading days |
| 2025 selloff | +33 trading days (1 day before the trough — no real warning) | **+2 trading days** | +14 trading days |

(“+N trading days” = N trading days after the SPY peak that started the crash; lower is
better. The last column is what `regime_analyzer.py` actually watches for in production
today.)

**Headline: `composite_5d_chg` beats both `hyg_5d_pct` alone and the current production
level threshold on every single one of the four episodes**, most dramatically on 2008 (22
trading days vs 235) and 2025 (2 days vs 14, and `hyg_5d_pct` alone completely missed this
one — it only fired the day before the bottom).

**Base rate / false-positive check, full history (2007-04-11 to 2026-08-21, n=4,848
days):**
- `hyg_5d_pct≤-3%`: fires on 2.4% of days. Hit rate (≥5% drawdown within 20d) when fired:
  **50.0%** vs **17.2%** unconditional — a real, ~2.9x lift, but (per the table above) its
  timing is inconsistent — sometimes early, sometimes a coincident/lagging confirmation
  rather than a warning (2025).
- `composite_5d_chg≤-3`: fires on 5.0% of days. Hit rate when fired: **28.7%** vs **17.4%**
  unconditional — a real but modest ~1.6x lift. By era: 2007-2012 fire=38.6%/no-fire=27.3%
  (1.4x), 2013-2019 fire=14.1%/no-fire=9.9% (1.4x), 2020-2026 fire=32.0%/no-fire=16.9%
  (1.9x). Holds up across eras, doesn't collapse post-2010 the way the pooled
  composite-bucket finding did in the earlier backtest — but it's a real, not spectacular,
  edge.
- Combined (both `composite_5d_chg≤-3` AND `hyg_5d_pct≤-3` on the same day): rarer (1.1%
  of days), better hit rate (54.9%, ~3.2x lift) — but it **loses almost all the lead-time
  advantage**: for 2008 the AND-signal doesn't fire until 235 trading days after the peak
  (same as the level threshold), and for 2025 it's the same 1-day-before-the-trough
  non-warning as `hyg_5d_pct` alone. The two signals rarely agree *early* in an episode —
  agreement is itself a lagging, confirming signal, not a warning. **Don't require both;
  they solve different problems.**

### Results — upside (catching the turn, symmetric ±3 threshold)

Tested whether `composite_5d_chg ≥ +3` (a sharp 5-day *improvement*) flags the bottom
early enough to participate in the recovery — the other half of the mission's own success
bar, not previously tested by anything in this repo:

| Episode | First `composite_5d_chg≥+3` fire | Trading days after the actual trough | SPY fwd 20d return from that day |
|---|---|---|---|
| 2008 GFC | 2009-04-09 | 23 | +8.36% |
| 2020 COVID | 2020-03-26 | 3 | +8.33% |
| 2022 bear | 2022-11-04 | 16 | +6.18% |
| 2025 selloff | 2025-04-23 | 10 | +8.86% |

Fires within 3-23 trading days of every real bottom, and every single fire was followed
by a strong (+6% to +9%) 20-day SPY return. Base rate: fires on 4.4% of all days, mean
fwd 20d return when fired is +1.82% vs +0.74% unconditional (2.5x), % of fires with a
positive fwd 20d return: 70.8% vs 65.2% unconditional — real but, again, not a dramatic
edge on its own; the crash-episode lead time is the more convincing part of this result
than the unconditional base-rate lift.

### Verdict: PARTIAL PASS — wired in as a WATCH-tier column, not a standalone action signal

This clears the mission's "would this have caught it" bar on lead time — real, consistent,
multi-episode lead time on both the way down and the way up, beating the system currently
in production on every episode tested. It does **not** clear the bar on precision/false-positive
rate cleanly enough to call it a standalone, size-into-it signal the way the mission's PASS
language implies (ROC-layer analogy) — a ~1.6-1.9x hit-rate lift with a ~5% daily fire rate
means roughly 3 out of 4 times it fires, no ≥5% drawdown follows within 20 days. That's a
real edge, not noise (holds up by era), but it's a WATCH flag to combine with other context,
not a trade-by-itself trigger.

**Action taken:** added `composite_5d_chg` and a boolean `early_warning` column
(`composite_5d_chg ≤ -3`) to `regime_analyzer.py` / `regime_log.csv`, computed the same way
the existing `hyg_5d_change` column already is (5-trading-day lookback into
`regime_hist`). Verified with a live run against real `gex_log.csv`/`macro_history.csv`
data before committing (output: `COMP 5D CHG: 0.0  EARLY WARNING: False` for 2026-08-28,
correctly reflecting the current max-bull, no-stress regime). Did not touch the existing
`detect_black_swan()` 10-day composite-drop check (Signal 4) or the black-swan-watch
3-of-6 threshold — that's a separate, already-shipped mechanism; this adds a faster,
narrower, independently-tracked column rather than changing production behavior. No
dashboard/tier wiring beyond the new CSV column — per the mission, that's a
review-and-decide step for the project owner, not something to wire in automatically.

**Caveats:**
- All four episodes are large, well-known crashes chosen because they're the ones this
  project already tracks — this is out-of-sample in the sense that the threshold (±3) was
  not fit to any one of them individually, but it is still only four episodes. A fifth
  real crash could easily fail differently than any of these four (see 2025's near-miss
  on `hyg_5d_pct` alone, which shows this family of signal is not uniformly reliable
  across episode types — 2025 was a policy/trade shock, not a credit event, and HYG barely
  reacted early, unlike 2020's fast panic).
- `regime_log.csv` (the live column) has zero real crash days in it yet (105 rows since
  2026-03-30) — this backtest is entirely on `deep_history_backtest_log.csv`'s
  reconstruction, which lacks GEX and uses a slightly different composite-score
  calculation lineage. The live column should be treated as unverified until it
  accumulates real stress days.
- Threshold (±3) was picked as a round number close to what `detect_black_swan()`
  already uses for its 10-day version (±3), not independently optimized — a follow-up
  could grid-search this, but that risks overfitting to these same four episodes with no
  fifth to validate against.

### New ideas added to `IDEA_BACKLOG.md` this run

- **VIX9D/VIX ratio as a practical VIX3M substitute** (promoted to backlog #5) — the
  seed idea assumed VIX3M was needed and unavailable; `vix9d_ratio` already exists and
  captures the same term-structure shape, fully testable today with zero new data.
- **Add the 2025 tariff selloff to `deep_history_backtest.py`'s `crash_window_analysis`**
  — found the actual peak/trough dates by hand this run (2025-02-19→2025-04-08); should
  be in the table permanently instead of re-derived every time it's needed.
- **Does `composite_5d_chg` flicker on false starts within the same episode, or fire
  cleanly once?** This run only checked the first fire date per episode — a signal that
  toggles on/off for weeks is much less actionable in practice than a clean single fire,
  and this matters for deciding whether it ever graduates past WATCH tier.
