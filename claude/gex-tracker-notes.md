# GEX Tracker notes
NOTE 2026-11-01: original notes file was not found in the repo (branch or main); this stub was created by the weekly research run.
NOTE 2026-11-07: the original long-form notes live in the claude.ai Project "GEX " as doc `claude/gex-tracker-notes.md` (history through 2026-10-22). This repo file tracks research-routine state only.

## Known open items
(updated 2026-11-21)
- P3 (second tranche) INCONCLUSIVE 2026-11-21: no tranche rule. Shallow -2%/5d add ~= base post-2010; -5% within 20d of a first fire = below-base add in all eras (SBX n=19); SB first-fire tranche doesn't pay (n=7). All-in at first fire = best total return. Invalidation idea -> P8(d).
- Live 11-20: SPY 690.43 (-11.65% from high), regime_signal DEFENSIVE (first ever), event ESCALATING 4/6. All 10 STRONG_BUYs since 10-16 at -6.1% to -9.6%; STRONG_BUY 20d now n=15, 86.7%, +2.02, worst -6.22. Live system averaged down via 4 re-fires below the 10-16 first fire.
- P2 (MAE tracking) PASS 2026-11-18: PR claude/pr-signal-mae adds mae_pct/mfe_pct + open_20d_windows to track_signal_performance.py (not merged). STRONG_BUY proxy drawdown risk = base rate; first fires cleaner (P(MAE20<=-3) 20.7% vs re-fires 36.5%, 2018+). Tight -3% stop costs return. -2% breach within 5d = +2.5% avg from breach (14 eps) -> P3.
- Live 11-18: all 10 STRONG_BUYs since 10-16 with >=2 days elapsed are underwater (to-date -0.3% to -4.0%); 10-22/10-26 resolve 20d on 11-19/11-20 at ~-4%. Event confirmation entries B-F now -2.9% to -3.7% vs early A/G -0.4% (11-17).
- P0b (quick_action) PASS (modest) 2026-11-14: DEFEND only after 2 consecutive trigger days; PR #7 (claude/pr-quick-action-defend-2day) open, not merged. DEFEND days 2007+ = higher fwd20 (+1.29 vs +0.78) but 2x drawdown risk; cash-on-DEFEND cost 3.8pp CAGR -> treat as no-adds, not sell. Waiting for DEFEND to clear: -0.4 to -0.6% upside, +0.3-0.9pp less MAE.
- Live 11-13: first 20d STRONG_BUY loss (10-16, -1.01%); event confirmation entries +0.13%/-0.74% vs early +2.67%.
- P0 (SMH/RSP rotation shakeout) INCONCLUSIVE 2026-11-11: dip-within-10d 42% vs 19% base, but 20d upside is threshold-fragile (6 episodes, 0 fires 2010-17); confirmation entries didn't help; credit-selling subgroup (HYG/IEF 10d <= -1) 2 bad of 4. Not wired in.
- P1 (vol-free STRONG_BUY gate) REJECTED 2026-11-07: keep composite>=1.
- Real live gap: Oct 16-Nov 3 STRONG_BUY cluster (composite 4.5-4.7) fired with rotation R ON + HYG/IEF 10d -1.5 to -2.0; 10d outcomes -0.88/-3.86/-1.26. STRONG_BUY fired again 11-10 with R ON (credit calmer). Next: P8 (re-fire / rotation+credit veto / RSI<40).
- Remaining priority items: P8 (next; now incl. (d) invalidation), P5, P6, P7, P9. Re-run deep_history_backtest.yml so the Nov-2026 event enters the deep log.
- Event 2026-11-05: confirmation entries (753.01) cost 2.5% vs trigger close (734.40), no drawdown avoided so far (trigger close was the low).
- STRONG_BUY setup is untestable pre-2010 in deep history (SKEW>138 only 2 days pre-2010); deep tests are effectively 2010+.
- Research routine CAN push to claude/research.
- ROC layer (composite_5d_chg, hyg_5d_pct): not in code; ~1.5-3x lift, poor lead time (2026-11-01).
- macro_history.csv last row 2026-08-17 (stale); deep_history_backtest_log.csv ends 2026-08-21 — re-run deep_history_backtest.yml to cover the Nov-2026 event.
- Sandbox can't reach Yahoo/FRED/CFTC; ideas 1,3,4,5,7 need allowlist (flow_history.csv now covers VIX3M, so idea 5 is testable locally).
- Bottom/risk-on-turn detection untested.
