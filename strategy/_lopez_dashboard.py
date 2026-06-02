"""
López de Prado portfolio-structure dashboard.

Visualizes the daily-book metrics computed in portfolio_daily.py and
lopez_stats.py. Complements _performance_dashboard.py (trade-level views)
with portfolio-level views you can only see day by day.

Six panels:
  1. Daily equity curve  (time-indexed cumulative PnL + TWRR index)
  2. Daily AUM           (gross notional, with avg / max bands)
  3. Net exposure        (directional dollar exposure over time)
  4. Leg contribution    (cumulative short-leg vs long-leg PnL)
  5. Open legs           (position count over time, capacity proxy)
  6. Holding periods     (per-leg histograms)

Outputs results/lopez_dashboard.png.
"""

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from pathlib import Path

ROOT = Path(__file__).parent.parent

daily  = pd.read_csv(ROOT / "results" / "portfolio_daily.csv",
                     parse_dates=["date"]).set_index("date").sort_index()
trades = pd.read_csv(ROOT / "results" / "trades.csv", parse_dates=[
    "earn_dt", "short_entry_dt", "long_entry_dt",
    "short_exit_dt", "long_exit_dt"])
stats  = pd.read_csv(ROOT / "results" / "lopez_stats.csv").iloc[0]

# TWRR equity index (geometric link of daily returns)
prev_aum  = daily["gross_notional"].shift(1).replace(0, np.nan)
daily_ret = (daily["daily_pnl"] / prev_aum).fillna(0)
twrr_idx  = (1 + daily_ret).cumprod()

# Daily cumulative PnL for short / long leg, derived from trades.csv
# (per-trade leg P&L stamped at the leg's exit date)
short_leg = (trades.set_index("short_exit_dt")["short_pnl"]
             .groupby(level=0).sum().sort_index().cumsum())
long_leg  = (trades.set_index("long_exit_dt")["long_pnl"]
             .groupby(level=0).sum().sort_index().cumsum())

# Holding periods
hp_short = (trades["short_exit_dt"] - trades["short_entry_dt"]).dt.days
hp_long  = (trades["long_exit_dt"]  - trades["long_entry_dt"]).dt.days

BG, PANEL = "#1a1a2e", "#16213e"
CYAN, GREEN, RED, AMBER, GREY = "#00d4ff", "#00ff88", "#e94560", "#ffb84d", "#aaa"

fig = plt.figure(figsize=(18, 13))
fig.patch.set_facecolor(BG)
gs = gridspec.GridSpec(3, 2, figure=fig, hspace=0.50, wspace=0.22,
                       height_ratios=[1.25, 1, 1])

def style(ax, title):
    ax.set_facecolor(PANEL)
    ax.set_title(title, color="white", fontsize=10.5, fontweight="bold")
    ax.tick_params(colors=GREY, labelsize=8)
    for s in ("top", "right"): ax.spines[s].set_visible(False)
    for s in ("bottom", "left"): ax.spines[s].set_color("#444")

# --- 1. EQUITY CURVE (top, full width) ----------------------------------
ax1 = fig.add_subplot(gs[0, :])
ax1.fill_between(daily.index, daily["cum_pnl"], 0,
                 where=(daily["cum_pnl"] >= 0), color=CYAN, alpha=0.18)
ax1.fill_between(daily.index, daily["cum_pnl"], 0,
                 where=(daily["cum_pnl"] < 0),  color=RED,  alpha=0.18)
ax1.plot(daily.index, daily["cum_pnl"], color=CYAN, lw=2.0, label="Cumulative PnL ($)")
ax1.axhline(0, color="#666", lw=0.6)
ax1.set_ylabel("Cumulative PnL ($)", color=GREY)

ax1b = ax1.twinx()
ax1b.plot(daily.index, (twrr_idx - 1) * 100, color=AMBER, lw=1.4, alpha=0.9,
          label="TWRR index (%)")
ax1b.set_ylabel("TWRR index (%)", color=AMBER)
ax1b.tick_params(colors=AMBER, labelsize=8)
for s in ("top",): ax1b.spines[s].set_visible(False)
ax1b.spines["right"].set_color("#444")

style(ax1,
      f"Daily Equity Curve   |   PnL: ${stats['total_pnl']:,.0f}   |   "
      f"TWRR ann: {stats['twrr_annualized_pct']:.2f}%   |   "
      f"{stats['start_dt']} to {stats['end_dt']}")
lines1, labels1 = ax1.get_legend_handles_labels()
lines2, labels2 = ax1b.get_legend_handles_labels()
ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left",
           fontsize=8, labelcolor="white", facecolor=BG, edgecolor="#444")

# --- 2. DAILY AUM (gross notional) --------------------------------------
ax2 = fig.add_subplot(gs[1, 0])
ax2.fill_between(daily.index, daily["gross_notional"] / 1000, 0,
                 color=CYAN, alpha=0.25)
