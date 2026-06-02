"""
Render each chart from the performance + López dashboards as a separate
PNG on an Anthropic-cream background, into results/charts/.

Unit per chart (only meaningful units used -- no forced percentages):
  Cumulative-over-time / state charts (dollars / counts):
    01 trade-indexed equity curve         -- $
    02 drawdown                           -- $
    06 daily mark-to-market equity curve  -- $
    09 leg contribution (short vs long)   -- $
    10 concurrency (open legs)            -- count

  Per-bucket / utilization charts (percentages of a meaningful denominator):
    03 annual return on net premium       -- % of that year's |net premium|
    04 monthly return on net premium      -- % of that month's |net premium|
    05 ticker cumulative return on premium-- % of that ticker's |net premium|
    07 daily AUM utilization              -- % of strategy avg AUM
    08 net exposure                       -- % of strategy avg AUM

Also copies results/tsla_jan2022_tos_style.png into the same folder.
"""

import shutil
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from pathlib import Path

ROOT = Path(__file__).parent.parent
OUT  = ROOT / "results" / "charts"
OUT.mkdir(parents=True, exist_ok=True)

# --- Anthropic-cream palette ------------------------------------------------
BG      = "#F5F1EB"
TEXT    = "#2C2A26"
GRID    = "#D6CFC2"
SPINE   = "#A39B8E"
BLUE    = "#4A6FA5"
GREEN   = "#4A7C59"
RED     = "#B0413E"
ORANGE  = "#D97757"
MUTED   = "#8C857A"

plt.rcParams.update({
    "font.family":     "DejaVu Sans",
    "axes.edgecolor":  SPINE,
    "axes.labelcolor": TEXT,
    "xtick.color":     TEXT,
    "ytick.color":     TEXT,
    "text.color":      TEXT,
    "axes.titlecolor": TEXT,
})

def new_fig(figsize=(11, 5)):
    fig, ax = plt.subplots(figsize=figsize)
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)
    for s in ("top", "right"):  ax.spines[s].set_visible(False)
    for s in ("bottom", "left"): ax.spines[s].set_color(SPINE)
    ax.grid(True, color=GRID, lw=0.7, alpha=0.7)
    ax.set_axisbelow(True)
    return fig, ax

def save(fig, name):
    fig.savefig(OUT / f"{name}.png", dpi=170, bbox_inches="tight", facecolor=BG)
    plt.close(fig)
    print(f"  saved -> charts/{name}.png")

def pct_fmt(v, _): return f"{v:.0f}%"

# --- Load data --------------------------------------------------------------
trades = pd.read_csv(ROOT / "results" / "trades.csv", parse_dates=[
    "earn_dt", "short_entry_dt", "long_entry_dt",
    "short_exit_dt", "long_exit_dt"]).sort_values("earn_dt").reset_index(drop=True)
trades["year"]            = trades["earn_dt"].dt.year
trades["month"]           = trades["earn_dt"].dt.month
trades["abs_net_premium"] = trades["net_premium"].abs()
trades["cum_pnl"]         = trades["total_pnl"].cumsum()
trades["cum_anp"]         = trades["abs_net_premium"].cumsum()
trades["peak"]            = trades["cum_pnl"].cummax()
trades["dd"]              = trades["cum_pnl"] - trades["peak"]

daily = pd.read_csv(ROOT / "results" / "portfolio_daily.csv",
                    parse_dates=["date"]).set_index("date").sort_index()

stats   = pd.read_csv(ROOT / "results" / "lopez_stats.csv").iloc[0]
AVG_AUM = stats["avg_aum"]

# ============================================================================
# 1. Equity curve (trade-indexed, $)
# ============================================================================
fig, ax = new_fig((12, 5))
ax.fill_between(trades["earn_dt"], trades["cum_pnl"], 0,
                where=(trades["cum_pnl"] >= 0), color=BLUE, alpha=0.18)
