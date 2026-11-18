# Weekly Research Log

## 2026-11-18 — P2: maximum adverse excursion (MAE) after STRONG_BUY / BUY_WATCH

**VERDICT: PASS — ready for review (tracking change only; no signal logic touched).** `track_signal_performance.py` now records the worst and best close inside each 5/10/20d window (`mae_pct`, `mfe_pct`), backfills the 448 older rows from gex_log.csv without changing their logged values, adds MAE stats per bucket to the summary, and lists STRONG_BUY/BUY_WATCH calls whose 20d window is still open. PR: `claude/pr-signal-mae` (4 unit tests). The research findings below are **not** proposed as rule changes; they feed P3 and P8.

**Data and method** (`research/p2_mae.py`; output `research/p2_mae_output.txt`, `p2_mae_results.json`):
- Live: regime_log.csv signals 2026-03-30..11-18 (162 days), SPY closes from gex_log.csv (the series the tracker uses). MAE_h = worst close in t+1..t+h vs entry close. Closes only, so intraday lows are missed and MAE is understated.
- Deep: deep_history_backtest_log.csv (1995-10-17..2026-08-21). STRONG_BUY proxy = composite ≥ 1 & RSI < 50 & SKEW > 138 & VIX > 17 (no GEX; same as P1). It fires only from 2010 (SKEW), so "full" = 2010+. BUY_WATCH proxy (composite ≥ 0 & RSI < 57) fires on 39% of days without the GEX leg and is not informative; reported in the output file only. Episode = first fire of a cluster separated by > 10 trading days.

**1. Live (hypothesis-grade; one bull run plus the current drawdown):**

| Signal | h | n | Hit | Avg | MAE avg | MAE worst | P(MAE ≤ −2) | P(MAE ≤ −3) |
|---|---|---|---|---|---|---|---|---|
| all days | 20 | 142 | 63.4% | +1.46 | −1.54 | −6.03 | 33.1% | 19.0% |
| STRONG_BUY | 5 | 21 | 76.2% | +1.34 | −0.60 | −2.73 | 19.0% | 0.0% |
| STRONG_BUY | 10 | 19 | 68.4% | +1.50 | −1.06 | −3.86 | 26.3% | 15.8% |
| STRONG_BUY | 20 | 14 | 92.9% | +2.61 | −0.57 | −3.58 | 7.1% | 7.1% |
| BUY_WATCH | 20 | 28 | 71.4% | +0.76 | −1.61 | −5.09 | 25.0% | 10.7% |

The resolved 20d STRONG_BUY bucket looks low-risk only because it is mostly Jun–Sep bull-run fires (13 of 14). **Every STRONG_BUY since 10-16 with at least 2 days elapsed is underwater to date** (10 fires; 10-22 −4.03% / MAE −4.24, 10-26 −3.88 / −4.09, 10-30 −2.90 / −3.12, 11-03 −2.86 / −3.07, 11-13 −2.77 / −2.99, 11-10 −2.24 / −2.46). When these resolve, the 20d MAE stats will move toward the all-days base. The new `open_20d_windows` list in the summary makes this visible before resolution, which was the point of P2.

**2. Deep proxy: is STRONG_BUY a low-drawdown entry? No; the edge is return, not risk.**

| Era | Set | n | Hit20 | Fwd20 | MAE20 avg | P(MAE20 ≤ −3) | Winners that first dipped ≤ −2 |
|---|---|---|---|---|---|---|---|
| 2018+ | base | 2151 | 67.2% | +1.06 | −2.69 | 33.2% | 24.4% |
| 2018+ | SB proxy, days | 133 | 69.2% | +1.42 | −2.61 | 33.1% | 28.3% |
| 2018+ | SB proxy, first fire (episodes) | 29 | 79.3% | +1.59 | −2.01 | 20.7% | 17.4% |
| 2018+ | SB proxy, re-fires | 104 | 66.3% | +1.37 | −2.78 | 36.5% | – |
| 2010–17 | base | 2013 | 67.3% | +0.97 | −2.05 | 26.5% | 18.6% |
| 2010–17 | SB proxy, days | 10 | 60.0% | +0.30 | −3.26 | 60.0% | 50.0% |
| 2010–17 | SB proxy, episodes | 6 | 66.7% | +0.11 | −3.71 | 50.0% | 50.0% |

- Day-level STRONG_BUY-proxy drawdown risk equals the base rate (2018+: 33.1% vs 33.2%). First fires are cleaner (20.7%); re-fires carry the risk (36.5%). This is the drawdown side of P8(a), with 29 first-fire episodes. 2010–17 counter-era: 10 days / 6 episodes, worse than base on both sides.
- Fixed −3% close stop (exit at the first close ≤ −3%): 2018+ day-level avg +0.87 vs +1.42 holding, 12 eventual winners stopped out; base +0.72 vs +1.06. At episode level the stop changed little (+1.82 vs +1.59, 0 winners stopped). **A tight stop costs return on these dip entries; not recommended.**
- Failure cases (SB-proxy episodes, fwd20 / MAE20): 2025-03-20 −6.91 / −12.20, 2022-04-13 −11.50 / −11.50, 2025-02-21 −5.99 / −8.09, 2022-01-05 −4.65 / −7.93, 2015-12-15 −6.39 / −7.90, 2016-01-04 −5.40 / −7.65. All are slow-grind selloffs (2015-16, 2022, 2025), not single shocks.

