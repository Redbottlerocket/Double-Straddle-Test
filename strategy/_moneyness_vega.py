"""
Compare vega (IV sensitivity) for ATM vs OTM vs ITM long straddles.
Also quantify: how much IV expansion do you need to break even on theta drag?
"""
import sys
import pandas as pd
import numpy as np
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(Path(__file__).parent))
from greeks import bs_price, greeks as bs_greeks, implied_vol

# Representative example: AAPL at $107, strike options with ~100 days to expiry
S    = 107.0    # stock price
T    = 100/365  # 100 days
r    = 0.04
q    = 0.0055
iv   = 0.28     # typical far-term IV (~28%)

print('=== VEGA by MONEYNESS (long straddle, 100 DTE, stock=$107, IV=28%) ===')
print()
print(f'{"Strike":>8}  {"Moneyness":>10}  {"Call vega":>10}  {"Put vega":>10}  '
      f'{"Straddle vega":>14}  {"Straddle cost":>14}  {"Vega/Dollar":>11}')
print('-' * 95)

rows = []
for K in [85, 90, 95, 100, 105, 107, 110, 115, 120, 125, 130]:
    money_pct = (K - S) / S * 100
    label     = 'ATM' if abs(money_pct) < 2 else ('OTM' if K > S else 'ITM')

    # Call
    c_price = bs_price(S, K, T, r, q, iv, 'call')
    c_g     = bs_greeks(S, K, T, r, q, iv, 'call')
    # Put
    p_price = bs_price(S, K, T, r, q, iv, 'put')
    p_g     = bs_greeks(S, K, T, r, q, iv, 'put')

    strad_cost  = (c_price + p_price) * 100
    strad_vega  = (c_g['vega'] + p_g['vega'])       # per share, per 1% vol
    strad_theta = (c_g['theta'] + p_g['theta'])      # per share, per day
    vega_per_dollar = strad_vega / (c_price + p_price)

    tag = '<<< ATM' if label == 'ATM' else ''
    print(f'{K:>8}  {money_pct:>+8.1f}%  {c_g["vega"]:>10.3f}  {p_g["vega"]:>10.3f}  '
          f'{strad_vega:>14.3f}  ${strad_cost:>12.2f}  {vega_per_dollar:>10.4f}  {tag}')
    rows.append({'K': K, 'moneyness': money_pct, 'strad_vega': strad_vega,
                 'strad_cost': strad_cost, 'strad_theta': strad_theta,
                 'vega_per_dollar': vega_per_dollar, 'label': label})

df = pd.DataFrame(rows)
atm = df[df['label'] == 'ATM'].iloc[0]

print()
print('=== KEY INSIGHT: ATM has highest vega in dollar terms ===')
print(f'ATM straddle (K={atm.K:.0f}): vega = {atm.strad_vega:.3f}/sh = ${atm.strad_vega*100:.1f}/contract per 1% vol rise')
otm_10 = df[df['K'] == 115].iloc[0]
otm_5  = df[df['K'] == 112].iloc[0] if 112 in df['K'].values else df[df['K'] == 110].iloc[0]
print(f'OTM strangle (K=115, +7.5%): vega = {otm_10.strad_vega:.3f}/sh = ${otm_10.strad_vega*100:.1f}/contract per 1% vol rise')
itm_5  = df[df['K'] == 100].iloc[0]
print(f'ITM straddle (K=100, -6.5%): vega = {itm_5.strad_vega:.3f}/sh = ${itm_5.strad_vega*100:.1f}/contract per 1% vol rise')

print()
print('=== THETA vs VEGA break-even for the long straddle ===')
print('How much must IV rise to offset theta decay over the holding period?')
print()
holding_days = 67   # Phase 2 duration (after short expires to long exit)
print(f'Holding period (Phase 2): {holding_days} days')
print()
for _, row in df[df['K'].isin([100, 105, 107, 110, 115])].iterrows():
    total_theta_cost = abs(row.strad_theta) * holding_days  # per share
    iv_needed = total_theta_cost / row.strad_vega if row.strad_vega > 0 else np.nan
    print(f"K={row['K']:>3}  ({row['moneyness']:>+5.1f}%)  "
          f"theta/day=${abs(row.strad_theta)*100:.2f}/contract  "
          f"total theta cost=${total_theta_cost*100:.0f}  "
          f"IV rise needed={iv_needed:.1f}%")

print()
print('=== WHAT ACTUALLY HAPPENS IN OUR BACKTEST ===')
g = pd.read_parquet(ROOT / "results" / "daily_greeks.parquet")
g['date'] = pd.to_datetime(g['date'])
# Long leg vega at entry (day 1 only)
t = pd.read_csv(ROOT / "results" / "trades.csv", parse_dates=['earn_dt','long_entry_dt'])
g['earn_dt'] = pd.to_datetime(g['earn_dt'])
long_legs = g[g['leg'].isin(['lc','lp'])].copy()
long_legs['date_d'] = long_legs['date'].dt.date
# Merge to get entry date
t['earn_dt_d'] = t['earn_dt'].dt.date
t['long_entry_d'] = t['long_entry_dt'].dt.date
lm = long_legs.merge(t[['ticker','earn_dt_d','long_entry_d']],
                     left_on=['ticker', long_legs['earn_dt'].dt.date.values],
                     right_on=['ticker','earn_dt_d'], how='left')
entry_only = long_legs[long_legs['date_d'] == long_legs['date_d']]
# Simple: filter where it's the first date per (ticker, earn_dt)
first_dates = long_legs.groupby(['ticker','earn_dt'])['date'].min().reset_index()
first_dates.columns = ['ticker','earn_dt','first_date']
long_entry = long_legs.merge(first_dates, on=['ticker','earn_dt'])
long_entry = long_entry[long_entry['date'] == long_entry['first_date']]
print(f'Avg long straddle vega at entry: {long_entry["pos_vega"].sum() / long_entry.groupby(["ticker","earn_dt"]).ngroups:.3f}/sh/contract')
print(f'Avg long straddle theta at entry: {long_entry["pos_theta"].sum() / long_entry.groupby(["ticker","earn_dt"]).ngroups:.3f}/sh/day')
iv_needed_actual = (abs(long_entry["pos_theta"].mean()) * 67) / long_entry["pos_vega"].mean()
print(f'IV rise needed to break even on {holding_days}-day theta: {iv_needed_actual:.1f}%')