ax.fill_between(trades["earn_dt"], trades["cum_pnl"], 0,
                where=(trades["cum_pnl"] < 0),  color=RED,  alpha=0.18)
ax.plot(trades["earn_dt"], trades["cum_pnl"], color=BLUE, lw=2.0)
ax.plot(trades["earn_dt"], trades["peak"], color=MUTED, lw=0.9, ls="--",
        alpha=0.8, label="Running peak")
ax.axhline(0, color=SPINE, lw=0.6)
ax.set_title(f"Equity Curve (trade-indexed)   |   "
             f"Cum P&L  \\${trades['total_pnl'].sum():,.0f}",
             fontsize=12, fontweight="bold", pad=12)
ax.set_ylabel("Cumulative P&L ($)")
ax.legend(loc="upper left", frameon=False)
save(fig, "01_equity_curve_by_trade")

# ============================================================================
# 2. Drawdown (trade-indexed, $)
# ============================================================================
fig, ax = new_fig((12, 4))
ax.fill_between(trades["earn_dt"], trades["dd"], 0, color=RED, alpha=0.35)
ax.plot(trades["earn_dt"], trades["dd"], color=RED, lw=1.5)
ax.axhline(0, color=SPINE, lw=0.6)
ax.set_title(f"Drawdown (trade-indexed)   |   "
             f"Max DD  \\${trades['dd'].min():,.0f}",
             fontsize=12, fontweight="bold", pad=12)
ax.set_ylabel("Drawdown ($)")
save(fig, "02_drawdown")

# ============================================================================
# 3. Annual Return on Net Premium  (year P&L / |year net premium|)
# ============================================================================
by_year_pnl = trades.groupby("year")["total_pnl"].sum()
by_year_anp = trades.groupby("year")["abs_net_premium"].sum()
annual_pct  = (by_year_pnl / by_year_anp) * 100
fig, ax = new_fig((10, 5))
colors = [GREEN if v > 0 else RED for v in annual_pct.values]
bars = ax.bar(annual_pct.index.astype(str), annual_pct.values,
              color=colors, edgecolor=BG, lw=1.0)
ax.axhline(0, color=SPINE, lw=0.6, ls="--")
ax.set_title("Annual Return on Net Premium   (year P&L  /  |year net premium paid|)",
             fontsize=12, fontweight="bold", pad=12)
ax.set_ylabel("Return on net premium")
for bar, val in zip(bars, annual_pct.values):
    ax.text(bar.get_x() + bar.get_width()/2,
            bar.get_height() + (3 if val > 0 else -6),
            f"{val:+.0f}%",
            ha="center", va="bottom" if val > 0 else "top",
            color=TEXT, fontsize=9)
ax.yaxis.set_major_formatter(plt.FuncFormatter(pct_fmt))
plt.xticks(rotation=45)
save(fig, "03_annual_return_pct")

# ============================================================================
# 4. Monthly Return on Net Premium heatmap
# ============================================================================
monthly_pnl = trades.groupby(["year", "month"])["total_pnl"].sum().unstack(fill_value=0)
monthly_anp = trades.groupby(["year", "month"])["abs_net_premium"].sum().unstack(fill_value=0)
monthly_pct = (monthly_pnl / monthly_anp.replace(0, np.nan)) * 100
display     = monthly_pct.fillna(0)

fig, ax = new_fig((11, 6))
vmax = max(abs(np.nanmin(monthly_pct.values)),
           abs(np.nanmax(monthly_pct.values)))
cmap = LinearSegmentedColormap.from_list("anthropic_div",
                                          [RED, BG, GREEN], N=256)
im = ax.imshow(display.values, cmap=cmap, aspect="auto",
               vmin=-vmax, vmax=vmax)
ax.set_xticks(range(12))
ax.set_xticklabels(["Jan","Feb","Mar","Apr","May","Jun",
                    "Jul","Aug","Sep","Oct","Nov","Dec"], fontsize=9)
