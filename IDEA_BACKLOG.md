# Idea Backlog (top = next)

## PRIORITY — signal accuracy (added 2026-11-05 by Simon's request)
Context: on 2026-11-05 SPY fell 4.4% to 734.40, yet regime_signal said only BUY_WATCH. STRONG_BUY had fired
Oct 30–Nov 3 at 751–755, which is now underwater (the first live loss after 13/13). Root cause: STRONG_BUY requires
composite >= 1, and composite collapsed 5.9 -> 0.9 almost entirely from vol_score (+2 -> -3). Credit and growth
were unchanged. The gate penalizes the very panic STRONG_BUY is meant to buy. Simon's philosophy: "don't be first,
don't be last, follow the whales". Confirmation over earliness.
Event data lives on branch claude/event-2026-11-05 (research/event_2026_11_05/), updated daily.

P0. NEW DATA (2026-11-05): flow_history.csv (repo root, 1999+, updated daily by gex_daily.yml) adds SMH, RSP, IWM,
    QQQ, HYG/LQD, HYG/IEF, KRE, defensive/cyclical ratio, VVIX, MOVE, USDJPY, copper/gold, BTC, VIX/VIX3M and SPY
    volume vs its 20d average. Use it for P5/P6 and the items below instead of saying the data isn't available.
    First read: into Nov 4, SMH/SPY 10d was -8.7% (2.7th pctile) while RSP/SPY was +3.9% (99.6th) and defensive/
    cyclical +6.8% (96th). Credit (HYG/IEF), VVIX, MOVE and USDJPY were all normal. That is a rotation out of
    semis/megacap tech, not a systemic de-risk. Quick test, "SMH/SPY 10d <= -6% AND RSP/SPY 10d >= +2.5%": 6 episodes
    since 1999 (2009-05, 2021-03, 2024-07, 2024-09, 2025-03, 2026-07); a >=3% dip within 10d followed 42% of days
    (base 22%), but the median 20d SPY return was +3.4% (base +1.2%). A shakeout, then bought. Small n. To do:
    validate it properly (episode-level, MAE, by_era), test it as a "heads-up, then wait for confirmation" rule, and
    check whether credit weakness (HYG/IEF) separates the bad cases.
P0b. QUICK ACTION tuning (quick_action.py, live on main 2026-11-05; the dashboard card + top line of Telegram).
    Replay over live history (147 days): HOLD 95, WAIT 39, DEFEND 10, ADD 3. DEFEND fired Oct 21-27 and Nov 2,
    ahead of the Nov 5 drop (avg 10d fwd -1.37%), but flip-flopped with HOLD day to day. WAIT days averaged +1.48%
    over 10d, so in this bull sample waiting cost upside. ADD n=3, too few to judge. To do: test a 2-day persistence
    rule to stop DEFEND/HOLD whipsaw; measure cost of waiting vs drawdown avoided over deep history using
    flow_history.csv; check whether the "Leaving stocks" flow rule (HYG/IEF 10d <= -1% AND defensive/cyclical
    >= +3%) is what drove DEFEND and how it did since 1999. Propose changes as a PR; don't edit main directly.
P1. [TESTED 2026-11-07 — rejected, see WEEKLY_RESEARCH_LOG.md] composite-ex-vol gate. Keep composite>=1.
P2. Max adverse excursion: track_signal_performance.py reports hit rate/avg return only. Add worst drawdown after
    signal (5/10/20d). A 100% hit rate can hide a -3% dip first. Resolve Oct 30–Nov 5 STRONG_BUY/BUY_WATCH outcomes
    as they mature.
P3. Deeper-but-downgraded entries: historically, when the signal downgrades while price falls further below a
    recent STRONG_BUY-type entry, is the lower entry better or worse? Should a second tranche be a rule?
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
    flow_history.csv) on STRONG_BUY; (c) RSI<40 instead of <50 — first read 2018+: A-group 20d hit 88.2%/+3.18% (52 days,
    17 episodes) vs 69.2%/+1.42% at RSI<50. Report fire-rate cost (fewer signals) alongside accuracy. Overlaps P3/P0.

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
