# Idea Backlog

Living list, not a fixed checklist. Pull the next untested idea from the TOP, test it,
then move it to `WEEKLY_RESEARCH_LOG.md` marked done/rejected. Add new ideas to the
bottom each run — grounded in something real from that run, never padded. See
`claude/gex-tracker-notes.md` for the network-access constraint that currently blocks
ideas 1-7.

1. COT (CFTC) positioning as a leading indicator for NQ/ES/gold futures — **BLOCKED**:
   `www.cftc.gov` not reachable from the research sandbox (403 at the egress proxy,
   confirmed 2026-08-30, re-confirmed 2026-09-06). Needs either a reachable mirror/API or
   the data pulled in by a GitHub Actions runner (which has normal internet) into a new
   CSV column.
2. Market breadth (% above 50MA/200MA, advance-decline) vs composite_score — needs
   per-stock breadth data not currently collected anywhere in this repo; not fetchable
   from the research sandbox either (needs many individual-ticker histories, Yahoo denied).
3. Net liquidity proxy (Fed balance sheet - RRP - TGA, from FRED) vs SPY forward returns
   — **BLOCKED**: `fred.stlouisfed.org` not reachable (confirmed 2026-08-30, re-confirmed
   2026-09-06).
4. Yield curve shape (2s10s re-steepening) as a leading recession signal — `yield10y`
   exists in `macro_history.csv` from 2021-08-17, but there's no `yield2y` anywhere in the
   repo yet. Needs a new data source.
5. VIX term structure (VIX/VIX3M backwardation) as an earlier stress flag than spot VIX —
   `vix9d`/`vix9d_ratio` already tracked live in `gex_log.csv` (only ~109 days of history,
   too short to backtest a real crash against) but `deep_history_backtest_log.csv` has no
   vix9d/vix3m column at all, so a real multi-decade backtest of this idea isn't possible
   without a new fetch. Worth revisiting once `regime_log.csv` has enough live history, or
   if `deep_history_backtest.py` is ever extended to include vix9d.
6. Yen carry trade stress (USDJPY + Nikkei correlation) — dedicated watch, not yet
   covered. Needs USDJPY and Nikkei history, not currently in the repo, Yahoo fetch denied.
7. Gold-specific drivers study: real yields (10y TIPS breakeven vs nominal), GDX/GLD
   ratio, vs the DXY-correlation myth already busted (corr ~0.03, don't re-test — build
   on it). Needs TIPS breakeven and GDX history, neither local nor fetchable right now.
8. **Sequential (not same-day) confirmation of composite_5d_chg + hyg_5d_pct** — this
   run's same-day AND-confirmation test (2026-09-06) got real hit-rate lift but destroyed
   the lead-time edge in the 2022 and 2025 episodes specifically because it demands both
   signals agree on the exact same day. Does requiring hyg_5d_pct to confirm within N
   trading days AFTER composite_5d_chg fires (rather than same-day) keep more of
   composite's lead time while still cutting some false positives? Directly testable from
   `deep_history_backtest_log.csv`, no fetch needed.
9. HYG/LQD spread (rather than HYG level or HYG-alone ROC) as a credit-market-specific
   stress detector — a spread nets out generic rate moves that push both HYG and LQD the
   same direction, which a HYG-only ROC can't distinguish from real credit-spread
   widening. Needs LQD history; check whether it's fetchable before attempting (Yahoo
   currently denied, so likely blocked too, but worth a quick allowlist check first since
   it only needs one more ticker).
10. Once `regime_log.csv` has 6-12 months of real accumulated history (currently 109 rows
    since 2026-03-30), re-run the composite_5d_chg/hyg_5d_pct early-warning test against
    LIVE data (not just the `deep_history_backtest.py` historical replay) to confirm the
    relationship holds when `gex` is a real (non-None) input, which the deep-history
    reconstruction structurally cannot test.
11. Add the 2025 tariff selloff (2025-02-19 to 2025-04-08, SPY -19%) to
    `deep_history_backtest.py`'s own `crash_window_analysis` table directly, instead of
    every new research script re-deriving the same peak/trough dates by hand — found
    independently by two separate runs now (2026-08-30 x2), a sign this keeps costing
    real time.
12. Does `composite_5d_chg <= -3` flicker on/off for weeks before a real move inside the
    same crash episode, or fire once cleanly and stay fired? Only the first-fire date per
    episode has been checked so far (both the 2026-08-30 and 2026-09-06 runs). A signal
    that toggles is much less actionable in practice than one that fires once — matters
    for deciding whether this ever graduates past WATCH tier.

## Done / superseded

- ~~Wire the validated ROC early-warning layer (composite_5d_chg, hyg_5d_pct) into
  regime_analyzer.py as a live-accumulating column, if not already done~~ — validated and
  coded 2026-08-30, actually landed on `main` 2026-09-06 (was stuck in two duplicate
  unmerged PRs for a week — see `claude/gex-tracker-notes.md` Bootstrap note). VERDICT:
  PASS. See `WEEKLY_RESEARCH_LOG.md` 2026-08-30 entry.
- ~~Confirmation-signal test: does requiring composite_5d_chg <= -3 AND hyg_5d_pct <=
  -1.5% to BOTH fire same-day raise the hit rate above either alone?~~ — tested
  2026-09-06, real hit-rate lift but destroys lead time in the 2022/2025 episodes.
  REJECTED as an early-warning upgrade. See `WEEKLY_RESEARCH_LOG.md` 2026-09-06 entry.
  (Superseded by backlog item 8 above, the sequential-confirmation variant.)
