# Idea Backlog (top = next)

## PRIORITY — signal accuracy (added 2026-11-05 by Simon's request)
Context: on 2026-11-05 SPY fell 4.4% to 734.40, yet regime_signal said only BUY_WATCH. STRONG_BUY had fired
Oct 30–Nov 3 at 751–755, which is now underwater (the first live loss after 13/13). Root cause: STRONG_BUY requires
composite >= 1, and composite collapsed 5.9 -> 0.9 almost entirely from vol_score (+2 -> -3). Credit and growth
were unchanged. The gate penalizes the very panic STRONG_BUY is meant to buy. Simon's philosophy: "don't be first,
don't be last, follow the whales". Confirmation over earliness.
Event data lives on branch claude/event-2026-11-05 (research/event_2026_11_05/), updated daily.

P0. [TESTED 2026-11-11 — inconclusive, see WEEKLY_RESEARCH_LOG.md] SMH/RSP rotation shakeout. Dip risk ~2x base
    (42% vs 19% day-level), but the 20d upside only holds at the original thresholds (neighbors negative); confirmations
    C1/C2/C3 don't help. Credit split (HYG/IEF 10d <= -1) 2-for-4 episodes. flow_history.csv remains the data source
    for the items below.
P0b. [TESTED 2026-11-14 — PASS (modest), PR claude/pr-quick-action-defend-2day; see WEEKLY_RESEARCH_LOG.md] DEFEND needs
    2 consecutive trigger days (switches 19.5 -> 12.0/yr 2007+; better both sides 2007+/2018+, worse max DD 2010-17).
    DEFEND is a vol flag, not a sell: cash-on-DEFEND cost 3.8pp CAGR 2007+. Headline reworded to "no new adds".
P0d. (new 2026-11-24) GEX AT THE LOW, a live-only hypothesis. At the 2026-11-20 flush (SPY 689.81, RSI 29.4, VIX 35.9)
    price made a new low while SPY GEX got LESS negative (-20.0 -> -13.2): dealers covering into the low. The 2026-03-30 low
    (RSI 22.8, GEX -3.5) looked similar. GEX history only starts 2026-03-30, so this can't be backtested. Track it on every
    future RSI<30 day: GEX change vs the prior day, VIX, next 5/10/20d return, and whether the low held. Also see
    research/rsi_divergence/FINDINGS.md: RSI bear divergence has no edge as a crash warning (present before 82% of all highs);
    first oversold is undercut within 60d 85% of the time.
P0c. (new 2026-11-15) NEWS SHOCKS / DIP QUALITY (live on main; dip_quality.py, research/news_shock/FINDINGS.md).
    6,163 S&P 500 shock drops since 2010. Bad news alone is ~50/50 vs SPY over 60d. The score (logistic, trained
    2010-18) is a modest edge on 2019+: top band beat SPY 54.8% vs 39.4% for the bottom band, test AUC 0.553.
    Clearest pattern: market also weak AND stock already beaten down = 60.5% / +4.0% median; stock-specific overnight
    gap <= -5% in a calm market near highs = 44.7% / -1.3% (post-news drift). Mag 7: the score does NOT rank them
    (AUC ~0.53), but 56.5% beat SPY at 60d and 64.5% at 120d, so they're judged on that record. To do:
    (a) SEC 8-K event type + XBRL revenue trend: SEC returns 403 to GitHub Actions IPs (both www.sec.gov and
        data.sec.gov). Simon can add sec.gov + data.sec.gov to the session's allowed domains; then fetch from the
        sandbox and merge on (ticker, date). Expected to be the biggest improvement (earnings vs no-filing news).
    (b) Survivorship bias: current S&P members only. Find a free historical-constituents source and quantify the bias.
    (c) Multi-day news slides (e.g. NVDA -12.7% over 5 days, Nov 2026, no single 6% day) aren't covered. Study them.
    (d) Re-run news_shock_study.yml + fit_dip_quality.py quarterly to resolve outcomes; track live accuracy of the
        verdicts in dip_quality.json. Propose changes as a PR.
