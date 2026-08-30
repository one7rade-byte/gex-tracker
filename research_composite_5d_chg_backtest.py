"""
Ad-hoc research script (weekly research cycle) — NOT part of the production pipeline.
Tests: does the 5-day rate-of-change (ROC) of HYG and composite_score give earlier /
better crash warning than the composite_score LEVEL alone (current regime_analyzer.py
scoring)? This directly tests the "ROC early-warning layer" referenced in the research
mission — no such layer exists yet in this repo, so this builds it from scratch.
"""
import pandas as pd
import numpy as np

df = pd.read_csv('deep_history_backtest_log.csv', parse_dates=['date'])
df = df.sort_values('date').reset_index(drop=True)

# Restrict to where HYG actually exists (ETF launched April 2007)
df = df[df['date'] >= '2007-04-11'].reset_index(drop=True)

df['hyg_5d_pct'] = df['hyg'].pct_change(5) * 100
df['composite_5d_chg'] = df['composite_score'].diff(5)

# forward SPY return over next 20 trading days (recompute directly, don't trust file's
# return_20d near the end where it's NaN, and to be explicit about method)
df['fwd_ret_20d'] = df['spy_close'].shift(-20) / df['spy_close'] - 1
df['fwd_ret_10d'] = df['spy_close'].shift(-10) / df['spy_close'] - 1

# rolling max drawdown over the NEXT 20 trading days (captures a crash even if it
# partially recovers by day 20 — a simple fwd_ret_20d can miss a sharp intra-window drop)
def fwd_min_dd(spy, horizon=20):
    n = len(spy)
    out = np.full(n, np.nan)
    for i in range(n - horizon):
        window = spy[i+1:i+1+horizon]
        out[i] = window.min() / spy[i] - 1
    return out

df['fwd_maxdd_20d'] = fwd_min_dd(df['spy_close'].values, 20)

print("=== Sample sizes ===")
print("Total rows (HYG-valid era):", len(df))
print("hyg_5d_pct non-null:", df['hyg_5d_pct'].notna().sum())
print()

# ---------------------------------------------------------------------------
# 1. Known crash episodes: does a ROC threshold fire BEFORE / near the start,
#    with real lead time vs the crash's own peak date?
# ---------------------------------------------------------------------------
episodes = {
    '2008_GFC':   ('2007-10-09', '2009-03-09'),   # SPY ATH pre-GFC to GFC trough
    '2020_COVID': ('2020-02-19', '2020-03-23'),   # SPY ATH to COVID trough
    '2022_BEAR':  ('2022-01-03', '2022-10-13'),   # SPY ATH to 2022 trough
    '2025_SELLOFF': ('2025-02-19', '2025-04-08'), # SPY ATH to tariff-selloff trough
}

THRESH = -3.0  # hyg_5d_pct <= -3% (a 3% drop in HYG over 5 trading days)

print(f"=== Lead time to first hyg_5d_pct <= {THRESH}% signal, per known crash ===")
for name, (peak, trough) in episodes.items():
    peak_d = pd.Timestamp(peak)
    trough_d = pd.Timestamp(trough)
    window = df[(df['date'] >= peak_d - pd.Timedelta(days=10)) & (df['date'] <= trough_d)]
    fired = window[window['hyg_5d_pct'] <= THRESH]
    if fired.empty:
        print(f"{name}: NEVER fired hyg_5d_pct<= {THRESH}% between {peak_d.date()} and {trough_d.date()} -- MISS")
        continue
    first_fire = fired.iloc[0]
    # trading-day lead time: fire date vs peak date (negative = fired before the top)
    days_from_peak = (df['date'] == first_fire['date']).idxmax() - (df['date'] >= peak_d).idxmax()
    print(f"{name}: first fired {first_fire['date'].date()} (hyg_5d_pct={first_fire['hyg_5d_pct']:.2f}%), "
          f"{days_from_peak} trading days after the SPY peak ({peak_d.date()}), "
          f"{(trough_d - first_fire['date']).days} calendar days before the trough ({trough_d.date()})")

