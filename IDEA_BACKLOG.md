# Idea Backlog

Living list, not a fixed checklist. Pull the next untested idea from the TOP, test it,
then move it to `WEEKLY_RESEARCH_LOG.md` marked done/rejected. Add new ideas to the
bottom each run — grounded in something real from that run, never padded. See
`claude/gex-tracker-notes.md` for the network-access constraint that currently blocks
ideas 1-7.

1. COT (CFTC) positioning as a leading indicator for NQ/ES/gold futures — **BLOCKED**:
   `www.cftc.gov` not reachable from the research sandbox (403 at the egress proxy,
   confirmed 2026-08-30, re-confirmed 2026-09-06 and 2026-09-13). Needs either a reachable
   mirror/API or the data pulled in by a GitHub Actions runner (which has normal internet)
   into a new CSV column.
2. Market breadth (% above 50MA/200MA, advance-decline) vs composite_score — needs
   per-stock breadth data not currently collected anywhere in this repo; not fetchable
   from the research sandbox either (needs many individual-ticker histories, Yahoo denied).
3. Net liquidity proxy (Fed balance sheet - RRP - TGA, from FRED) vs SPY forward returns
   — **BLOCKED**: `fred.stlouisfed.org` not reachable (confirmed 2026-08-30, re-confirmed
   2026-09-06 and 2026-09-13).
4. Yield curve shape (2s10s re-steepening) as a leading recession signal — `yield10y`
   exists in `macro_history.csv` from 2021-08-17, but there's no `yield2y` anywhere in the
   repo yet. Needs a new data source.
5. VIX term structure (VIX/VIX3M backwardation) as an earlier stress flag than spot VIX —
   `vix9d`/`vix9d_ratio` already tracked live in `gex_log.csv` (only ~115 days of history,
   too short to backtest a real crash against) but `deep_history_backtest_log.csv` has no
   vix9d/vix3m column at all, so a real multi-decade backtest of this idea isn't possible
   without a new fetch. Worth revisiting once `regime_log.csv` has enough live history, or
   if `deep_history_backtest.py` is ever extended to include vix9d.
6. Yen carry trade stress (USDJPY + Nikkei correlation) — dedicated watch, not yet
   covered. Needs USDJPY and Nikkei history, not currently in the repo, Yahoo fetch denied.
7. Gold-specific drivers study: real yields (10y TIPS breakeven vs nominal), GDX/GLD
   ratio, vs the DXY-correlation myth already busted (corr ~0.03, don't re-test — build
   on it). Needs TIPS breakeven and GDX history, neither local nor fetchable right now.
8. HYG/LQD spread (rather than HYG level or HYG-alone ROC) as a credit-market-specific
   stress detector — a spread nets out generic rate moves that push both HYG and LQD the
   same direction, which a HYG-only ROC can't distinguish from real credit-spread
   widening. Needs LQD history — **BLOCKED**: re-checked 2026-09-20, `query1.finance.yahoo.com`
   and `stooq.com` (tried as an alternate free source) both still return connect_rejected
   (403) from the egress proxy. Same status as items 1-7.
9. Once `regime_log.csv` has 6-12 months of real accumulated history (currently 115 rows
   since 2026-03-30), re-run the composite_5d_chg/hyg_5d_pct early-warning test against
   LIVE data (not just the `deep_history_backtest.py` historical replay) to confirm the
   relationship holds when `gex` is a real (non-None) input, which the deep-history
   reconstruction structurally cannot test.
10. Does `composite_5d_chg <= -3` flicker on/off for weeks before a real move inside the
    same crash episode, or fire once cleanly and stay fired? Only the first-fire date per
    episode has been checked so far (2026-08-30, 2026-09-06, and 2026-09-13 runs). A
    signal that toggles is much less actionable in practice than one that fires once —
    matters for deciding whether this ever graduates past WATCH tier.
11. Candidate fix for the `regime_signal` 2025 blind spot: test adding a narrow
    `composite_score < 0 AND vix_5d_pct >= [threshold]` override to `get_regime_signal`'s
    DEFENSIVE branch, false-positive-checked the same way `composite_5d_chg` was validated
    2026-08-30, to see if it catches 2025-style equity/vol-driven selloffs (which spare
    credit markets, so the existing `composite<=-3 OR hyg<74` gate barely fires — 8.6%/
    0.0% of days respectively in 2025 vs 30-75%/15-59% in 2008/2020/2022) without raising
    the whipsaw rate in calm periods. Root cause diagnosed 2026-09-20, not yet tested as a
    wired-in change. Now the top item — directly testable, no fetch needed.
12. A confirming signal for `composite_5d_chg` built from composite's own sub-scores MINUS
    `vol_score` (credit_score + flow_score + growth_score + skew_score 5-day change, VIX's
    contribution stripped out) — motivated by 2026-09-20's finding that `vix_5d_pct` fails
    as a confirming signal specifically because it's not independent of composite_score
    (r=-0.73, since VIX is a direct input via vol_score). A "composite-without-vol" ROC
    would be independent of VIX by construction; might behave like HYG (informative,
    doesn't just double-count) without HYG's specific 2022/2025 lag problem, since it
    still includes credit_score. Directly testable, no fetch needed.

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
  (Superseded by the sequential-confirmation variant below.)
- ~~Sequential (not same-day) confirmation of composite_5d_chg + hyg_5d_pct — does
  requiring hyg_5d_pct to confirm within N trading days after (rather than same-day)
  preserve more lead time?~~ — tested 2026-09-13 at N=3/5/10/20, same rejection as the
  same-day version for a structural reason (HYG itself is the slow signal in 2022/2025,
  not the same-day requirement). REJECTED. See `WEEKLY_RESEARCH_LOG.md` 2026-09-13 entry.
- ~~Add the 2025 tariff selloff to `deep_history_backtest.py`'s own `crash_window_analysis`
  table directly~~ — done 2026-09-13 (found independently by two prior runs' scripts
  first — a real, avoidable cost). See `WEEKLY_RESEARCH_LOG.md` 2026-09-13 entry.
- ~~VIX/SKEW 5-day-ROC as an alternative confirmation signal for composite_5d_chg~~ —
  tested 2026-09-20. VIX confirmation looked like a win (zero crash-window lag in all
  four episodes) but is an artifact: vix_5d_pct correlates -0.73 with composite_5d_chg
  because VIX is a direct input to composite_score, so it isn't an independent confirming
  signal (90% trigger overlap with composite alone at the loosest threshold). SKEW
  confirmation is independent but has no standalone edge (negative lift alone) and fails
  to confirm in 3 of 4 crash windows. REJECTED, both variants. See `WEEKLY_RESEARCH_LOG.md`
  2026-09-20 entry.
- ~~Why does regime_signal badly underperform flow_regime specifically in the 2025
  selloff?~~ — root-caused 2026-09-20: HYG never traded below $74 during the entire
  35-day episode (0.0% of days vs 15-59% in the other three crashes) and composite_score
  only hit <=-3 on 8.6% of days (vs 29-75% elsewhere), so regime_signal's DEFENSIVE gate
  (composite<=-3 OR hyg<74) barely fires. A real, quantified blind spot for fast
  equity/vol-driven selloffs that spare credit markets — not yet fixed, candidate gate
  added to backlog above. See `WEEKLY_RESEARCH_LOG.md` 2026-09-20 entry.
