# WEEKLY RESEARCH LOG

## 2026-10-18 — VIX9D/VIX term structure as an early stress flag (seed #5)

**VERDICT: INCONCLUSIVE — needs more data (no PASS).**

Setup problems found first:
- `claude/gex-tracker-notes.md` does not exist in this repo (any branch). No ROC-layer validation notes, signal framework or open-items backlog could be read. IDEA_BACKLOG.md and this log did not exist either; created from the seed list.
- Yahoo Finance (query1.finance.yahoo.com) is rejected by the sandbox egress proxy (403 CONNECT). No live fetch possible, so network-dependent seeds #1-4, #6-7 were skipped. Seed #8 (wire ROC): regime_analyzer.py only has `hyg_5d_change`; no `composite_5d_chg` column, so it is not done.

Tested (offline, existing CSVs only): macro_history.csv vix9d/vix (the only rows with vix9d: 251 rows, 2025-08-18 to 2026-08-17) against forward SPY closes from deep_history_backtest_log.csv. Event = SPY falls >=5% (close-to-close min) within the next 10 trading days. N=245 usable days.

Numbers:
- Base rate: 2 event days out of 245 (0.82%), forming ONE episode (starting 2026-03-16).
- ratio (vix9d/vix) > 1.0: fires 27 days (11.0%); event rate 3.7%; avg fwd-10d -0.22%.
- ratio > 1.1: fires 3 days (1.2%); 0 events; avg fwd-10d +0.54%.
- ratio > 1.2: never fired.
- spot VIX > 25: fires 16 (6.5%); 0 events; avg fwd-10d +2.49%. VIX > 20: 48 days (19.6%); 4.2% events.
- The one episode: at its start VIX was 23.5 and ratio 1.03; ratio > 1.1 did NOT fire in the prior 10 days; VIX > 25 did.
- Half-split: first half had 0 events; second half 1.6% base, ratio>1.1 & VIX<=25 fired 3 times, 0 hits.

Caveats: a single drawdown episode in-sample, so hit rate, lead time and false-positive rate are statistically meaningless. The point estimates give no support for term structure beating spot VIX (ratio>1 fires 11% of days for a 3.7% event rate). Neither COVID 2020 nor the 2025 selloff is in the vix9d sample, so the mission benchmarks cannot be evaluated. Not rejected, just untestable on live data.

Next step: backlog #8 (full-history vix9d/vix3m via the deep-history fetch workflow).

New ideas added to backlog:
- #8 full-history VIX term-structure test — this run's sample had only one episode.
- #9 fetch-via-Actions or allowlist fix — Yahoo is blocked in scheduled sessions, which blocks most of the list.
