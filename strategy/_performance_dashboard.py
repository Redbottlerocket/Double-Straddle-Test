"""
Performance dashboard for the calendar straddle strategy.
Produces results/performance_dashboard.png with 6 panels:
  - Equity curve (cumulative P&L over time)
  - Drawdown
  - Annual P&L bars
  - Monthly heatmap
  - Per-ticker cumulative P&L
  - Return distribution
"""
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from pathlib import Path

ROOT = Path(__file__).parent.parent

t = pd.read_csv(ROOT / "results" / "trades.csv", parse_dates=["earn_dt"])
t = t.sort_values("earn_dt").reset_index(drop=True)
t["year"]      = t["earn_dt"].dt.year
t["month"]     = t["earn_dt"].dt.month
t["cum_pnl"]   = t["total_pnl"].cumsum()
t["peak"]      = t["cum_pnl"].cummax()
t["drawdown"]  = t["cum_pnl"] - t["peak"]

# Aggregate metrics
n          = len(t)
win_rate   = (t["total_pnl"] > 0).mean() * 100
cum_pnl    = t["total_pnl"].sum()
avg_pnl    = t["total_pnl"].mean()
avg_ret    = t["return_pct"].mean()
mdd        = t["drawdown"].min()
sharpe     = (t["return_pct"].mean() / t["return_pct"].std()) * np.sqrt(4) if t["return_pct"].std() > 0 else 0
avg_win    = t.loc[t["total_pnl"] > 0, "total_pnl"].mean()
avg_loss   = t.loc[t["total_pnl"] < 0, "total_pnl"].mean()
pf         = abs(avg_win / avg_loss) if avg_loss != 0 else 0

# Set up the figure
fig = plt.figure(figsize=(18, 12))
fig.patch.set_facecolor('#1a1a2e')
gs = gridspec.GridSpec(3, 2, figure=fig, hspace=0.45, wspace=0.25,
                       height_ratios=[1.3, 1, 1])

# --- 1. EQUITY CURVE (top, full width across left column) ---
ax1 = fig.add_subplot(gs[0, :])
ax1.set_facecolor('#16213e')
ax1.fill_between(t["earn_dt"], t["cum_pnl"], 0, where=(t["cum_pnl"] >= 0),
                 color='#00d4ff', alpha=0.20)
ax1.fill_between(t["earn_dt"], t["cum_pnl"], 0, where=(t["cum_pnl"] < 0),
                 color='#e94560', alpha=0.20)
ax1.plot(t["earn_dt"], t["cum_pnl"], color='#00d4ff', lw=2.2)
ax1.plot(t["earn_dt"], t["peak"],    color='#888', lw=0.8, ls='--', alpha=0.6,
         label='Running peak')
ax1.axhline(0, color='#666', lw=0.6, ls='-')
ax1.set_title(f'Equity Curve  |  Cum P&L: ${cum_pnl:,.0f}  |  Max DD: ${mdd:,.0f}  |  '
              f'Win rate: {win_rate:.1f}%  |  Sharpe: {sharpe:.2f}',
              color='white', fontsize=11, fontweight='bold')
ax1.set_ylabel('Cumulative P&L ($)', color='#aaa')
ax1.tick_params(colors='#aaa')
for spine in ['top','right']: ax1.spines[spine].set_visible(False)
for spine in ['bottom','left']: ax1.spines[spine].set_color('#444')
ax1.legend(loc='upper left', fontsize=8, labelcolor='white',
           facecolor='#1a1a2e', edgecolor='#444')

# --- 2. DRAWDOWN ---
ax2 = fig.add_subplot(gs[1, 0])
ax2.set_facecolor('#16213e')
ax2.fill_between(t["earn_dt"], t["drawdown"], 0, color='#e94560', alpha=0.40)
ax2.plot(t["earn_dt"], t["drawdown"], color='#e94560', lw=1.5)
ax2.axhline(0, color='#666', lw=0.6)
ax2.set_title(f'Drawdown  (max ${mdd:,.0f})', color='white', fontsize=10)
ax2.set_ylabel('Drawdown ($)', color='#aaa')
ax2.tick_params(colors='#aaa')
for spine in ['top','right']: ax2.spines[spine].set_visible(False)
for spine in ['bottom','left']: ax2.spines[spine].set_color('#444')