**3. A −2% close within 5 days of a STRONG_BUY: warning, or second-tranche entry?**
- SB proxy 2010+: if the first 5 days stay above −2%, 20d hit 78.0% / +1.97% (n=100 days). If they breach −2%, 46.5% / −0.13% from the **original** entry (n=43 days, 14 episodes).
- But from the **breach close** (what you actually know then), holding to entry+20 returned +2.50% avg / +2.47% median, hit 60.5% (2018+: +2.99%, 66.7%, 12 episodes), with a further MAE of −2.60% avg and P(further ≤ −3%) 37.2%. Compare any-day −2% breaches 2010+: +1.75%, hit 68.9%, further MAE −2.87%.
- So the breach is not a sell signal. As a second-tranche point it has higher average payoff than a random −2% breach, but lower hit rate and a 1-in-3 chance of another −3%. That is the P3 question; 14 episodes is not enough to wire it in. Live: 10-30/11-02/11-03 breached on 11-05 (734.40) and are −0.18% from the breach as of 11-18; 11-10/11-13 breached on 11-17 (731.46), +0.22% from the breach. Still open.

**Caveats:** closes only (MAE understated); live n is small and regime-specific; deep proxy has no GEX leg and is effectively 2018+ (133 of 143 fire days); day-level rows overlap; no costs.

**Live check (signal_performance_log.csv recomputed through 11-18; event tracking_log through 11-17):**
- Resolved since 11-14: 3 new outcomes (now 451 rows). STRONG_BUY 20d still n=14 / 92.9% / +2.60% (10-16 −1.01% is the only loss). 10-22 and 10-26 STRONG_BUY 20d resolve 11-19 and 11-20 at about −4%. BUY_WATCH 20d n=28, 71.4%, +0.76% (10-19 −3.50%).
- Event 2026-11-05 (day 8, 11-17): SPY 731.46, first close below the 734.40 trigger; escalation 2/6. Ledger flipped from the 11-14 picture: early A/G −0.40% (max DD −0.40%), confirmation B/C/F (753.01) −2.86%, D/E (759.62) −3.71%. **Confirmation entries are now worse on both sides**, not just more expensive. One event, but it is the first live case where waiting for "stabilization" bought a lower-quality entry, consistent with P0's C1/C2 result.
- Contradiction worth flagging: regime_signal fired STRONG_BUY on 11-13, 11-16 and 11-18 (composite 3.7 → 2.5 → 1.5) while SPY made lower closes, VVIX rose 101 → 121 and HYG/IEF fell. These are re-fires in a cluster that started 10-16, the subgroup with 36.5% P(MAE20 ≤ −3) above. P8(a) is the next item.

## 2026-11-14 — P0b: QUICK ACTION tuning (DEFEND persistence, cost of waiting vs drawdown avoided, "Leaving stocks" since 2007)

**VERDICT: PASS — ready for review (modest).** Require the DEFEND trigger to hold for **2 consecutive days** before quick_action says DEFEND. Across 2007–2026 this cuts switches from 19.5/yr to 12.0/yr. It is better than the 1-day rule on both sides in 2 of 3 eras. In 2010–17 it is worse on drawdown. A second finding matters more for how the card is read: **DEFEND is not a sell signal.** Going to cash on every DEFEND day cost 3.8 pp of CAGR over 2007–2026 (8.83% → 5.05%). It is a "no new adds / don't be first" flag, and the headline should say so. PR #7: `claude/pr-quick-action-defend-2day` (open, not merged).

**Data and method** (`research/p0b_quick_action.py`; output in `research/p0b_quick_action_output.txt`, `p0b_quick_action_results.json`, `p0b_live_replay.csv`):
- **Live replay:** quick_action's decision re-run for each SPY day in gex_log.csv (2026-04-08 to 11-13, 154 days), using only data up to that day. flow_history.csv is the current file, which may include revisions, so dates can differ slightly from the 11-05 replay. That replay had DEFEND on Oct 21–27 + Nov 2; this one has Sep 29, Oct 16–27 and Nov 2.
- **Deep test:** the DEFEND triggers that don't need GEX, rebuilt from flow_history.csv (2007-04-11 to 2026-11-13, 4,932 days). T1 credit breaking = HYG 5d ≤ −1.5%. T2 = VIX/VIX3M > 1 for ≥3 days (the live "backwardation" is VIX3M − VIX < 0, the same thing). T3 "Leaving stocks" = HYG/IEF 10d ≤ −1% AND defensive/cyclical 10d ≥ +3%. T4 = deep-log regime DEFENSIVE/CRISIS (to 2026-08-21). T4 is reported separately because the live regime_signal has never been DEFENSIVE/CRISIS.
- Persistence state machine: ON after k_on consecutive raw days, OFF after k_off consecutive clear days. Overlay = hold SPY, cash the day after a DEFEND close. No costs, no cash yield, price-only SPY. This is an upper bound on what "protect" could mean.