ax.set_yticks(range(len(display.index)))
ax.set_yticklabels(display.index, fontsize=9)
ax.set_title("Monthly Return on Net Premium (%)",
             fontsize=12, fontweight="bold", pad=12)
for i in range(len(display.index)):
    for j in range(display.shape[1]):
        v = monthly_pct.values[i, j]
        if pd.notna(v) and abs(v) > vmax * 0.05:
            ax.text(j, i, f"{v:.0f}%", ha="center", va="center",
                    color=TEXT, fontsize=8)
ax.grid(False)
cbar = plt.colorbar(im, ax=ax, fraction=0.03, pad=0.02)
cbar.ax.tick_params(labelsize=8)
cbar.outline.set_edgecolor(SPINE)
cbar.ax.yaxis.set_major_formatter(plt.FuncFormatter(pct_fmt))
save(fig, "04_monthly_heatmap")

# ============================================================================
# 5. Cumulative Return on Net Premium by Ticker
# ============================================================================
by_tk_pnl = trades.groupby("ticker")["total_pnl"].sum()
by_tk_anp = trades.groupby("ticker")["abs_net_premium"].sum()
by_tk_pct = (by_tk_pnl / by_tk_anp * 100).sort_values()
fig, ax = new_fig((10, 8))
tk_colors = [RED if v < 0 else GREEN for v in by_tk_pct.values]
ax.barh(by_tk_pct.index, by_tk_pct.values, color=tk_colors,
        edgecolor=BG, lw=0.8)
ax.axvline(0, color=SPINE, lw=0.6, ls="--")
ax.set_title("Cumulative Return on Net Premium by Ticker",
             fontsize=12, fontweight="bold", pad=12)
ax.set_xlabel("Return on net premium")
ax.xaxis.set_major_formatter(plt.FuncFormatter(pct_fmt))
for ticker, val in by_tk_pct.items():
    ax.text(val + (1 if val >= 0 else -1), ticker,
            f"{val:+.0f}%",
            ha="left" if val >= 0 else "right", va="center",
            color=TEXT, fontsize=8)
save(fig, "05_cum_pnl_by_ticker")

# ============================================================================
# 6. Daily equity curve (mark-to-market, $)
# ============================================================================
fig, ax = new_fig((12, 5))
ax.fill_between(daily.index, daily["cum_pnl"], 0,
                where=(daily["cum_pnl"] >= 0), color=BLUE, alpha=0.18)
ax.fill_between(daily.index, daily["cum_pnl"], 0,
                where=(daily["cum_pnl"] < 0),  color=RED,  alpha=0.18)
ax.plot(daily.index, daily["cum_pnl"], color=BLUE, lw=1.8)
ax.axhline(0, color=SPINE, lw=0.6)
ax.set_title(f"Daily Equity Curve (mark-to-market)   |   "
             f"PnL  \\${stats['total_pnl']:,.0f}",
             fontsize=12, fontweight="bold", pad=12)
ax.set_ylabel("Cumulative P&L ($)")
save(fig, "06_daily_equity_curve")

# ============================================================================
# 7. Daily AUM  (% of strategy avg AUM)
# ============================================================================
aum_pct = daily["gross_notional"] / AVG_AUM * 100
fig, ax = new_fig((12, 5))
ax.fill_between(daily.index, aum_pct, 0, color=BLUE, alpha=0.22)
ax.plot(daily.index, aum_pct, color=BLUE, lw=1.0)
ax.axhline(100, color=ORANGE, lw=1.1, ls="--", label="Avg (100%)")
ax.axhline(stats["max_aum"] / AVG_AUM * 100, color=RED, lw=1.1, ls=":",
           label=f"Max ({stats['max_aum']/AVG_AUM*100:.0f}%)")
ax.set_title(f"Daily AUM Utilization (% of avg gross notional, \\${AVG_AUM/1000:.0f}k)",
             fontsize=12, fontweight="bold", pad=12)
ax.set_ylabel("Utilization")
ax.yaxis.set_major_formatter(plt.FuncFormatter(pct_fmt))
ax.legend(loc="upper left", frameon=False)
save(fig, "07_daily_aum")

