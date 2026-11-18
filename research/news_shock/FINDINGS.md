# News shock study — findings

Built 2026-11-16T04:01:15+00:00 from `shock_events.csv` (6163 shock days in current S&P 500 members since 2010).
Shock day = stock down ≥6% close-to-close, ≥5 points worse than SPY, volume ≥1.5x its 50-day average.
Outcome = stock return minus SPY return over the next 60 trading days. "Beat SPY" = that number > 0.
Weights learned on shocks before 2019-01-01; every result below is graded on 2019+ shocks the model never saw.
Survivorship bias: only TODAY's index members are included, so companies that collapsed and dropped out are missing. Absolute recovery rates are too optimistic; the comparisons between factors are more trustworthy.

## At the shock-day close (t0)

Train n=2297, test n=3689. Beat-SPY base rate: train 54.7%, test 48.6%. AUC train 0.581, **test 0.553** (0.5 = coin flip).

| Score band (test set) | n | Beat SPY over 60d | Median excess return | Median worst point, next 20d |
|---|---|---|---|---|
| 1 (lowest) | 439 | 39.4% | -2.74% | -4.65% |
| 2  | 567 | 47.1% | -0.7% | -4.36% |
| 3  | 709 | 46.1% | -1.81% | -5.16% |
| 4  | 878 | 48.3% | -0.64% | -4.96% |
| 5 (highest) | 1096 | 54.8% | 2.07% | -6.77% |

Weights (standardized; + means more likely to recover):

| Factor | Weight |
|---|---|
| Opening gap | +0.215 |
| Market in an uptrend | -0.107 |
| VIX (market fear) | +0.105 |
| Run-up in the 60 days before | +0.093 |
| Drop vs the market that day | -0.075 |
| Distance from 52-week high before | -0.073 |
| Size of the drop | -0.068 |
| Was in an uptrend (above 200-day) | -0.066 |
| Volume vs normal | +0.030 |
| Market's 20-day trend | -0.030 |
| Closed off the lows (buyers stepped in) | +0.029 |
| Market's own move that day | +0.009 |

Top vs bottom band by year (test set, % that beat SPY):

| Year | Top band | Bottom band |
|---|---|---|
| 2019 | 50.0% (n=24) | 36.9% (n=65) |
| 2020 | 58.5% (n=381) | 48.1% (n=27) |
| 2021 | 43.5% (n=23) | 38.7% (n=31) |
| 2022 | 54.5% (n=382) | 25.0% (n=4) |
| 2023 | 41.0% (n=78) | 39.7% (n=63) |
| 2024 | 52.9% (n=17) | 40.3% (n=119) |
| 2025 | 53.7% (n=134) | 35.1% (n=74) |
| 2026 | 61.4% (n=57) | 42.9% (n=56) |

## After waiting 3 days for confirmation (t3)

Train n=2297, test n=3685. Beat-SPY base rate: train 57.3%, test 50.5%. AUC train 0.576, **test 0.535** (0.5 = coin flip).

| Score band (test set) | n | Beat SPY over 60d | Median excess return | Median worst point, next 20d |
|---|---|---|---|---|
| 1 (lowest) | 593 | 49.2% | -0.35% | -5.5% |
| 2  | 702 | 46.3% | -1.43% | -5.12% |
| 3  | 711 | 48.4% | -0.7% | -4.55% |
| 4  | 625 | 49.4% | -0.21% | -4.22% |
| 5 (highest) | 1054 | 56.0% | 2.66% | -6.54% |

Weights (standardized; + means more likely to recover):

| Factor | Weight |
|---|---|
| Run-up in the 60 days before | +0.144 |
| Market in an uptrend | -0.126 |
| Opening gap | +0.126 |
| Volume vs normal | +0.118 |
| Distance from 52-week high before | -0.114 |
| VIX (market fear) | +0.055 |
| Size of the drop | -0.039 |
| Drop vs the market that day | -0.038 |
| Bounce in the 3 days after | +0.037 |
| Market's 20-day trend | -0.036 |
| Market's own move that day | -0.030 |
| Closed off the lows (buyers stepped in) | +0.028 |
| Undercut the shock-day low within 3 days | -0.012 |
| Was in an uptrend (above 200-day) | +0.001 |