**1. Live replay (hypothesis-grade, one bull run).** HOLD 98, WAIT 43, DEFEND 10, ADD 3; 44 action changes in 154 days. DEFEND triggers: flow-red 9 days, credit5d 1 day. 10d after DEFEND days: n=9, hit 11.1%, avg −1.82%, MAE −2.79%, P(dd ≤ −3%) 44.4%. Base: 54.9% / +0.56% / −1.17% / 11.1%. WAIT 10d: n=37, hit 81.1%, +1.43%, MAE −0.66%; waiting cost upside in this sample. ADD n=3, −0.42%: too few to judge. Four live STRONG_BUY days (10-16, 10-22, 10-26, 11-02) were already overridden to DEFEND by the flow-red rule. quick_action effectively already applies the P8(b) veto on those days.
- 2-day persistence (k_on=2, k_off=1) on live: 10 → 7 DEFEND days, 6 → 2 switches, one episode (10-19..10-27). 10d after: 0/7 hit, −2.43%, MAE −3.39%. It drops two single-day fires. **9-29 (credit5d) was a false alarm** (fwd10 +1.47%, MAE10 −0.45%). **11-02 was a real warning** (MAE10 −2.34% into the 11-05 drop). On this tiny sample that is one gain and one miss.

**2. Deep history: what DEFEND days are followed by** (20d, day level):

| Era | Trigger | Days (%) | Episodes | Hit20 | Fwd20 | MAE20 | P(MAE20 ≤ −5) |
|---|---|---|---|---|---|---|---|
| 2007+ | base | 4912 | – | 65.2% | +0.78 | −2.72 | 17.9% |
| 2007+ | T1 credit5d | 412 (8.4%) | 79 | 61.7% | +1.36 | −4.43 | 33.5% |
| 2007+ | T2 backw 3d | 321 (6.5%) | 30 | 66.4% | +1.74 | −5.93 | 37.4% |
| 2007+ | T3 flow red | 363 (7.4%) | 66 | 63.1% | +0.97 | −4.47 | 33.2% |
| 2007+ | T1∪T2∪T3 | 808 (16.4%) | 96 | 63.0% | +1.29 | −4.26 | 30.8% |
| 2007-09 | T1∪T2∪T3 (base −0.57 / −4.88 / 34.8%) | 248 (36.0%) | 18 | 57.3% | −0.03 | −6.31 | 40.7% |
| 2010-17 | T1∪T2∪T3 (base +0.97 / −2.05 / 12.1%) | 256 (12.7%) | 38 | 66.4% | +2.02 | −2.51 | 19.5% |
| 2018+ | T1∪T2∪T3 (base +1.03 / −2.66 / 17.8%) | 304 (13.6%) | 40 | 64.9% | +1.77 | −4.05 | 32.1% |
| 2018+ | T4 regime | 173 (7.8%) | 10 | 75.7% | +4.08 | −2.50 | 19.7% |

DEFEND days are **volatility flags, not direction flags.** Drawdown risk roughly doubles (P(MAE20 ≤ −5) 30.8% vs 17.9%). But average forward return is *higher* than base in every era except 2007–09, because these are dips that mostly bounce. 39% of raw trigger runs last one day (T1 40%, T3 47%, T2 27%). That is the whipsaw P0b asked about.

**3. Cash-on-DEFEND overlay vs buy & hold** (T1∪T2∪T3):

| Era | Rule | Time out | Switches/yr | CAGR B&H → rule | Max DD B&H → rule |
|---|---|---|---|---|---|
| 2007+ | 1-day (current) | 16.4% | 19.5 | 8.83 → 5.05 | −56.5 → −42.7 |
| 2007+ | **2-day on, 1-day off** | 12.5% | 12.0 | 8.83 → **6.50** | −56.5 → **−34.8** |
| 2007+ | 2-day on, 2-day off | 15.4% | 11.2 | 8.83 → 5.45 | −56.5 → −29.7 |
| 2018+ | 1-day | 13.6% | 19.4 | 12.38 → 7.47 | −34.1 → −22.5 |
| 2018+ | **2-day on, 1-day off** | 9.8% | 10.9 | 12.38 → **9.42** | −34.1 → **−20.9** |
| 2010-17 | 1-day | 12.7% | 18.3 | 11.32 → 7.61 | −19.4 → −14.7 |
| 2010-17 | **2-day on, 1-day off** | 9.1% | 12.0 | 11.32 → 7.44 | −19.4 → **−18.1 (worse)** |

- Every variant of the union costs 2–5 pp of CAGR vs holding. Days spent out of the market had positive net returns (2007+ 1-day: +664.7 pp of up days missed vs 575.2 pp of down days avoided). **So DEFEND should not mean "sell".**
- T2 alone (backwardation ≥3d) is the most efficient single trigger: CAGR 8.83 → 8.66, max DD −56.5 → −47.3, 4.2 switches/yr. T1 alone 1-day: 8.83 → 6.20, max DD barely changes (−54.8). T3 alone: 8.83 → 7.35, max DD −57.2 (no help). T3 with 2-day on/off was the only variant to beat B&H CAGR (9.59; 2018+ 14.85 vs 12.38), but in 2010–17 it lost (9.00 vs 11.32, DD worse). I'm treating that as noise, not a finding.
- Adding T4 (regime) on top changes little: 2-day on, 1-day off 2007–Aug 2026 gives 9.03 → 6.27, max DD −26.0.

**4. "No new adds while DEFEND": buy at the DEFEND start vs wait until it clears** (common endpoint = clear day + 20):