# Same test using composite_score LEVEL dropping into "stress" (<=-1) per regime_analyzer.py doc
print()
print("=== Same test using composite_score <= -1 (current production 'stress' threshold) ===")
for name, (peak, trough) in episodes.items():
    peak_d = pd.Timestamp(peak)
    trough_d = pd.Timestamp(trough)
    window = df[(df['date'] >= peak_d - pd.Timedelta(days=10)) & (df['date'] <= trough_d)]
    fired = window[window['composite_score'] <= -1]
    if fired.empty:
        print(f"{name}: NEVER dropped to composite_score<=-1 in window -- MISS")
        continue
    first_fire = fired.iloc[0]
    print(f"{name}: composite_score first <=-1 on {first_fire['date'].date()} (score={first_fire['composite_score']})")

# ---------------------------------------------------------------------------
# 2. Base rate / false positive check: how often does hyg_5d_pct<=THRESH fire
#    overall, and what's the REAL forward-return distribution when it fires,
#    vs unconditional?
# ---------------------------------------------------------------------------
print()
print("=== Base rate check (full HYG-valid history, 2007-04-11 to 2026-08-21) ===")
valid = df.dropna(subset=['hyg_5d_pct', 'fwd_maxdd_20d'])
signal = valid['hyg_5d_pct'] <= THRESH
n_fire = signal.sum()
n_total = len(valid)
print(f"Fires on {n_fire}/{n_total} days ({100*n_fire/n_total:.1f}% of days)")
print(f"Mean fwd 20d max-drawdown | signal fired:     {valid.loc[signal,'fwd_maxdd_20d'].mean()*100:.2f}%")
print(f"Mean fwd 20d max-drawdown | no signal:         {valid.loc[~signal,'fwd_maxdd_20d'].mean()*100:.2f}%")
print(f"Mean fwd 20d return        | signal fired:     {valid.loc[signal,'fwd_ret_20d'].mean()*100:.2f}%")
print(f"Mean fwd 20d return        | no signal:         {valid.loc[~signal,'fwd_ret_20d'].mean()*100:.2f}%")

# "Hit" = within the fwd 20d window, SPY draws down at least 5% from the signal day
hit_thresh = -0.05
hits = (valid.loc[signal, 'fwd_maxdd_20d'] <= hit_thresh).mean()
base_hits = (valid.loc[~signal, 'fwd_maxdd_20d'] <= hit_thresh).mean()
print(f"Hit rate (>=5% drawdown within 20d) | signal fired: {hits*100:.1f}%")
print(f"Hit rate (>=5% drawdown within 20d) | unconditional/no-signal: {base_hits*100:.1f}%")

# ---------------------------------------------------------------------------
# 3. By-era check (mission requires this discipline)
# ---------------------------------------------------------------------------
print()
print("=== By-era cross-check ===")
for era_name, (lo, hi) in [('2007-2012 (GFC era)', ('2007-04-11','2012-12-31')),
                            ('2013-2019 (calm bull)', ('2013-01-01','2019-12-31')),
                            ('2020-2026 (post-COVID)', ('2020-01-01','2026-08-21'))]:
    sub = valid[(valid['date']>=lo) & (valid['date']<=hi)]
    if len(sub) == 0:
        continue
    sig = sub['hyg_5d_pct'] <= THRESH
    if sig.sum() == 0:
        print(f"{era_name}: signal never fired ({len(sub)} days)")
        continue
    print(f"{era_name}: fires {sig.sum()}/{len(sub)} ({100*sig.sum()/len(sub):.1f}%), "
          f"hit-rate(>=5% dd/20d)={100*(sub.loc[sig,'fwd_maxdd_20d']<=hit_thresh).mean():.1f}%, "
          f"mean fwd20d ret|fire={100*sub.loc[sig,'fwd_ret_20d'].mean():.2f}%, "
          f"mean fwd20d ret|no-fire={100*sub.loc[~sig,'fwd_ret_20d'].mean():.2f}%")