P1. [TESTED 2026-11-07 — rejected, see WEEKLY_RESEARCH_LOG.md] composite-ex-vol gate. Keep composite>=1.
P2. [TESTED 2026-11-18 — PASS (tracking), PR claude/pr-signal-mae; see WEEKLY_RESEARCH_LOG.md] MAE/MFE now in
    track_signal_performance.py + open_20d_windows list. STRONG_BUY proxy MAE = base (2018+ P(MAE20<=-3) 33.1% vs 33.2%);
    first fires 20.7%, re-fires 36.5%. -3% close stop costs return. Do not add a stop rule.
P3. [TESTED 2026-11-21 — inconclusive, see WEEKLY_RESEARCH_LOG.md] Second tranche after a first fire. Shallow add
    (-2% in 5d) ~= base after 2010; deeper adds worse; -5% within 20d of a first fire is a below-base add in all 3 eras
    (SBX n=19). SB proxy first fires: tranche does not pay (n=7). All-in at first fire has the best total return.
    No tranche rule. "Don't average down a failed STRONG_BUY" moved into P8(d).
P4. [DONE 2026-11-05 on main, a8606d1] Fix the stale HYG 5d bug: regime_analyzer.hyg_5d_change reads macro_history.csv, frozen since 2026-08-17, so
    every "HYG dropped $X in 5 days" warning since then is false (true 5d on 11-05 was -0.39%). Compute it from
    gex_log.csv's hyg column. Small PR with a test.
P5. Confirmation-tier entries (Simon's philosophy): across the 28 historical SPY <= -3.5% days, compare early entries
    (trigger close, RSI<30) vs confirmation entries (VIX back below a threshold, VIX9D<VIX, credit holding). Report
    cost of waiting (rebound missed) vs pain avoided (drawdown after entry).
P6. QQQ lagging SPY >= 2-3% over 10d as an early heads-up (2.5x base rate live, 2026 only). Needs QQQ history
    (Yahoo, 1999+). If the sandbox can't fetch it, add a fetch step to a workflow_dispatch workflow and say so.
P7. 2-day GEX confirmation: a 1-day GEX flip positive after >=3 negative days (Nov 4) preceded a >=3% dip 3/15 times
    live. Test whether requiring 2 consecutive positive days before GREEN reduces false all-clears.
P8. (new 2026-11-07) STRONG_BUY re-fire / "early not confirmed" problem. Live: 7 STRONG_BUYs Oct 16-Nov 3 (SPY 752-764,
    composite 4.5-4.7, VIX 18.4-21.2) all -2.2% to -3.7% by 11-06; the gate never blocked them. Test, with the deep proxy
    (RSI<50/SKEW>138/VIX>17 legs, no GEX): (a) first fire of a cluster vs re-fires when legs already fired >=3 of prior
    10 days and price is below the first fire; (b) a whale-flow veto (SMH/SPY 10d <= -6% or defensive/cyclical 10d >= +3%,
    flow_history.csv) on STRONG_BUY — P0 run 2026-11-11 suggests testing "rotation R ON AND HYG/IEF 10d <= -1" as the
    veto (Oct-2026 cluster had it; Aug-2024 rebound also had it, so measure the upside cost); P2 (2026-11-18) drawdown side of (a): 2018+ first fires P(MAE20<=-3) 20.7%, hit 79.3%, +1.59 (n=29) vs
    re-fires 36.5%, 66.3%, +1.37 (n=104). Live re-fires 11-13/11-16/11-18 are in this subgroup. (c) RSI<40 instead of <50 — first read 2018+: A-group 20d hit 88.2%/+3.18% (52 days,
    17 episodes) vs 69.2%/+1.42% at RSI<50. Report fire-rate cost (fewer signals) alongside accuracy. Overlaps P3/P0.
    (d) (from P3, 2026-11-21) invalidation: once a first fire is -5% (or -3% with composite<1) within 20d, suppress
    STRONG_BUY re-fires below the first-fire price until a new episode. Live: 4 re-fires below 761.68 (11-06..11-16)
    are all -6% to -8% to date. Measure upside missed (2010-17 tranches were positive) vs drawdown avoided.
P9. (new 2026-11-14) Backwardation >=3d (T2) was the most cost-efficient DEFEND trigger 2007+ (CAGR 8.83->8.66,
    max DD -56.5->-47.3, 4 switches/yr) while credit5d (T1) cost 2.6pp CAGR for ~no DD help. Test tiering DEFEND by
    trigger (T2/T4 = de-risk; T1/T3 alone = no-adds only) and whether T1 needs a level filter (HYG below 50d MA).

## General backlog (from earlier runs)
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
