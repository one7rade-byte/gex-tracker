# Idea backlog (top = next to test)

NOTE 2026-10-04: items 1-7 need live data (CFTC, FRED, Yahoo) and the research sandbox's proxy
denies cftc.gov / fred.stlouisfed.org / query1.finance.yahoo.com (HTTP 403 on CONNECT). They stay
at the top until those hosts are allowlisted; items that can run on repo data go first.

1. COT (CFTC) positioning as a leading indicator for NQ/ES/gold futures  [BLOCKED: cftc.gov]
2. Market breadth (% above 50MA/200MA, advance-decline) vs composite_score  [BLOCKED: needs constituent prices]
3. Net liquidity proxy (Fed balance sheet - RRP - TGA, FRED) vs SPY forward returns  [BLOCKED: FRED]
4. Yield curve shape (2s10s re-steepening) as leading recession signal  [BLOCKED: FRED]
5. VIX term structure (VIX/VIX3M backwardation) as earlier stress flag than spot VIX  [BLOCKED for history; gex_log only has vix_3m since 2026-03-30, no crash in sample]
6. Yen carry trade stress (USDJPY + Nikkei correlation)  [BLOCKED: Yahoo]
7. Gold drivers: real yields, GDX/GLD ratio (DXY myth already busted, don't re-test)  [BLOCKED: FRED/Yahoo]
9. Fast-shock detector: VIX 5d ROC / VIX level jump on deep_history_backtest_log.csv (offline-runnable).
   Why: 2025 selloff — HYG ROC fired 44 days after the SPY peak (at the trough); credit lags tariff/vol shocks.
10. Risk-on turn, episode-level: composite_5d_chg >= +4 while SPY >=10% under its 252d high. Count
    independent episodes (not days) and compare to HYG-led turn. Why: 29 in-drawdown fire days looked
    strong (+3.42% vs +1.08% base fwd 20d) but are heavily clustered, so n is far below 29.