# ---------------------------------------------------------------------------
# 4. Does composite_5d_chg add anything beyond hyg_5d_pct alone?
# ---------------------------------------------------------------------------
print()
print("=== composite_5d_chg <= -3 (sharp 5-day deterioration in composite score) ===")
valid2 = df.dropna(subset=['composite_5d_chg', 'fwd_maxdd_20d'])
sig2 = valid2['composite_5d_chg'] <= -3
print(f"Fires on {sig2.sum()}/{len(valid2)} ({100*sig2.sum()/len(valid2):.1f}%)")
print(f"Hit rate (>=5% dd/20d) | fired: {100*(valid2.loc[sig2,'fwd_maxdd_20d']<=hit_thresh).mean():.1f}%")
print(f"Mean fwd20d ret | fired: {100*valid2.loc[sig2,'fwd_ret_20d'].mean():.2f}%  | not fired: {100*valid2.loc[~sig2,'fwd_ret_20d'].mean():.2f}%")

for name, (peak, trough) in episodes.items():
    peak_d = pd.Timestamp(peak); trough_d = pd.Timestamp(trough)
    window = df[(df['date'] >= peak_d - pd.Timedelta(days=10)) & (df['date'] <= trough_d)]
    fired = window[window['composite_5d_chg'] <= -3]
    if fired.empty:
        print(f"{name}: composite_5d_chg never <=-3 in window -- MISS")
    else:
        print(f"{name}: composite_5d_chg first <=-3 on {fired.iloc[0]['date'].date()} (val={fired.iloc[0]['composite_5d_chg']:.1f})")

print(f"Hit rate (>=5% dd/20d) | not fired: {100*(valid2.loc[~sig2,'fwd_maxdd_20d']<=hit_thresh).mean():.1f}%")

print()
print("=== composite_5d_chg by-era cross-check ===")
for era_name, (lo, hi) in [('2007-2012 (GFC era)', ('2007-04-11','2012-12-31')),
                            ('2013-2019 (calm bull)', ('2013-01-01','2019-12-31')),
                            ('2020-2026 (post-COVID)', ('2020-01-01','2026-08-21'))]:
    sub = valid2[(valid2['date']>=lo) & (valid2['date']<=hi)]
    if len(sub) == 0:
        continue
    sig = sub['composite_5d_chg'] <= -3
    if sig.sum() == 0:
        print(f"{era_name}: signal never fired ({len(sub)} days)")
        continue
    print(f"{era_name}: fires {sig.sum()}/{len(sub)} ({100*sig.sum()/len(sub):.1f}%), "
          f"hit-rate(>=5% dd/20d)|fire={100*(sub.loc[sig,'fwd_maxdd_20d']<=hit_thresh).mean():.1f}%, "
          f"hit-rate|no-fire={100*(sub.loc[~sig,'fwd_maxdd_20d']<=hit_thresh).mean():.1f}%, "
          f"mean fwd20d ret|fire={100*sub.loc[sig,'fwd_ret_20d'].mean():.2f}%, "
          f"mean fwd20d ret|no-fire={100*sub.loc[~sig,'fwd_ret_20d'].mean():.2f}%")

