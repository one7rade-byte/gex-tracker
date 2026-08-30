# Idea Backlog

Living list, not a fixed checklist. Pull the next untested idea from the TOP, test it,
then move it to `WEEKLY_RESEARCH_LOG.md` marked done/rejected. Add new ideas to the
bottom each run — grounded in something real from that run, never padded.

1. COT (CFTC) positioning as a leading indicator for NQ/ES/gold futures — **BLOCKED**:
   `www.cftc.gov` is not reachable from the research sandbox (confirmed 2026-08-30,
   403 from egress proxy). Needs either a reachable mirror/API or the data pulled in by
   a GitHub Actions runner (which has normal internet) into a new CSV column.
2. Market breadth (% above 50MA/200MA, advance-decline) vs composite_score — needs
   per-stock breadth data not currently collected anywhere in this repo; not fetchable
   from the research sandbox either (needs many individual-ticker histories).
3. Net liquidity proxy (Fed balance sheet - RRP - TGA, from FRED) vs SPY forward returns
   — **BLOCKED**: `fred.stlouisfed.org` not reachable from the research sandbox
   (confirmed 2026-08-30).
4. Yield curve shape (2s10s re-steepening) as a leading recession signal — `yield10y`
   exists in `macro_history.csv` from 2021-08-17, but there's no `yield2y` anywhere in
   the repo yet. Needs a new data source.
5. VIX term structure (VIX/VIX3M backwardation) as an earlier stress flag than spot VIX
   — `vix9d`/`vix9d_ratio` already tracked, but not VIX3M specifically. Worth testing
   with vix9d_ratio first before assuming VIX3M is needed (same idea, shorter tenor,
   already in hand).
6. Yen carry trade stress (USDJPY + Nikkei correlation) — dedicated watch, not yet
   covered. Needs USDJPY and Nikkei history, not currently in the repo.
7. Gold-specific drivers study: real yields (10y TIPS breakeven vs nominal), GDX/GLD
   ratio, vs the DXY-correlation myth already busted (corr ~0.03, don't re-test — build
   on it). Needs TIPS breakeven and GDX history, not currently in the repo.

## Done / superseded

- ~~Wire the validated ROC early-warning layer (composite_5d_chg, hyg_5d_pct) into
  regime_analyzer.py as a live-accumulating column, if not already done~~ — done
  2026-08-30. See `WEEKLY_RESEARCH_LOG.md` 2026-08-30 entry. Note: no prior validation
  of this actually existed anywhere in the repo before this run (see
  `claude/gex-tracker-notes.md` "Known open items") — this run built and validated it
  from scratch rather than just wiring in existing work.

## New ideas (added 2026-08-30)

- **VIX9D/VIX ratio as the practical VIX3M substitute** — idea #5 above assumed VIX3M
  was needed and unavailable, but `vix9d_ratio` (already computed daily in
  `regime_analyzer.py`, and derivable from `vix`+`vix9d` for the full 1995-2026 deep
  history) captures the same "near-term fear vs. longer-term calm" shape, just at a
  shorter tenor. Test whether `vix9d_ratio` backwardation (ratio > 1) gives earlier
  warning than spot VIX crossing a fixed threshold, same crash-episode methodology as
  this week's composite_5d_chg test — fully testable with data already in the repo,
  no fetch needed. Promoted to backlog item 5, keep the VIX3M version as a stretch
  goal if a data source is ever found.
- **2025 tariff selloff missing from `crash_window_analysis`** — `deep_history_backtest.py`
  only computes that table for 2008/2020/2022. Add the 2025-02-19 to 2025-04-08 window
  (found this run — see notes) so future backtests get it for free instead of every
  research run re-deriving the peak/trough dates by hand.
- **Does `composite_5d_chg` fire on false starts inside the SAME episode, or just once
  cleanly at the start?** This week's test only checked the FIRST fire date per crash.
  A signal that flickers on/off for weeks before a real move is much less useful in
  practice than one that fires once and stays fired. Worth a follow-up pass on the
  existing `research_hyg_roc.py`-style analysis before this graduates past WATCH tier.