| Rule | Era | Episodes | Median wait | End ret early → late | Late entry price vs early | MAE early → late | P(MAE ≤ −5) early → late | Late better |
|---|---|---|---|---|---|---|---|---|
| 1-day | 2007+ | 189 | 2d | +1.39 → +0.97 | +0.40% | −3.57 → −3.05 | 27.0 → 22.8% | 34.4% |
| 2-day on | 2007+ | 116 | 3d | +1.35 → +0.91 | +0.43% | −4.16 → −3.28 | 28.4 → 25.0% | 30.2% |
| 2-day on | 2018+ | 47 | 2d | +1.38 → +0.84 | +0.53% | −4.64 → −3.76 | 31.9 → **34.0%** | 27.7% |
| 2-day on | 2010-17 | 48 | 3d | +2.11 → +1.48 | +0.61% | −2.60 → −2.29 | 16.7 → 14.6% | 35.4% |

Waiting for DEFEND to clear costs about 0.4–0.6% of upside and cuts average drawdown by 0.3–0.9 pp. That fits the "a bit late is fine" philosophy; this is the trade being made. The 2-day rule gives slightly more drawdown relief at the same cost (2007+), but in 2018+ the tail measure, P(MAE ≤ −5), got slightly worse. Small edge, not a big one.

**Failure cases (T3 "Leaving stocks" episodes since 2007, fwd20 / MAE20):** the rule caught 2008-09-15 (−15.60 / −26.31), 2020-02-25 (−22.23 / −28.69), 2018-12-13 (−3.00 / −11.69) and 2022-08-26 (−10.12 / −10.12). It also fired before many quick rebounds: 2011-09-30 (+13.65), 2009-02-23 (+10.14 after −8.76 first), 2015-09-28 (+10.10), 2022-11-09 (+5.91), 2025-04-03 (+5.60 after MAE −7.49). 2026-10-16 just resolved at −1.16 / −3.96. Of 66 episodes, 44 had a positive fwd20.

**What I'm proposing (PR):** (a) DEFEND only when a DEFEND trigger fired today AND yesterday. A first-day trigger appends a heads-up line to the headline (e.g. "DEFEND trigger today: credit5d; DEFEND if it holds tomorrow") but leaves the action as computed otherwise. (b) Headline changes from "protect what you have" to "No new adds until this clears. Not a sell signal on its own." Not proposed: any change to ADD/WAIT (live n=3 ADD), or to the trigger thresholds.

**Caveats:** the overlay is a cash-switch proxy, but the card's real meaning is "no adds", so CAGR numbers overstate the stakes. GEX-based ADD/WAIT can't be tested before 2026. SPY is price-only (no dividends) and cash earns nothing in the overlay; these two simplifications roughly offset. T2 already has its own 3-day persistence, so the 2-day rule mostly affects T1/T3. 2010–17 is the counter-era on max drawdown. Live evidence is 2 dropped single-day fires (one right, one wrong).

**Live check (signal_performance_log.csv through 11-13; event tracking through 11-13):**
- STRONG_BUY resolved: 5d n=20, 80.0% hit, +1.53%, worst −2.60%. 10d n=17, 76.5%, +1.96%, worst −3.86%. **20d n=14, 92.9%, +2.60%. First 20d loss: 10-16 STRONG_BUY at 761.68 → −1.01% (11-13).** 10-30 STRONG_BUY 10d −0.13%; 11-06 STRONG_BUY (735.40, comp 2.1) 5d +2.53%. BUY_WATCH 20d n=27, 74.1%, +0.92%; 10-14/10-15 BUY_WATCH 20d −1.83%/−1.49%.
- Event 2026-11-05 (day 6): early entries A/G 734.40 at +2.67%, max DD 0.0%. Confirmation B/C/F 753.01 at +0.13% (worst −0.42%). D/E (GEX > 0 / above zero gamma) 759.62 at −0.74%. Waiting for confirmation has cost 2.5–3.4% so far with no drawdown avoided. One event; consistent with P0/P1 and section 4 above (waiting is cheap on average but not free).
- Contradiction worth flagging: today's quick_action is WAIT on STRONG_BUY with defensive/cyclical 10d at +4.30% and SMH/SPY 10d −6.67%, but HYG/IEF 10d is +1.27, so not red. The flow-red rule requires credit, which is what protected against a false DEFEND here. The 11-11 GEX flip positive reversed on 11-12 (P7 trap repeated live).

## 2026-11-11 — P0: "rotation shakeout" flag (SMH/SPY 10d ≤ −6% AND RSP/SPY 10d ≥ +2.5%), properly validated

**VERDICT: inconclusive. Do not wire this in as a buy rule or a veto yet.** As a heads-up it does raise the odds of a near-term dip (a ≥3% drawdown within 10 days on 42.1% of fire days vs a 19.0% base). But the "shakeout, then bought" upside from the 11-05 first read only holds at the exact thresholds first picked, and it falls apart at neighboring ones. None of the three confirmation entries I tested improved the trade-off between waiting and drawdown. Credit (HYG/IEF) looks like the right thing to split on, but it rests on 4 episodes, 2 bad and 2 fine.

