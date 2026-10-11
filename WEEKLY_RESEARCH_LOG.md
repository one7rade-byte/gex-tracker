# Weekly research log

## 2026-10-11 — cycle could not run a test (data access + missing context)
**VERDICT: no test run — blocked.** Nothing tested, no numbers produced, nothing rejected or passed.

- Next idea (#1, COT) needs cftc.gov. Sandbox egress proxy returned 403 (CONNECT rejected) for cftc.gov, query1.finance.yahoo.com, fred.stlouisfed.org, stooq.com. Ideas 2-7 need those same sources. pandas/yfinance are also not installed.
- `claude/gex-tracker-notes.md` did not exist on `main` or the working branch (the ROC validation of 2026-08-25 is also not documented anywhere in the repo history), so the signal framework/backlog context referenced by the routine was unavailable. A stub was created.
- Idea #8 (wire ROC layer) not attempted: composite_5d_chg definition/validation is not in the repo; guessing it would risk wiring an unvalidated signal.
- Backlog: added #9 (re-run with network allowlist) and #10 (offline lead-lag study on macro_history.csv).