# ---------------------------------------------------------------------------
# 5. Combined signal: composite_5d_chg <= -3 OR hyg_5d_pct <= -3 (either fires)
#    -- does combining reduce false positives vs either alone, or just add noise?
# ---------------------------------------------------------------------------
print()
print("=== Combined: fires when EITHER composite_5d_chg<=-3 OR hyg_5d_pct<=-3 ===")
valid3 = df.dropna(subset=['composite_5d_chg', 'hyg_5d_pct', 'fwd_maxdd_20d'])
sig3 = (valid3['composite_5d_chg'] <= -3) | (valid3['hyg_5d_pct'] <= -3)
sig_and = (valid3['composite_5d_chg'] <= -3) & (valid3['hyg_5d_pct'] <= -3)
print(f"OR fires on {sig3.sum()}/{len(valid3)} ({100*sig3.sum()/len(valid3):.1f}%), hit-rate={100*(valid3.loc[sig3,'fwd_maxdd_20d']<=hit_thresh).mean():.1f}%")
print(f"AND (both agree) fires on {sig_and.sum()}/{len(valid3)} ({100*sig_and.sum()/len(valid3):.1f}%), hit-rate={100*(valid3.loc[sig_and,'fwd_maxdd_20d']<=hit_thresh).mean():.1f}%")

print()
print("=== Lead time of the AND (both composite_5d_chg<=-3 AND hyg_5d_pct<=-3) signal per crash ===")
for name, (peak, trough) in episodes.items():
    peak_d = pd.Timestamp(peak); trough_d = pd.Timestamp(trough)
    window = df[(df['date'] >= peak_d - pd.Timedelta(days=10)) & (df['date'] <= trough_d)].copy()
    window_fire = window[(window['composite_5d_chg'] <= -3) & (window['hyg_5d_pct'] <= -3)]
    if window_fire.empty:
        print(f"{name}: AND signal NEVER fired in window -- MISS")
    else:
        f = window_fire.iloc[0]
        days_from_peak = (df['date'] == f['date']).idxmax() - (df['date'] >= peak_d).idxmax()
        print(f"{name}: AND first fired {f['date'].date()}, {days_from_peak} trading days after peak, "
              f"{(trough_d - f['date']).days} calendar days before trough")

# ---------------------------------------------------------------------------
# 6. Symmetric test: does composite_5d_chg >= +3 (sharp improvement) flag the
#    BOTTOM / risk-on turn early, for participating in the recovery?
# ---------------------------------------------------------------------------
print()
print("=== BOTTOM test: first composite_5d_chg >= +3 within 15 trading days after each known trough ===")
for name, (peak, trough) in episodes.items():
    trough_d = pd.Timestamp(trough)
    trough_idx = (df['date'] >= trough_d).idxmax()
    window = df.iloc[trough_idx: trough_idx + 30]
    fired = window[window['composite_5d_chg'] >= 3]
    if fired.empty:
        print(f"{name}: composite_5d_chg never >=+3 within 30 trading days after the {trough_d.date()} trough -- MISS")
    else:
        f = fired.iloc[0]
        days_after_trough = (df['date'] == f['date']).idxmax() - trough_idx
        fwd20 = f['fwd_ret_20d']
        print(f"{name}: first fired {f['date'].date()} ({days_after_trough} trading days after the trough, "
              f"val={f['composite_5d_chg']:.1f}), SPY fwd 20d return from that day: "
              f"{fwd20*100:.2f}%" if pd.notna(fwd20) else f"{name}: first fired {f['date'].date()} ({days_after_trough}d after trough)")

# base rate for the bottom signal
sig_bottom = valid2['composite_5d_chg'] >= 3
print()
print(f"Bottom-signal (composite_5d_chg>=+3) fires on {sig_bottom.sum()}/{len(valid2)} ({100*sig_bottom.sum()/len(valid2):.1f}%) of days")
print(f"Mean fwd20d return | fired: {100*valid2.loc[sig_bottom,'fwd_ret_20d'].mean():.2f}%  | not fired: {100*valid2.loc[~sig_bottom,'fwd_ret_20d'].mean():.2f}%")
print(f"Pct positive fwd20d return | fired: {100*(valid2.loc[sig_bottom,'fwd_ret_20d']>0).mean():.1f}%  | not fired: {100*(valid2.loc[~sig_bottom,'fwd_ret_20d']>0).mean():.1f}%")