**Data and method** (`research/p0_rotation_shakeout.py`; raw output in `research/p0_rotation_shakeout_output.txt`, `p0_rotation_shakeout_results.json`):
- `flow_history.csv`, 1999-01-04 to 2026-11-10. The 11-11 row is an intraday partial bar and was dropped. Both legs exist from 2003-05-15, which gives 5,891 valid days with 20d forward data. SPY closes come from flow_history; they differ slightly from the tracker's (e.g. 11-05 733.00 vs 734.40).
- Fwd h = SPY close-to-close. MAE h = worst close in the next h days vs entry. Episode = first fire day of a cluster whose fire days are separated by >10 trading days. "Family" = the looser SMH ≤ −5 / RSP ≥ +1.5, used to get more episodes for the separator and confirmation tests.

**1. Rule R as specified (20d unless noted)**

| Scope | n | Dip ≥3% in 10d | Hit10 | Fwd10 | Hit20 | Fwd20 (med) | MAE20 | P(MAE20 ≤ −5%) |
|---|---|---|---|---|---|---|---|---|
| base 2003+ | 5891 days | 19.0% | 62.2% | +0.41 | 65.8% | +0.80 (+1.34) | −2.52 | 15.4% |
| R, day level | 19 days | 42.1% | 57.9% | +0.64 | 89.5% | +2.73 (+3.38) | −3.06 | 26.3% |
| R, episode level | 6 eps | 33.3% | 50.0% | −0.03 | 83.3% | +1.84 (+2.26) | −3.01 | 33.3% |
| R 2018+, day level (base 2018+: 20.9% / 66.7% / +1.03 / 17.8%) | 17 days | 41.2% | 58.8% | +0.96 | 88.2% | +2.76 | −2.98 | 29.4% |