ax2.plot(daily.index, daily["gross_notional"] / 1000, color=CYAN, lw=1.1)
ax2.axhline(stats["avg_aum"] / 1000, color=AMBER, lw=1.0, ls="--",
            label=f"Avg ${stats['avg_aum']/1000:.0f}k")
ax2.axhline(stats["max_aum"] / 1000, color=RED,   lw=1.0, ls=":",
            label=f"Max ${stats['max_aum']/1000:.0f}k")
ax2.set_ylabel("Gross notional ($000)", color=GREY)
style(ax2, "Daily AUM (gross notional, liquidation marks)")
ax2.legend(loc="upper left", fontsize=8, labelcolor="white",
           facecolor=BG, edgecolor="#444")

# --- 3. NET EXPOSURE ----------------------------------------------------
ax3 = fig.add_subplot(gs[1, 1])
ne = daily["net_exposure"] / 1000
ax3.fill_between(daily.index, ne, 0, where=(ne >= 0), color=GREEN, alpha=0.30)
ax3.fill_between(daily.index, ne, 0, where=(ne < 0),  color=RED,   alpha=0.30)
ax3.plot(daily.index, ne, color="white", lw=0.9, alpha=0.7)
ax3.axhline(0, color="#666", lw=0.6)
ax3.axhline(stats["avg_net_exposure"] / 1000, color=AMBER, lw=1.0, ls="--",
            label=f"Avg ${stats['avg_net_exposure']/1000:.0f}k  "
                  f"({stats['ratio_longs_pct']:.0f}% days net long)")
ax3.set_ylabel("Net exposure ($000)", color=GREY)
style(ax3, "Net Exposure (longs +, shorts −)")
ax3.legend(loc="upper left", fontsize=8, labelcolor="white",
           facecolor=BG, edgecolor="#444")

# --- 4. LEG CONTRIBUTION ------------------------------------------------
ax4 = fig.add_subplot(gs[2, 0])
ax4.plot(short_leg.index, short_leg.values, color=GREEN, lw=1.6,
         label=f"Short leg  +${stats['pnl_short_leg']:,.0f}")
ax4.plot(long_leg.index,  long_leg.values,  color=RED,   lw=1.6,
         label=f"Long leg   ${stats['pnl_long_leg']:,.0f}")
ax4.axhline(0, color="#666", lw=0.6, ls="--")
ax4.set_ylabel("Cumulative PnL ($)", color=GREY)
style(ax4, "Leg Contribution (cumulative PnL by leg)")
ax4.legend(loc="upper left", fontsize=8, labelcolor="white",
           facecolor=BG, edgecolor="#444")

# --- 5. OPEN LEGS -------------------------------------------------------
ax5 = fig.add_subplot(gs[2, 1])
ax5.fill_between(daily.index, daily["open_legs"], 0, color=CYAN, alpha=0.25)
ax5.plot(daily.index, daily["open_legs"], color=CYAN, lw=0.9)
ax5.axhline(daily["open_legs"].mean(), color=AMBER, lw=1.0, ls="--",
            label=f"Avg {daily['open_legs'].mean():.0f} legs")
ax5.axhline(daily["open_legs"].max(),  color=RED,   lw=1.0, ls=":",
            label=f"Max {int(daily['open_legs'].max())} legs")
ax5.set_ylabel("Open legs", color=GREY)
style(ax5, "Concurrency (open legs per day)")
ax5.legend(loc="upper left", fontsize=8, labelcolor="white",
           facecolor=BG, edgecolor="#444")

# --- 6. HOLDING PERIOD DISTRIBUTION (inset under panel 5 — full bottom) -
# Drop a stat-sheet text box anchored to the bottom-right
stats_text = (
    f"Frequency of bets    : {stats['frequency_bets_per_year']:.1f}/yr\n"
    f"Avg holding (full)   : {stats['avg_holding_days_trade']:.0f} d\n"
    f"  short leg          : {stats['avg_holding_days_short']:.0f} d\n"
    f"  long  leg          : {stats['avg_holding_days_long']:.0f} d\n"
    f"Annualized turnover  : {stats['annualized_turnover']:.1f}x\n"
    f"Leverage (gross/|net|): {stats['leverage_gross_over_net']:.2f}x\n"
    f"Hit ratio            : {stats['hit_ratio_pct']:.1f}%\n"
    f"Avg return on hits   : {stats['avg_return_hits_pct']:+.1f}%\n"
    f"Avg return on misses : {stats['avg_return_misses_pct']:+.1f}%"
)
fig.text(0.985, 0.012, stats_text, ha="right", va="bottom",
         color="white", fontsize=8.5, family="monospace",
         bbox=dict(boxstyle="round,pad=0.5", facecolor=PANEL, edgecolor="#444"))

fig.suptitle("Calendar Straddle — Portfolio Structure (López de Prado Ch. 14)",
             color="white", fontsize=14, fontweight="bold", y=0.995)

out = ROOT / "results" / "lopez_dashboard.png"
plt.savefig(out, dpi=150, bbox_inches="tight", facecolor=BG)
print(f"Saved -> {out.relative_to(ROOT)}")