Top vs bottom band by year (test set, % that beat SPY):

| Year | Top band | Bottom band |
|---|---|---|
| 2019 | 62.9% (n=35) | 48.6% (n=70) |
| 2020 | 63.1% (n=339) | 50.0% (n=34) |
| 2021 | 40.7% (n=27) | 58.5% (n=65) |
| 2022 | 55.9% (n=354) | 46.7% (n=15) |
| 2023 | 39.2% (n=79) | 45.1% (n=71) |
| 2024 | 29.6% (n=27) | 45.4% (n=130) |
| 2025 | 57.1% (n=140) | 49.5% (n=103) |
| 2026 | 49.1% (n=53) | 51.4% (n=105) |

## Mag 7 (AAPL, MSFT, NVDA, AMZN, GOOGL/GOOG, META, TSLA)

147 shocks. Beat SPY over 60 days 56.5% (median +0.99%), over 120 days 64.5% (median +6.72%). Median worst point in the next 20 days -5.25%. The general score does **not** rank Mag 7 shocks (AUC 0.529 within Mag 7), so they are judged on this track record instead. Survivorship bias is strongest here: these are, by definition, today's biggest winners.

## Each factor on its own (all years, quintiles)

**Size of the drop** (`drop_pct`)

| Bucket | n | Beat SPY 60d | Median excess |
|---|---|---|---|
| ≤-11.75 | 1196 | 56.4% | 2.38% |
| -11.75–-9.06 | 1197 | 49.5% | -0.08% |
| -9.06–-7.70 | 1195 | 48.1% | -0.64% |
| -7.70–-6.77 | 1197 | 50.9% | 0.24% |
| -6.77+ | 1201 | 49.8% | -0.02% |

**Drop vs the market that day** (`excess_pct`)

| Bucket | n | Beat SPY 60d | Median excess |
|---|---|---|---|
| ≤-10.83 | 1192 | 53.8% | 1.54% |
| -10.83–-8.46 | 1195 | 48.1% | -0.4% |
| -8.46–-7.20 | 1203 | 49.0% | -0.27% |
| -7.20–-6.22 | 1194 | 51.0% | 0.22% |
| -6.22+ | 1202 | 52.7% | 1.01% |

**Market's own move that day** (`spy_day_pct`)

| Bucket | n | Beat SPY 60d | Median excess |
|---|---|---|---|
| ≤-1.42 | 1192 | 56.9% | 2.87% |
| -1.42–-0.56 | 1184 | 49.7% | -0.06% |
| -0.56–-0.09 | 1185 | 47.7% | -0.98% |
| -0.09–0.39 | 1213 | 49.1% | -0.18% |
| 0.39+ | 1212 | 51.3% | 0.46% |

**Volume vs normal** (`vol_ratio`)

| Bucket | n | Beat SPY 60d | Median excess |
|---|---|---|---|
| ≤1.99 | 1183 | 54.7% | 2.17% |
| 1.99–2.63 | 1192 | 50.9% | 0.22% |
| 2.63–3.53 | 1213 | 50.1% | 0.02% |
| 3.53–5.15 | 1197 | 49.3% | -0.09% |
| 5.15+ | 1201 | 49.7% | -0.08% |

**Opening gap** (`gap_pct`)

| Bucket | n | Beat SPY 60d | Median excess |
|---|---|---|---|
| ≤-8.26 | 1196 | 51.5% | 0.51% |
| -8.26–-5.37 | 1197 | 48.5% | -0.37% |
| -5.37–-3.03 | 1194 | 49.9% | -0.02% |
| -3.03–-0.85 | 1199 | 51.5% | 0.5% |
| -0.85+ | 1200 | 53.3% | 1.41% |

