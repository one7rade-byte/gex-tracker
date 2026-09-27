# Idea backlog

Living list for the weekly GEX Tracker research cycle. Pull the next untested
idea from the TOP, test it, then move it to `WEEKLY_RESEARCH_LOG.md` marked
done/rejected. Never let this list run dry — add new ideas at the bottom
every run (grounded in something real from that run, not padding).

Created 2026-09-27 from the seed list in the task prompt. Seed item 8
("wire the ROC layer into regime_analyzer.py") was tested first (see
`WEEKLY_RESEARCH_LOG.md` 2026-09-27 entry) instead of item 1, because the
task prompt referenced it as already-validated prior work that turned out
not to exist in the repo — resolving that discrepancy took priority once
found. It's been tested and removed from this list; items 1-7 remain
untested and are unchanged from the original seed order.

1. COT (CFTC) positioning as a leading indicator for NQ/ES/gold futures
2. Market breadth (% above 50MA/200MA, advance-decline) vs composite_score
3. Net liquidity proxy (Fed balance sheet - RRP - TGA, from FRED) vs SPY forward returns
4. Yield curve shape (2s10s re-steepening) as a leading recession signal
5. VIX term structure (VIX/VIX3M backwardation) as an earlier stress flag than spot VIX
6. Yen carry trade stress (USDJPY + Nikkei correlation) — dedicated watch, not yet covered
7. Gold-specific drivers study: real yields (10y TIPS breakeven vs nominal), GDX/GLD ratio,
   vs the DXY-correlation myth already busted (corr ~0.03, don't re-test — build on it)

## Added 2026-09-27

8. Precision filter for the composite_5d_chg stress trigger: this run found
   composite_5d_chg <= -3 has real lead time on every major crash tested
   (2008/2020/2022/2025) but only ~11-19% precision standalone (137 firings,
   most are noise pullbacks that mean-revert). HYG confirmation, VIX-level
   filter, and 3-day persistence were all tried quickly and didn't move the
   needle much. Worth a dedicated pass: does requiring the composite level
   to already be in "stress" or below (not just the 5d change) combined
   with a *widening* (not just declining) HYG-vs-duration-matched-Treasury
   spread help? This needs LQD or IEF data to build an actual credit
   spread rather than proxying credit risk off HYG's raw price (which also
   moves with rates, not just credit quality) — currently blocked on Yahoo
   Finance reachability in this sandbox, so this needs to run somewhere
   that host is allowlisted.
9. Composite_5d_chg risk-on turn (>= +4) fared better than the stress side
   (35.7% precision vs 10.9%, positive avg forward return, and it caught
   the post-bottom turn within 5-15 trading days after the 2020/2022/2025
   lows). Worth its own dedicated test as a "add risk back on" signal
   rather than bundling it with the (weaker) stress-warning side — test
   it standalone against the mission's recovery benchmarks with a proper
   base-rate check, not just the three anecdotal bottoms already glanced
   at this run.
