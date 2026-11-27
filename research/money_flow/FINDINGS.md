# Cross-asset money flow: does it help take risk off or put it on?

Principle (Simon, 2026-11-28): nothing goes on the dashboard just because it's interesting. It has to show where money is moving across assets and be tested for whether it helps de-risk or add risk. Untested items are labelled informational.

## Method (`flow_study.py`; daily read in `money_flow.py`)
- **8 flow pairs**, each the 60-session relative return of a risk asset vs a safety asset: stocks vs bonds (SPY/TLT), stocks vs gold (SPY/GLD), junk vs Treasuries (HYG/IEF), cyclicals vs defensives (XLY+XLK / XLU+XLP), copper vs gold, the dollar (inverted UUP), small vs large caps (IWM/SPY), EM vs US (EEM/SPY).
- **No look-ahead:** each pair is z-scored against its own past 2 years only. The **risk appetite score** is the average, ranked against its own past (percentile). Weights are equal and untuned.
- **Window:** 2010-02 → 2026-11, 4,101 days.

## Results
| Score quintile | SPY median 120d | Up after 120d | 10%+ drop within 120d |
|---|---|---|---|
| All days | +6.6% | 79.0% | 20.5% |
| Bottom 20% (money to safety) | +5.9% | 74.3% | **30.1%** |
| 20–40% | +4.6% | 67.3% | 26.0% |
| 40–60% | +6.5% | 83.7% | 17.3% |
| 60–80% | +8.0% | 88.5% | 10.9% |
| Top 20% (money to risk) | +8.9% | 86.8% | **12.2%** |

Held in both eras. Chance of a 10%+ drop, bottom 20% vs top 20%: 23.5% vs 8.4% in 2009–17, and 39.5% vs 15.3% in 2018+.

**Taking risk off:**
- **SPY near its high + score in the bottom 20%:** a 10%+ drop followed 35.2% of the time vs 20.7% on other near-high days (median 120d +3.0% vs +5.9%). But halving exposure only on those days didn't help (CAGR 11.96% vs 12.07%, same max drawdown), because Feb 2020 wasn't flagged.
- **Score in the bottom 20% at any time:** halving exposure cut max drawdown from −34.1% to **−24.1%** for about 1 pt/yr (11.1% vs 12.1% CAGR). That's a real trade-off, not a free lunch.

**Putting risk on:**
- **Trigger:** SPY 8%+ below its high and the score up 0.5+ over 20 sessions, meaning money rotating back toward risk.
- **History:** the first signal per drop came *after* the low each time: 2010-07, 2011-10, 2019-01, 2020-04, 2022-05 and 2025-05. Median +15.6% over 120 days, 5 of 6 up. 2022 was early: the bear market went on to October.
- **What it is:** the "not first, not last" confirmation, a reason to add beyond the single buy, or to add TQQQ at full size.

## How it's used (dashboard, Quick Action, Telegram)
- **Score level:** a risk thermometer. In the bottom 20%, be patient: no adds beyond the plan, and expect more downside. In the top 20%, the backdrop is normal or supportive.
- **Risk-on trigger:** confirmation to add more risk during a drawdown.
- **Optional rule (Simon's call):** half size while the score is in the bottom 20%. It cut drawdowns but cost about 1 pt/yr.

## Caveats
- One window (2010+, since every series needs history); only 6 risk-on signals.
- Asset relationships change. Stocks vs bonds behaved differently in 2022, when both fell.
- The research agent tracks it forward (backlog P0g).