**Closed off the lows (buyers stepped in)** (`close_loc`)

| Bucket | n | Beat SPY 60d | Median excess |
|---|---|---|---|
| ≤0.05 | 1194 | 51.9% | 0.83% |
| 0.05–0.11 | 1194 | 51.7% | 0.8% |
| 0.11–0.20 | 1193 | 52.5% | 0.72% |
| 0.20–0.38 | 1195 | 50.0% | 0.0% |
| 0.38+ | 1197 | 48.6% | -0.47% |

**Run-up in the 60 days before** (`pre60_pct`)

| Bucket | n | Beat SPY 60d | Median excess |
|---|---|---|---|
| ≤-11.39 | 1197 | 61.6% | 4.44% |
| -11.39–-1.94 | 1197 | 46.4% | -1.15% |
| -1.94–5.64 | 1197 | 49.2% | -0.23% |
| 5.64–16.18 | 1197 | 46.4% | -0.96% |
| 16.18+ | 1198 | 51.0% | 0.6% |

**Was in an uptrend (above 200-day)** (`above_200ma`)

| Bucket | n | Beat SPY 60d | Median excess |
|---|---|---|---|
| 0 | 2479 | 54.0% | 1.57% |
| 1 | 3507 | 48.8% | -0.37% |

**Distance from 52-week high before** (`off_52w_high_pct`)

| Bucket | n | Beat SPY 60d | Median excess |
|---|---|---|---|
| ≤-29.50 | 1197 | 57.9% | 3.73% |
| -29.50–-17.76 | 1196 | 52.9% | 1.1% |
| -17.76–-9.55 | 1198 | 49.2% | -0.24% |
| -9.55–-3.29 | 1196 | 48.0% | -0.61% |
| -3.29+ | 1199 | 46.7% | -0.93% |

**Market's 20-day trend** (`spy_20d_pct`)

| Bucket | n | Beat SPY 60d | Median excess |
|---|---|---|---|
| ≤-3.77 | 1196 | 56.7% | 2.39% |
| -3.77–-0.32 | 1183 | 51.4% | 0.61% |
| -0.32–1.71 | 1212 | 49.3% | -0.26% |
| 1.71–3.48 | 1196 | 48.6% | -0.42% |
| 3.48+ | 1199 | 48.7% | -0.29% |

**Market in an uptrend** (`spy_above_200ma`)

| Bucket | n | Beat SPY 60d | Median excess |
|---|---|---|---|
| 0 | 1611 | 56.7% | 2.32% |
| 1 | 4375 | 48.8% | -0.39% |

**VIX (market fear)** (`vix`)

| Bucket | n | Beat SPY 60d | Median excess |
|---|---|---|---|
| ≤14.46 | 1188 | 49.2% | -0.17% |
| 14.46–17.05 | 1205 | 48.1% | -0.76% |
| 17.05–20.34 | 1194 | 45.7% | -1.33% |
| 20.34–26.09 | 1198 | 53.7% | 1.4% |
| 26.09+ | 1201 | 57.9% | 3.05% |

**Bounce in the 3 days after** (`t3_pct`)

| Bucket | n | Beat SPY 60d | Median excess |
|---|---|---|---|
| ≤-3.80 | 1196 | 59.1% | 3.7% |
| -3.80–-1.00 | 1193 | 53.7% | 1.55% |
| -1.00–1.14 | 1194 | 50.5% | 0.1% |
| 1.14–3.92 | 1202 | 50.9% | 0.24% |
| 3.92+ | 1197 | 51.2% | 0.36% |

**Undercut the shock-day low within 3 days** (`new_low_3d`)

| Bucket | n | Beat SPY 60d | Median excess |
|---|---|---|---|
| 0 | 1914 | 50.3% | 0.07% |
| 1 | 4068 | 54.4% | 1.56% |

## SEC 8-K event type: not yet available

SEC blocks requests from GitHub Actions servers, so event type (earnings / leadership / restatement / no filing) and revenue trend are not in this build. See README for how to add them.

