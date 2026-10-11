# Idea backlog (top = next to test)

Seeded 2026-10-11 from the standing seed list. Data needs noted per item.

1. COT (CFTC) positioning as a leading indicator for NQ/ES/gold futures — needs cftc.gov (BLOCKED in sandbox 2026-10-11)
2. Market breadth (% above 50MA/200MA, A/D) vs composite_score — needs constituent price history (no source reachable)
3. Net liquidity proxy (Fed balance sheet - RRP - TGA) vs SPY forward returns — needs FRED (BLOCKED)
4. Yield curve shape (2s10s re-steepening) — needs FRED/2y yield (BLOCKED)
5. VIX term structure (VIX/VIX3M) — needs VIX3M history (BLOCKED; repo has vix9d only from 2026-03-30, 135 rows)
6. Yen carry trade stress (USDJPY + Nikkei) — needs Yahoo/other (BLOCKED)
7. Gold drivers: real yields (TIPS breakeven), GDX/GLD — needs FRED/Yahoo (BLOCKED). Do not re-test DXY corr (~0.03).
8. Wire validated ROC early-warning layer (composite_5d_chg, hyg_5d_pct) into regime_analyzer.py as a live column. regime_analyzer.py already logs hyg_5d_change; composite_5d_chg is not computed. Blocked on notes file with the validated definitions (not in repo).

## Added 2026-10-11
9. Re-run the cycle from an environment with network access to Yahoo/FRED/CFTC (allowlist finance hosts in the routine's environment) — prerequisite for items 1-7.
10. Offline-feasible test using only macro_history.csv (1290 rows, 2021-08-17 on): gold/TLT/yield10y/HYG cross-asset lead-lag vs SPY forward returns (no external data needed). Came up because every external-data idea was blocked this run.
