"""
Sensitivity: vary long straddle exit from 1 to 30 trading days before next earnings.
For each offset N, look up the option price on that day and recompute P&L.
"""
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from pathlib import Path

ROOT = Path(__file__).parent.parent

# Load trades and options
t = pd.read_csv(ROOT / "results" / "trades.csv", parse_dates=[
    'earn_dt','short_entry_dt','long_entry_dt','short_exit_dt','long_exit_dt'])
sched = pd.read_csv(ROOT / "data" / "trade_schedule.csv", parse_dates=[
    'earn_dt','next_earn','entry_dt','short_exp','long_exp'])

opts  = pd.read_parquet(ROOT / "data" / "options_daily.parquet")
opts['date'] = pd.to_datetime(opts['date'])
opts_idx = opts.set_index(['symbol','date'])['mid']

equity = pd.read_parquet(ROOT / "data" / "equity_prices.parquet")
equity['date'] = pd.to_datetime(equity['date'])
trading_days = sorted(equity['date'].unique())

def nth_td_before(target_dt, n):
    """Return the trading day that is n trading days before target_dt."""
    candidates = [d for d in trading_days if d < target_dt]
    if len(candidates) < n:
        return None
    return candidates[-n]

def get_mid_ffill(symbol, date):
    """Mid price on date; backward-fill up to 5 days if missing."""
    try:
        sym_data = opts_idx.loc[symbol.strip()]
    except KeyError:
        return np.nan
    try:
        return sym_data.loc[date]
    except KeyError:
        prior = sym_data[sym_data.index <= date]
        if len(prior) >= 1:
            return prior.iloc[-1]
    return np.nan

# Merge symbols into trades
sched['earn_dt'] = pd.to_datetime(sched['earn_dt'])
t_s = t.merge(
    sched[['ticker','earn_dt','next_earn','long_call','long_put']],
    on=['ticker','earn_dt'], how='left'
)

print(f'Trades with symbol data: {t_s["long_call"].notna().sum()} / {len(t_s)}')
print()

# Run sensitivity across offsets 1..30 trading days before next_earn
offsets = list(range(1, 31))
results = {}

for N in offsets:
    rows = []
    for _, row in t_s.iterrows():
        if pd.isna(row.get('next_earn')) or pd.isna(row.get('long_call')):
            continue
        exit_dt = nth_td_before(row['next_earn'], N)
        if exit_dt is None:
            continue
        lc_price = get_mid_ffill(str(row['long_call']), exit_dt)
        lp_price = get_mid_ffill(str(row['long_put']),  exit_dt)
        if np.isnan(lc_price) or np.isnan(lp_price):
            continue
        long_credit  = (lc_price + lp_price) * 100
        long_pnl_new = long_credit - row['long_debit']
        total_new    = row['short_pnl'] + long_pnl_new
        net_prem     = abs(row['net_premium'])
        ret_new      = (total_new / net_prem * 100) if net_prem > 0 else np.nan
        rows.append({
            'total_pnl':  total_new,
            'long_pnl':   long_pnl_new,
            'return_pct': ret_new,
        })
    df = pd.DataFrame(rows)
    results[N] = {
        'n_trades':   len(df),
        'cum_pnl':    df['total_pnl'].sum(),
        'avg_pnl':    df['total_pnl'].mean(),
        'avg_ret':    df['return_pct'].mean(),
        'win_rate':   (df['total_pnl'] > 0).mean() * 100,
        'med_ret':    df['return_pct'].median(),
    }
    print(f'N={N:2d}d  trades={len(df):3d}  cumP&L=${df["total_pnl"].sum():>9,.0f}'
          f'  win={results[N]["win_rate"]:4.1f}%  avgRet={results[N]["avg_ret"]:6.1f}%')

res_df = pd.DataFrame(results).T
res_df.index.name = 'days_before_earn'

# ── Chart ──────────────────────────────────────────────────────────────────
fig, axes = plt.subplots(2, 2, figsize=(14, 9))
fig.patch.set_facecolor('#1a1a2e')
fig.suptitle('Sensitivity: Long Straddle Exit Timing\n(N trading days before next earnings)',
             color='white', fontsize=13, fontweight='bold')

params = [
    ('cum_pnl',  'Cumulative P&L ($)', '#00d4ff'),
    ('win_rate', 'Win Rate (%)',        '#00ff88'),
    ('avg_ret',  'Avg Return on Net Premium (%)', '#f5a623'),
    ('med_ret',  'Median Return (%)',   '#ff6b9d'),
]
for ax, (col, label, color) in zip(axes.flat, params):
    ax.set_facecolor('#16213e')
    ax.plot(res_df.index, res_df[col], color=color, lw=2.5, marker='o', ms=4)
    ax.axhline(0, color='#555', lw=0.8, ls='--')
    # Mark current design (N=1)
    ax.axvline(1, color='white', lw=1, ls=':', alpha=0.7)
    ax.annotate('current\n(N=1)', xy=(1, res_df[col].iloc[0]),
                xytext=(4, res_df[col].iloc[0]),
                color='white', fontsize=7.5, va='center',
                arrowprops=dict(arrowstyle='->', color='white', lw=0.8))
    # Mark best
    best_n = res_df[col].idxmax()
    ax.axvline(best_n, color=color, lw=1, ls='--', alpha=0.5)
    ax.set_title(label, color='white', fontsize=10)
    ax.set_xlabel('Trading days before next earnings', color='#aaa')
    ax.tick_params(colors='#aaa')
    ax.spines['bottom'].set_color('#444')
    ax.spines['left'].set_color('#444')
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

plt.tight_layout()
plt.savefig(ROOT / "results" / "sensitivity_exit.png", dpi=150, bbox_inches='tight',
            facecolor='#1a1a2e')
print('\nSaved -> results/sensitivity_exit.png')

# Best offset
best = res_df['cum_pnl'].idxmax()
print(f'\nBest cumulative P&L: exit {best} trading days before next earnings')
print(res_df.loc[best].round(1))