# --- 3. ANNUAL P&L BARS ---
ax3 = fig.add_subplot(gs[1, 1])
ax3.set_facecolor('#16213e')
by_year = t.groupby("year")["total_pnl"].sum()
colors = ['#00ff88' if v > 0 else '#e94560' for v in by_year.values]
bars = ax3.bar(by_year.index.astype(str), by_year.values / 1000,
               color=colors, edgecolor='#1a1a2e', lw=0.5)
ax3.axhline(0, color='#666', lw=0.6, ls='--')
ax3.set_title('Annual P&L', color='white', fontsize=10)
ax3.set_ylabel("P&L ($000's)", color='#aaa')
ax3.tick_params(colors='#aaa', axis='x', rotation=45)
ax3.tick_params(colors='#aaa', axis='y')
for spine in ['top','right']: ax3.spines[spine].set_visible(False)
for spine in ['bottom','left']: ax3.spines[spine].set_color('#444')
for bar, val in zip(bars, by_year.values):
    ax3.text(bar.get_x() + bar.get_width()/2,
             bar.get_height() + (3 if val > 0 else -8),
             f'{val/1000:.0f}k', ha='center', va='bottom',
             color='white', fontsize=7.5)

# --- 4. MONTHLY HEATMAP ---
ax4 = fig.add_subplot(gs[2, 0])
ax4.set_facecolor('#16213e')
monthly = t.groupby(["year","month"])["total_pnl"].sum().unstack(fill_value=0) / 1000
vmax = max(abs(monthly.values.min()), abs(monthly.values.max()))
im = ax4.imshow(monthly.values, cmap='RdYlGn', aspect='auto',
                vmin=-vmax, vmax=vmax)
ax4.set_xticks(range(12))
ax4.set_xticklabels(['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'],
                    color='#aaa', fontsize=8)
ax4.set_yticks(range(len(monthly.index)))
ax4.set_yticklabels(monthly.index, color='#aaa', fontsize=8)
ax4.set_title("Monthly P&L Heatmap ($000's)", color='white', fontsize=10)
for i in range(len(monthly.index)):
    for j in range(monthly.shape[1]):
        v = monthly.values[i, j]
        if abs(v) > vmax * 0.05:
            ax4.text(j, i, f'{v:.0f}', ha='center', va='center',
                     color='black' if abs(v) > vmax * 0.4 else 'white',
                     fontsize=7)
cbar = plt.colorbar(im, ax=ax4, fraction=0.03, pad=0.02)
cbar.ax.tick_params(colors='#aaa', labelsize=7)

# --- 5. PER-TICKER CUMULATIVE P&L ---
ax5 = fig.add_subplot(gs[2, 1])
ax5.set_facecolor('#16213e')
by_tk = t.groupby("ticker")["total_pnl"].sum().sort_values()
tk_colors = ['#e94560' if v < 0 else '#00ff88' for v in by_tk.values]
ax5.barh(by_tk.index, by_tk.values / 1000, color=tk_colors,
         edgecolor='#1a1a2e', lw=0.5)
ax5.axvline(0, color='#666', lw=0.6, ls='--')
ax5.set_title('Cumulative P&L by Ticker', color='white', fontsize=10)
ax5.set_xlabel("P&L ($000's)", color='#aaa')
ax5.tick_params(colors='#aaa', labelsize=8)
for spine in ['top','right']: ax5.spines[spine].set_visible(False)
for spine in ['bottom','left']: ax5.spines[spine].set_color('#444')

fig.suptitle(f'Calendar Straddle Backtest — Performance Dashboard  '
             f'(818 trades, 2016–2026)',
             color='white', fontsize=14, fontweight='bold', y=0.995)

plt.savefig(ROOT / "results" / "performance_dashboard.png", dpi=150,
            bbox_inches='tight', facecolor='#1a1a2e')
print('Saved -> results/performance_dashboard.png')

# Print key metrics
print()
print('=== KEY METRICS ===')
print(f'  Total trades       : {n:,}')
print(f'  Cumulative P&L     : ${cum_pnl:>12,.0f}')
print(f'  Avg P&L / trade    : ${avg_pnl:>12,.2f}')
print(f'  Avg return         : {avg_ret:>11.1f}%')
print(f'  Win rate           : {win_rate:>11.1f}%')
print(f'  Profit factor      : {pf:>11.2f}x')
print(f'  Max drawdown       : ${mdd:>12,.0f}')
print(f'  Sharpe (annualised): {sharpe:>11.2f}')
print(f'  Best trade         : ${t["total_pnl"].max():>12,.0f}')
print(f'  Worst trade        : ${t["total_pnl"].min():>12,.0f}')