# ============================================================================
# 8. Net Exposure  (% of strategy avg AUM)
# ============================================================================
ne_pct     = daily["net_exposure"] / AVG_AUM * 100
avg_ne_pct = stats["avg_net_exposure"] / AVG_AUM * 100
fig, ax = new_fig((12, 5))
ax.fill_between(daily.index, ne_pct, 0,
                where=(ne_pct >= 0), color=GREEN, alpha=0.30)
ax.fill_between(daily.index, ne_pct, 0,
                where=(ne_pct < 0),  color=RED,   alpha=0.30)
ax.plot(daily.index, ne_pct, color=TEXT, lw=0.8, alpha=0.8)
ax.axhline(0, color=SPINE, lw=0.6)
ax.axhline(avg_ne_pct, color=ORANGE, lw=1.1, ls="--",
           label=f"Avg {avg_ne_pct:.0f}%  "
                 f"({stats['ratio_longs_pct']:.0f}% days net long)")
ax.set_title(f"Net Exposure (% of avg gross notional, \\${AVG_AUM/1000:.0f}k; longs +, shorts −)",
             fontsize=12, fontweight="bold", pad=12)
ax.set_ylabel("Net exposure")
ax.yaxis.set_major_formatter(plt.FuncFormatter(pct_fmt))
ax.legend(loc="upper left", frameon=False)
save(fig, "08_net_exposure")

# ============================================================================
# 9. Leg Contribution (cumulative leg P&L, $)
# ============================================================================
short_leg = (trades.set_index("short_exit_dt")["short_pnl"]
             .groupby(level=0).sum().sort_index().cumsum())
long_leg  = (trades.set_index("long_exit_dt")["long_pnl"]
             .groupby(level=0).sum().sort_index().cumsum())

fig, ax = new_fig((12, 5))
ax.plot(short_leg.index, short_leg.values, color=GREEN, lw=1.8,
        label=f"Short leg   +\\${stats['pnl_short_leg']:,.0f}")
ax.plot(long_leg.index, long_leg.values, color=RED, lw=1.8,
        label=f"Long leg    \\${stats['pnl_long_leg']:,.0f}")
ax.axhline(0, color=SPINE, lw=0.6, ls="--")
ax.set_title("Leg Contribution (cumulative P&L by leg)",
             fontsize=12, fontweight="bold", pad=12)
ax.set_ylabel("Cumulative P&L ($)")
ax.legend(loc="upper left", frameon=False)
save(fig, "09_leg_contribution")

# ============================================================================
# 10. Concurrency (open legs count)
# ============================================================================
fig, ax = new_fig((12, 5))
ax.fill_between(daily.index, daily["open_legs"], 0, color=BLUE, alpha=0.22)
ax.plot(daily.index, daily["open_legs"], color=BLUE, lw=0.9)
ax.axhline(daily["open_legs"].mean(), color=ORANGE, lw=1.1, ls="--",
           label=f"Avg {daily['open_legs'].mean():.0f} legs")
ax.axhline(daily["open_legs"].max(), color=RED, lw=1.1, ls=":",
           label=f"Max {int(daily['open_legs'].max())} legs")
ax.set_title("Concurrency (open legs per day)",
             fontsize=12, fontweight="bold", pad=12)
ax.set_ylabel("Open legs")
ax.legend(loc="upper left", frameon=False)
save(fig, "10_concurrency")

# ============================================================================
# Copy the TSLA TOS-style chart
# ============================================================================
src = ROOT / "results" / "tsla_jan2022_tos_style.png"
dst = OUT / "tsla_jan2022_tos_style.png"
if src.exists():
    shutil.copy2(src, dst)
    print(f"  copied -> charts/tsla_jan2022_tos_style.png")
else:
    print(f"  ! source not found: {src}")

print(f"\nAll charts written to {OUT.relative_to(ROOT)}/")
