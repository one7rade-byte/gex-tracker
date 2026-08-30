# Idea Backlog

Living list, not a fixed checklist. Pull the next untested idea from the TOP,
test it, then move it to `WEEKLY_RESEARCH_LOG.md` marked done/rejected. New
ideas get appended at the bottom as they surface. See
`claude/gex-tracker-notes.md` for the network-access constraint that
currently blocks ideas 1-7.

1. COT (CFTC) positioning as a leading indicator for NQ/ES/gold futures —
   blocked, needs a live CFTC fetch, denied by this sandbox's network policy
   (403 at the proxy, confirmed 2026-08-30).
2. Market breadth (% above 50MA/200MA, advance-decline) vs composite_score —
   blocked, no per-stock breadth data exists locally and Yahoo fetches are
   denied.
3. Net liquidity proxy (Fed balance sheet - RRP - TGA, from FRED) vs SPY
   forward returns — blocked, fred.stlouisfed.org denied by the proxy.
4. Yield curve shape (2s10s re-steepening) as a leading recession signal —
   blocked, macro_history.csv only has yield10y, no 2y series locally.
5. VIX term structure (VIX/VIX3M backwardation) as an earlier stress flag
   than spot VIX — blocked for a real backtest: deep_history_backtest_log.csv
   has no vix3m/vix9d column, and refetching from Yahoo is denied. gex_log.csv
   does track vix_term_structure live but only ~105 days of history, too
   short to backtest against a real crash.
6. Yen carry trade stress (USDJPY + Nikkei correlation) — blocked, no local
   data, Yahoo fetch denied.
7. Gold-specific drivers study: real yields (10y TIPS breakeven vs nominal),
   GDX/GLD ratio, vs the DXY-correlation myth already busted (corr ~0.03,
   don't re-test — build on it) — blocked, needs TIPS breakeven + GDX
   history, neither local nor fetchable right now.
8. Confirmation-signal test: does requiring composite_5d_chg <= -3 AND
   hyg_5d_pct <= -1.5% to BOTH fire on the same day (rather than either
   alone) meaningfully raise the forward-drawdown hit rate above the ~25-35%
   seen for each alone in the 2026-08-30 backtest? This is fully testable
   from deep_history_backtest_log.csv already on disk, no network needed.
   Natural next step now that the single-signal version is validated and
   wired in (see WEEKLY_RESEARCH_LOG.md 2026-08-30 entry).
9. Now that composite_5d_chg is being logged live in regime_log.csv, once it
   has ~6-12 months of real accumulated history, re-run the same
   early-warning test against LIVE data (not just the historical replay) to
   confirm the relationship holds when gex is a real (non-None) input,
   which deep_history_backtest.py structurally cannot test.
10. HYG/LQD spread (rather than HYG level or HYG-alone ROC) as a
    credit-market-specific stress detector — a spread nets out generic
    rate moves that push both HYG and LQD the same direction, which a
    HYG-only ROC can't distinguish from real credit-spread widening. Needs
    LQD history; check whether it's fetchable before attempting (Yahoo
    currently denied, so likely blocked too, but worth a quick allowlist
    check first since it only needs one more ticker).