Fire rate: 30 days (0.51% of valid days), 7 episodes. The 7th (2026-10-16) is still open. By era: 2 fire days in 2003–09, **0 in 2010–17**, 17 in 2018+. In practice this is a post-2018 pattern, and "by era" can't be checked any further than that.
Episodes (fwd5/10/20, MAE10/20): 2009-05-08 −4.59/−4.26/+1.27, −4.62/−4.62 · 2021-03-04 +4.47/+3.92/+6.35, +1.33/+1.33 · 2024-07-19 −0.83/−2.93/+0.97, −2.93/**−5.76** · 2024-09-04 +0.63/+1.90/+3.25, −1.92/−1.92 · **2025-03-03 −3.97/−2.85/−4.18, −5.54/−5.54** · 2026-07-28 +4.11/+4.01/+3.38, −1.54/−1.54 · 2026-10-16 (open): −3.96% max drawdown to the 11-05 close.

**2. Threshold sensitivity, episode level (the key result).** Fwd20 is above base only in the RSP ≥ +2.5 / SMH ≤ −6 or −7 corner (+1.84) and at RSP ≥ +3.5 (n=2). The neighbors are flat or negative: SMH −4/RSP 2.5: −0.46 (MAE20 −4.71); −5/2.5: −0.17 (−4.28); −6/1.5: −0.55 (−4.09); −7/1.5: −1.36 (−4.73). SMH weakness alone: +0.25 to +1.19, roughly base, with worse MAE (−2.7 to −3.9). So the upside is a cherry-picked corner. The dip-risk side is more stable: at day level, a ≥3% dip within 10d occurs on 27–48% of fire days across every combo vs 19% base. (At episode level it ranges 0–62.5%, noisy.)

**3. What separates the bad cases (family, 15 episodes)**
- HYG/IEF 10d ≤ −1 at the flag: 2 episodes (2008-09-05, 2025-02-27), both bad: fwd20 −7.19, MAE20 −8.53. HYG/IEF > −1: 13 episodes, hit20 84.6%, fwd20 +1.95, MAE20 −2.22, P(MAE20 ≤ −5) 15.4%, the same as base.
- Day-level robustness: family & HYG/IEF 10d ≤ −0.5: 19 days, hit20 42.1%, fwd20 −3.08, P(MAE20 ≤ −5) 52.6%, vs credit selling alone (any day 2007+) at 62.5% / +0.76 / 22.8%. The rotation-plus-credit combination looks worse than credit alone. **But those 19 days are just 4 episodes:** 2008-09 ✗, 2025-03 ✗, and 2024-08 (yen unwind, fwd20 +2.8 to +6.7) ✓ and 2024-09 ✓. So the split is 2-for-4, and it is a hypothesis, not a rule.
- SPY 10d ≤ −3% at the flag: 3 episodes, hit20 33.3%, fwd20 −2.00. SPY already ≥5% off its 60d high: 5 episodes, fwd20 −1.33. Both small n.
- Worst family cases by MAE20: 2008-09-05 −11.32, 2022-04-11 −9.49 (credit calm, −0.11, so credit would *not* have caught it), 2024-07-18 −6.38, 2025-02-27 −5.75.

**4. Heads-up, then wait for confirmation?** All 15 family episodes, common endpoint flag + 30d. The confirmation definitions were fixed before I looked at results.
- Early entry at the flag close: avg −1.09% (median +1.24%), avg MAE −5.93%, P(MAE ≤ −5%) 40.0%. The family as a whole is not a buy signal over 30 days.
- C1 "semis back" (SMH/SPY 5d > 0): confirmed 15/15, median lag 6d, entry +0.41% above the flag. End −1.60 vs early −1.09; MAE −5.33 vs −5.93; P(MAE ≤ −5) 40% vs 40%. **No drawdown avoided, small cost.**
- C2 "trend back" (SPY > SMA10): 15/15, lag 3d, entry +1.07% above. End −2.15 vs −1.09; MAE −6.34 vs −5.93. **Worse on both sides.**
- C3 "dip ≥2% then +1% up day": 9/15, lag 7d, entry −1.29% below the flag. On those 9: end −2.95 vs early −4.16, MAE −7.09 vs −8.87. But the 6 episodes it never entered averaged +3.52% early, so across all 15 C3 nets about −1.77% vs early −1.09%. It buys the dips that keep going and misses the ones that don't.
- Conclusion: none of these confirmations is "whale confirmation". When SMH/SPY turns back up for 5 days, that does not tell you institutions are back.

**What this means for the live rules (feeds P8):** the Oct 16–26 STRONG_BUY cluster (761.68–763.86) fired while R was ON *and* HYG/IEF 10d was −1.48 to −2.04, which is the 2008-09 / 2025-03 subgroup. Those entries were −3.7% to −3.9% by 11-05. By 11-04 to 11-10, R is on again but HYG/IEF 10d is only −0.34 to −0.87, so credit is not confirming. A "rotation AND credit selling" veto on STRONG_BUY would have blocked the Oct cluster. But historically it would also have blocked the Aug-2024 rebound (+5.5–6.7% over 20d). It should be tested as P8(b), with fire-rate cost, not wired in from this run.

**Caveats:** n=6 episodes for R and 15 for the family; 0 fires in 2010–17; overlapping windows inflate day-level n; the 11-05 first-read numbers (42% dip / median +3.4%) reproduced at day level (42.1% / +3.38%), but the episode-level and sensitivity views are much weaker; the GEX leg is not in flow_history.

**Live check (signal_performance_log.csv through 11-10; event tracking_log through 11-10):**
- Resolved STRONG_BUY: 5d n=19, 78.9% hit, +1.47%, worst −2.60%. 10d n=16, 81.2%, +2.09%, worst −3.86%. 20d n=13, 100%, +2.88%, worst +1.00% (the 20d bucket has not reached the Oct fires yet). BUY_WATCH: 5d n=29, 55.2%, +0.42%; 10d n=29, 65.5%, +0.27%, worst −4.19%; 20d n=25, 80.0%, +1.13%.
- Newly resolved since 11-07: 10-26 STRONG_BUY 10d −1.26%; 11-02 STRONG_BUY 5d +0.14%; 11-03 STRONG_BUY 5d −0.63%. The Oct cluster's 10d outcomes are −0.88, −3.86, −1.26 (10-16/22/26). The 20d outcomes resolve 11-13 to 11-24.
- Event (day 3, 11-10): STABILIZING, 4/6 stabilization, 0/6 escalation. Early entries A/G (734.40) +2.11%. Confirmation entries B/C/F (753.01) −0.42%. Here the cost of waiting for confirmation was 2.5%, and it bought no drawdown protection because the trigger close was the low (max DD after A = 0.0%). That matches the P1 finding (waiting costs ~1–2%) and the C1/C2 results above. One event, so a hypothesis.
- Contradiction worth flagging: `regime_signal` went STRONG_BUY on 11-06 and 11-10 while rule R was ON (SMH/SPY 10d −9.0 / −11.0, RSP/SPY +3.1 / +4.2). The 11-10 STRONG_BUY came at composite 4.7 and VIX 19.5, the same profile as the Oct losers. Credit is calmer this time (HYG/IEF 10d −0.44 vs −1.5 to −2.0 in Oct). The 11-11 intraday print (~762, partial bar, not used in any number above) is above both entries.

## 2026-11-07 — P1: STRONG_BUY macro gate with vol_score removed (composite-ex-vol >= 1 vs composite >= 1)

**VERDICT: rejected. Keep the current `composite >= 1` gate.** Removing vol_score from the gate adds a small number of coin-flip setups with roughly double the drawdown risk. The vol leg is not a useful confirmation step either: waiting for it costs about 1.2% and does not reduce drawdown. Neither version of the gate explains the live Oct 16–Nov 3 losers. Those fired with composite 4.5–4.7, far above either threshold.

**Why P1 before P0:** the mission names P1 explicitly, and P1 is the direct question raised on 11-05 ("the gate penalizes the panic STRONG_BUY is meant to buy"). P0/P0b are still open and come next.

**Data and method** (`research/p1_vol_gate.py`, `research/p1_confirmation_wait.py`; raw output is in `research/*_output.txt` and `p1_vol_gate_results.json`):
- `deep_history_backtest_log.csv`, 7,762 days, 1995-10-17 to 2026-08-21. GEX has no history, so the setup is the non-GEX legs of STRONG_BUY: RSI<50 (the backtest's own simple 14-day RSI), SKEW>138, VIX>17. This is a proxy. The live rule also needs GEX < −10B.
- vol_score is not stored in the log. I recovered it exactly as (composite − 1.5·credit − flow − growth − skew)/1.2, with the other legs taken from regime_analyzer's own `score_*` functions. 1,278 rows could not be recovered because composite was clamped at +8. 16 of those are setup days, but all have ex-vol ≥ 6, so they land in the same group under both gates and no classification changes.
- Groups among setup days: **A** = current gate passes (comp ≥ 1). **B** = blocked *only* by vol (comp < 1 but ex-vol ≥ 1); this is the group the proposal would add. **C** = blocked by non-vol legs (ex-vol < 1). **NEW** = A + B. Forward return and MAE come from SPY closes. MAE = worst close within the next h days vs the entry close. Episode = first day of a cluster of fire days separated by more than 10 trading days.
- **by_era:** SKEW > 138 occurred on only 2 days before 2010, so the setup never fires pre-2010. In practice this is a post-2010 rule. Pooled "full" ≈ 2010+.

**Results, 20-day horizon, day level** (base = all days in the same era):

| Era | Group | Days (% of days) | Episodes | Hit | Avg fwd | Avg MAE | P(MAE ≤ −3%) |
|---|---|---|---|---|---|---|---|
| full | base | 7762 | – | 63.8% | +0.77% | −2.75% | 34.5% |
| full | A current gate | 147 (1.89%) | 35 | 68.5% | +1.34% | −2.66% | 35.0% |
| full | **B vol-only block** | 16 (0.21%) | 9 | **50.0%** | +0.88% | **−3.98%** | **62.5%** |
| full | C non-vol block | 26 (0.33%) | 10 | 80.8% | +2.00% | −2.28% | 26.9% |
| full | NEW ex-vol gate | 160 (2.06%) | 34 | 66.7% | +1.29% | −2.75% | 37.8% |
| 2018+ | base | 2171 | – | 67.2% | +1.06% | −2.69% | 33.2% |
| 2018+ | A current gate | 137 (6.31%) | 29 | 69.2% | +1.42% | −2.61% | 33.1% |
| 2018+ | B vol-only block | 13 (0.60%) | 6 | 53.8% | +1.14% | −4.12% | 61.5% |
| 2018+ | NEW ex-vol gate | 147 (6.77%) | 28 | 67.8% | +1.40% | −2.70% | 35.7% |
| 2010–17 | A current gate | 10 | 6 | 60.0% | +0.30% | −3.26% | 60.0% |
| 2010–17 | B vol-only block | 3 | 3 | 33.3% | −0.29% | −3.37% | 66.7% |

At 10 days the picture is the same: B hit 50.0%, MAE −2.65%, P(MAE ≤ −3%) 50.0%, vs A at 59.2% / −1.87% / 27.2% (full). At the episode level (20d, full), NEW looks a bit better than A (79.4% / +1.83% / MAE −1.83% vs 77.1% / +1.33% / −2.30%), but that is 34 vs 35 episodes differing by a handful, and B's own episodes hit only 55.6% (5/9).

**The 9 B episodes (the days the proposal would turn into STRONG_BUY), fwd20 / MAE20:** 2015-12-11 −4.07/−4.93 ✗; 2016-01-08 −3.39/−3.39 ✗; 2016-06-24 (Brexit) +6.60/−1.79 ✓; 2022-04-27 −4.77/−6.66 ✗; 2024-08-05 (yen unwind) +6.71/+0.25 ✓; 2024-10-31 +5.96/+0.21 ✓; 2025-03-03 −4.18/−5.54 ✗; 2025-04-03 +5.60/**−7.49** ✓ (eventually); 2026-03-27 +12.79/−0.33 ✓. All 4 failures were VIX 22.8–31.6 days in an ongoing decline (2015-16 and 2022 bear legs, early Mar-2025). The wins include sharp one-off shocks (Brexit, Aug-2024 yen unwind, Apr-2025 tariffs) at similar VIX levels (23.2–38.6). The ex-vol composite cannot tell these apart: 2.0–3.0 for the failures vs 1.5–3.5 for the wins.

**Is the vol gate a useful "wait for confirmation" step? No.** For the 9 B episodes, waiting for the first later day with comp ≥ 1 took 1–13 days (all 9 confirmed within 20). Median cost of waiting was +1.56% (mean +1.21%). Mean MAE20 was −3.30% entering early vs −3.29% entering on confirmation, so no drawdown was avoided. To a common endpoint (blocked day + 20), early averaged +2.36% vs late +1.15%. The failures (2015-12, 2022-04, 2025-03) kept falling after confirmation, with late MAE −7.9%, −9.2% and −12.5%. A one-notch VIX drop is not confirmation of institutional buying.

**Side finding (not tested properly, logged as a backlog idea):** RSI depth matters more than the vol gate. 2018+, group A with RSI < 40: 52 days / 17 episodes, 20d hit 88.2%, avg +3.18%, MAE −2.03%, vs RSI < 50 at 69.2% / +1.42% / −2.61%. Without GEX, A at RSI < 50 is only marginally better than base (69.2% vs 67.2% hit), so in the live rule GEX < −10B and/or RSI depth must be doing most of the work.

**Caveats:** GEX leg missing (proxy setup); n(B) = 9 episodes; the deep log ends 2026-08-21, so the Nov-2026 event is outside it; the RSI method (simple average) may differ slightly from the live tracker's; overlapping 20-day windows at day level inflate apparent n.

**Live check (signal_performance_log.csv, resolved through 2026-10-30; tracking data through 11-06):**
- Resolved STRONG_BUY: 5d n=17, 82.4% hit, +1.67%, worst −2.60%; 10d n=15, 86.7%, +2.31%, worst −3.86%; 20d n=13, 100%, +2.88%. BUY_WATCH: 5d n=29, 55.2%, +0.42%; 10d n=29, 65.5%, +0.27%, worst −4.19%; 20d n=25, 80.0%, +1.13%.
- The first losses have resolved: 10-22 STRONG_BUY 10d −3.86%; 10-26 5d −1.40%; 10-30 5d −2.60%; 10-23 BUY_WATCH 10d −4.19%.
- Every STRONG_BUY from 10-16 to 11-03 (7 fires, SPY 751.96–763.86) is underwater against 11-06's 735.40, from −2.20% to −3.73%, with worst close −2.34% to −3.86%. **All 7 had composite 4.5–4.7 (vol_score 0 to +1), so neither gate version would have blocked them.** They fired at moderate VIX (18.4–21.2) and repeatedly over 3 weeks while price drifted lower and SMH/SPY was breaking down (P0). That is "early", not "confirmed", and it contradicts the philosophy more than the vol gate does. This is the real accuracy gap: see new backlog item P8.
- 11-05 was a B day (comp 0.9, ex-vol 4.5, GEX −19.4B, RSI 35.5) at 734.40. The current gate passed on 11-06 at 735.40 (comp 2.1). Cost of the one-day delay so far: +0.14%. Event state UNRESOLVED, 0/6 escalation, 0/6 stabilization, and no confirmation entry rule has fired yet.
- Note: `signal_performance_summary.json` still only reports hit rate and average return (no MAE); that is P2.

## 2026-11-01 — Idea #8 (ROC early-warning layer): independent re-test on deep-history data

**VERDICT: inconclusive — NOT ready for review; wiring into regime_analyzer.py not done.**

**Setup problems (stated plainly):**
- `claude/gex-tracker-notes.md` does not exist on this branch or on main, so the 2026-08-25 ROC validation record and any "already wired" status could not be read. `grep` finds no `composite_5d_chg` / `hyg_5d_pct` anywhere in the repo, so the layer is not wired into `regime_analyzer.py` (it only has `hyg_5d_change`).
- Sandbox egress allowlist blocks Yahoo, FRED and cftc.gov (HTTP 403 from proxy). Ideas 1, 3, 4, 5 (VIX3M), 7 cannot be tested here. Not faked.
- `macro_history.csv` ends 2026-08-17 and `deep_history_backtest_log.csv` ends 2026-08-21, so there is nothing newer than ~10 weeks old to evaluate.

**What was tested:** definitions reconstructed from the names: `composite_5d_chg` = 5-day change in composite_score; `hyg_5d_pct` = 5-day % change in HYG. Event = SPY falls >=8% (close to the min of the next 20 trading days). Source: `deep_history_backtest_log.csv`, 7762 days, 1995-10-17 to 2026-08-21; HYG exists only from 2007-04-11. Fire counts are days; clusters = fires separated by >30 days.

| Era | Trigger | Days fired | Clusters | P(event \| fire) | Base rate |
|---|---|---|---|---|---|
| full | composite_5d_chg <= -3 | 265 (3.4%) | 79 | 15.8% | 8.0% |
| full | hyg_5d_pct <= -2 | 247 (5.1%) | 37 | 24.7% | 8.2% |
| 2010+ | composite_5d_chg <= -3 | 195 (4.7%) | 57 | 12.3% | 6.2% |
| 2010+ | hyg_5d_pct <= -2 | 151 (3.6%) | 27 | 15.2% | 6.2% |
| 2020+ | composite_5d_chg <= -3 | 103 (6.2%) | 28 | 18.4% | 8.1% |
| 2020+ | hyg_5d_pct <= -2 | 64 (3.8%) | 8 | 29.7% | 8.1% |
| 2020+ | both (c5<=-3 & h5<=-1) | 55 (3.3%) | 16 | 25.5% | 8.1% |

(Other thresholds -2/-4 and -1/-1.5 were run too; same direction.)

**Findings:**
- Real but modest lift: a fire raises P(>=8% drop in next 20d) about 1.5-3x over base. But 70-88% of fires are NOT followed by such a drop (false-positive rate by this definition), and the 2010+ lift is weaker than full-history (pooled-vs-recent check: lift shrinks, e.g. 15.8% -> 12.3%).
- Lead time in the two benchmark crashes is poor. COVID: composite_5d_chg first hit -7.1 on 2026-02-26 (SPY 311.5 vs ~337 on 02-20, already ~-7.6% off the high); hyg_5d_pct did not reach -1 until 2020-03-09 (SPY 274). 2025: composite_5d_chg was -2.4 on 02-24 and -2.2 on 03-06 (SPY 597 / 573 vs 611 on 02-18), HYG 5d never below about -1.4% until 04-03, i.e. after the low-volatility drop was under way. These are coincident-to-slightly-leading, not early.
- Fires also precede positive average 20d returns (avg fwd20 +1.77% for c5<=-3 vs +0.77% unconditional full history): the signal catches sharp dips that often bounce, so it is not a de-risk signal by itself, and is not a bottom signal either (bottom/risk-on turn was not tested this run).
- Caveat: event definition and thresholds are mine, not the 08-25 validation's; I cannot say whether that validation used a different target. Differences vs it should be reconciled once the notes are restored.

**Next:** restore notes file; wire columns as live-accumulating (do not use for sizing yet).

**New backlog items added:** see IDEA_BACKLOG.md (3).
