# IDEA BACKLOG (top = next to test)

1. COT (CFTC) positioning as a leading indicator for NQ/ES/gold futures  [needs network: cftc.gov — check allowlist]
2. Market breadth (% above 50MA/200MA, advance-decline) vs composite_score  [needs network]
3. Net liquidity proxy (Fed balance sheet - RRP - TGA, from FRED) vs SPY forward returns  [needs network]
4. Yield curve shape (2s10s re-steepening) as a leading recession signal  [needs network]
5. Yen carry trade stress (USDJPY + Nikkei correlation)  [needs network]
6. Gold-specific drivers: real yields (10y TIPS breakeven vs nominal), GDX/GLD ratio (DXY-correlation myth already busted, corr ~0.03 — build on it)  [needs network]
7. [DONE 2026-10-25, PR pending review] Wire the ROC early-warning layer (composite_5d_chg, hyg_5d_pct) into regime_analyzer.py as live-accumulating columns. Only hyg_5d_change exists today; composite_5d_chg does not. The 2026-08-25 validation notes are NOT in this repo (see log 2026-10-18).
8. VIX9D/VIX backwardation, FULL-HISTORY re-test: extend vix9d/vix3m back to ~2011 via deep_history_backtest.py's yf fetch (the live macro_history.csv has only 251 rows with vix9d). Reason: the 2026-10-18 test had 1 drawdown episode and could not decide. [needs network: Yahoo]
9. Make the sandbox able to run live fetches: Yahoo (query1.finance.yahoo.com) is rejected by the egress proxy, so 1-6 and 8 can't run in scheduled sessions. Either add hosts to the allowlist, or run the fetch in a GitHub Actions workflow (like deep_history_backtest.yml) that commits CSVs, and test against those.
10. Merge the research notes/backlog/log from the sibling `claude/beautiful-goodall-*` branches into main (they exist only on unmerged branches, so each run rediscovers them).
11. Re-derive ROC thresholds (composite_5d_chg, hyg_5d_pct) offline from deep_history_backtest_log.csv with hit rate + fire rate + by-era split; the 2026-08-25 validation numbers are not in the repo. Offline-capable, so it can run even while Yahoo is blocked.
