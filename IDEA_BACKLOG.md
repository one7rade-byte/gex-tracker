# Idea Backlog (top = next)
1. COT (CFTC) positioning as a leading indicator for NQ/ES/gold futures [needs cftc.gov allowlisted]
2. Market breadth (% above 50MA/200MA, A/D) vs composite_score
3. Net liquidity proxy (Fed BS - RRP - TGA, FRED) vs SPY forward returns [needs FRED]
4. Yield curve 2s10s re-steepening as recession signal [needs FRED]
5. VIX term structure (VIX/VIX3M) vs spot VIX [needs VIX3M data; only vix9d is local]
6. Yen carry trade stress (USDJPY + Nikkei)
7. Gold drivers: real yields, GDX/GLD (DXY myth already busted, corr ~0.03)
8. Wire ROC layer (composite_5d_chg, hyg_5d_pct) into regime_analyzer.py as live column — NOT done; 2026-11-01 re-test showed weak lead time (see log); wire as accumulate-only
9. (new) ROC-trigger *conditioned on level*: does c5<=-3 only matter when composite is already <=2 / HYG<79? Raw fires precede positive avg 20d returns, so unconditioned it mixes dips and crashes
10. (new) Bottom/risk-on turn detector: ROC layer was only tested on the downside; test composite_5d_chg >= +4 after drawdown >10% vs 2020-03 and 2025-04 lows (benchmark #2 in mission is untested)
11. (new) Data freshness: macro_history.csv stops 2026-08-17; check why the daily collection stopped before any further live-accumulating work
