"""
Payout pattern charts for the calendar straddle strategy.
Produces results/payout_patterns.png
"""
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from pathlib import Path

ROOT = Path(__file__).parent.parent

t = pd.read_csv(ROOT / "results" / "trades.csv", parse_dates=['earn_dt'])
t['year'] = t['earn_dt'].dt.year

# ── 1. Theoretical payout diagram (one example trade) ─────────────────────
# Use AAPL Apr-26-2016 trade as the example
aapl = t[(t['ticker'] == 'AAPL') & (t['earn_dt'].dt.year == 2016)].iloc[1]
K        = 105.0   # strike
sc_prem  = aapl['sc_entry'] + aapl['sp_entry']   # per-share short credit
lc_prem  = aapl['lc_entry'] + aapl['lp_entry']   # per-share long debit

# Stock price range at short expiry
S = np.linspace(70, 145, 500)

# Short straddle P&L at expiry (we SOLD it, so profit = premium - intrinsic)
short_intrinsic = np.maximum(S - K, 0) + np.maximum(K - S, 0)  # call + put
short_pnl_ps    = sc_prem - short_intrinsic   # per share

# Long straddle: approximate value at far-term exit (held ~3 months, IV expansion)
# Simplified: long straddle gains vega * delta_IV, decays theta, + intrinsic change
# We model it as: bought at lc_prem, exits at lc_exit + lp_exit from actual trade
lc_exit_ps = aapl['lc_exit'] + aapl['lp_exit']  # what we sold it for
# Approximate long straddle value for diagram (linear approximation around K)
long_intrinsic = np.maximum(S - K, 0) + np.maximum(K - S, 0)
long_theta_decay = lc_prem - lc_exit_ps          # net decay over holding period
long_pnl_ps = (long_intrinsic - long_theta_decay * 0.3) - lc_prem  # simplified

combined_ps = short_pnl_ps + long_pnl_ps

fig = plt.figure(figsize=(16, 12))
fig.patch.set_facecolor('#1a1a2e')
gs  = gridspec.GridSpec(2, 2, figure=fig, hspace=0.4, wspace=0.35)

ax1 = fig.add_subplot(gs[0, 0])
ax1.set_facecolor('#16213e')
ax1.plot(S, short_pnl_ps * 100, color='#e94560', lw=2.5, label='Short straddle')
ax1.axhline(0, color='#888', lw=0.8, ls='--')
ax1.axvline(K, color='#f5a623', lw=1, ls=':', alpha=0.8)
ax1.fill_between(S, short_pnl_ps * 100, 0,
                 where=(short_pnl_ps > 0), alpha=0.15, color='#00ff88')
ax1.fill_between(S, short_pnl_ps * 100, 0,
                 where=(short_pnl_ps < 0), alpha=0.15, color='#e94560')
ax1.set_title('Short Near-Term Straddle\n(SELL call + put, ATM, expires after earnings)',
              color='white', fontsize=10)
ax1.set_xlabel('Stock Price at Expiry', color='#aaa')
ax1.set_ylabel('P&L per Contract ($)', color='#aaa')
ax1.tick_params(colors='#aaa')
ax1.spines['bottom'].set_color('#444')
ax1.spines['left'].set_color('#444')
ax1.spines['top'].set_visible(False)
ax1.spines['right'].set_visible(False)
ax1.annotate('Profits from IV crush\nif stock stays near $105',
             xy=(K, sc_prem * 100 * 0.9), ha='center', va='top',
             color='#00ff88', fontsize=8.5)
ax1.annotate('Loses if big move', xy=(K + 20, -600), color='#e94560',
             fontsize=8.5, ha='center')

# ── 2. Long straddle theoretical payout ──────────────────────────────────
ax2 = fig.add_subplot(gs[0, 1])
ax2.set_facecolor('#16213e')
long_at_exit = np.abs(S - K) * 0.7 + 2.5   # simplified: intrinsic component + time value
long_pnl_show = (long_at_exit - lc_prem) * 100
ax2.plot(S, long_pnl_show, color='#00d4ff', lw=2.5, label='Long straddle')
ax2.axhline(0, color='#888', lw=0.8, ls='--')
ax2.axvline(K, color='#f5a623', lw=1, ls=':', alpha=0.8)
ax2.fill_between(S, long_pnl_show, 0,
                 where=(long_pnl_show > 0), alpha=0.15, color='#00d4ff')
ax2.fill_between(S, long_pnl_show, 0,
                 where=(long_pnl_show < 0), alpha=0.15, color='#e94560')
ax2.set_title('Long Far-Term Straddle\n(BUY call + put, ATM, exit before next earnings)',
              color='white', fontsize=10)
ax2.set_xlabel('Stock Price at Exit', color='#aaa')
ax2.set_ylabel('P&L per Contract ($)', color='#aaa')
ax2.tick_params(colors='#aaa')
ax2.spines['bottom'].set_color('#444')
ax2.spines['left'].set_color('#444')
ax2.spines['top'].set_visible(False)
ax2.spines['right'].set_visible(False)
ax2.annotate('Profits from IV expansion\nbefore next earnings',
             xy=(K + 22, 400), color='#00d4ff', fontsize=8.5, ha='center')

# ── 3. Historical return distribution ─────────────────────────────────────
ax3 = fig.add_subplot(gs[1, 0])
ax3.set_facecolor('#16213e')
ret = t['return_pct'].clip(-300, 300)
bins = np.linspace(-300, 300, 40)
colors = ['#e94560' if b < 0 else '#00ff88' for b in bins[:-1]]
n, edges, patches = ax3.hist(ret, bins=bins, color='#00d4ff', edgecolor='#1a1a2e', lw=0.5)
for patch, c in zip(patches, colors):
    patch.set_facecolor(c)
ax3.axvline(0, color='white', lw=1, ls='--')
ax3.axvline(ret.mean(), color='#f5a623', lw=1.5, ls='-', label=f'Mean {ret.mean():.0f}%')
ax3.axvline(ret.median(), color='#ff9f43', lw=1.5, ls=':', label=f'Median {ret.median():.0f}%')
ax3.set_title(f'Return Distribution -- All {len(t)} Trades\n'
              f'Win rate: {(t["total_pnl"]>0).mean()*100:.1f}%  |  '
              f'Median: {ret.median():.0f}%  |  Mean: {ret.mean():.0f}%',
              color='white', fontsize=10)
ax3.set_xlabel('Return on Net Premium (%)', color='#aaa')
ax3.set_ylabel('Number of Trades', color='#aaa')
ax3.tick_params(colors='#aaa')
ax3.spines['bottom'].set_color('#444')
ax3.spines['left'].set_color('#444')
ax3.spines['top'].set_visible(False)
ax3.spines['right'].set_visible(False)
ax3.legend(fontsize=9, labelcolor='white', facecolor='#1a1a2e', edgecolor='#444')

# ── 4. Annual P&L bar chart ────────────────────────────────────────────────
ax4 = fig.add_subplot(gs[1, 1])
ax4.set_facecolor('#16213e')
by_year = t.groupby('year')['total_pnl'].sum()
bar_colors = ['#00ff88' if v > 0 else '#e94560' for v in by_year.values]
bars = ax4.bar(by_year.index.astype(str), by_year.values / 1000,
               color=bar_colors, edgecolor='#1a1a2e', lw=0.5)
ax4.axhline(0, color='#888', lw=0.8, ls='--')
ax4.set_title(f'Annual P&L  |  Cumulative: ${by_year.sum():,.0f}  (mid-price fills)',
              color='white', fontsize=10)
ax4.set_xlabel('Year', color='#aaa')
ax4.set_ylabel("P&L ($000's)", color='#aaa')
ax4.tick_params(colors='#aaa', axis='x', rotation=45)
ax4.tick_params(colors='#aaa', axis='y')
ax4.spines['bottom'].set_color('#444')
ax4.spines['left'].set_color('#444')
ax4.spines['top'].set_visible(False)
ax4.spines['right'].set_visible(False)
for bar, val in zip(bars, by_year.values):
    ax4.text(bar.get_x() + bar.get_width()/2, bar.get_height() + (2 if val > 0 else -8),
             f'${val/1000:.0f}k', ha='center', va='bottom', color='white', fontsize=7.5)

fig.suptitle('Calendar Straddle Earnings Strategy -- Payout Patterns',
             color='white', fontsize=14, fontweight='bold', y=0.98)

plt.savefig(ROOT / "results" / "payout_patterns.png", dpi=150, bbox_inches='tight',
            facecolor='#1a1a2e')
print('Saved -> results/payout_patterns.png')

# ── Print key stats ────────────────────────────────────────────────────────
print()
print('=== RETURN DISTRIBUTION ===')
bins2 = [-400,-200,-100,-50,-25,0,25,50,100,200,400]
lbls  = ['<-200','-200:-100','-100:-50','-50:-25','-25:0','0:25','25:50','50:100','100:200','>200']
t['bucket'] = pd.cut(t['return_pct'], bins=bins2, labels=lbls)
dist = t.groupby('bucket', observed=True).size()
total = len(t)
for b, n2 in dist.items():
    bar = '#' * int(n2 / total * 50)
    print(f'  {str(b):>12}: {n2:3d} trades  ({n2/total*100:4.1f}%)  {bar}')

print()
print('Short leg win rate:', round((t['short_pnl']>0).mean()*100,1), '%  | Avg:', round(t['short_pnl'].mean(),0))
print('Long  leg win rate:', round((t['long_pnl']>0).mean()*100,1), '%  | Avg:', round(t['long_pnl'].mean(),0))
print('Combined  win rate:', round((t['total_pnl']>0).mean()*100,1), '%  | Avg:', round(t['total_pnl'].mean(),0))
