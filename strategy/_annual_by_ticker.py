"""
Per-ticker annual Return on Net Premium charts.

For each ticker, for each year: that ticker's year P&L divided by the sum of
|net premium paid| on that ticker's trades that year.

Same metric as 03_annual_return_pct.png (canonical Return on Net Premium) but
sliced per stock instead of aggregated.

Outputs results/charts/by_ticker_annual/<TICKER>.png for each ticker.
"""

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path

ROOT = Path(__file__).parent.parent
OUT  = ROOT / "results" / "charts" / "by_ticker_annual"
OUT.mkdir(parents=True, exist_ok=True)

# Anthropic-cream palette
BG, TEXT, GRID, SPINE = "#F5F1EB", "#2C2A26", "#D6CFC2", "#A39B8E"
GREEN, RED = "#4A7C59", "#B0413E"

plt.rcParams.update({
    "font.family":      "DejaVu Sans",
    "axes.edgecolor":   SPINE,
    "axes.labelcolor":  TEXT,
    "xtick.color":      TEXT,
    "ytick.color":      TEXT,
    "text.color":       TEXT,
    "axes.titlecolor":  TEXT,
})

trades = pd.read_csv(ROOT / "results" / "trades.csv", parse_dates=["earn_dt"])
trades["year"]            = trades["earn_dt"].dt.year
trades["abs_net_premium"] = trades["net_premium"].abs()

all_years = sorted(trades["year"].unique())

pivot_pnl = trades.pivot_table(index="ticker", columns="year",
                               values="total_pnl", aggfunc="sum", fill_value=0)
pivot_anp = trades.pivot_table(index="ticker", columns="year",
                               values="abs_net_premium", aggfunc="sum", fill_value=0)
pivot_pnl = pivot_pnl.reindex(columns=all_years, fill_value=0)
pivot_anp = pivot_anp.reindex(columns=all_years, fill_value=0)

pivot_pct = (pivot_pnl / pivot_anp.replace(0, np.nan)) * 100

tickers = sorted(trades["ticker"].unique())

for ticker in tickers:
    pct    = pivot_pct.loc[ticker]
    pnl_yr = pivot_pnl.loc[ticker]
    anp_yr = pivot_anp.loc[ticker]
    cum_pnl = pnl_yr.sum()
    cum_anp = anp_yr.sum()
    cum_pct = (cum_pnl / cum_anp * 100) if cum_anp > 0 else 0

    fig, ax = plt.subplots(figsize=(10, 5))
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)
    for s in ("top", "right"): ax.spines[s].set_visible(False)
    for s in ("bottom", "left"): ax.spines[s].set_color(SPINE)
    ax.grid(True, color=GRID, lw=0.7, alpha=0.7)
    ax.set_axisbelow(True)

    plot_vals = pct.fillna(0).values
    colors    = [GREEN if v > 0 else RED for v in plot_vals]
    bars      = ax.bar([str(y) for y in pct.index], plot_vals,
                       color=colors, edgecolor=BG, lw=1.0)
    ax.axhline(0, color=SPINE, lw=0.6, ls="--")
    ax.set_title(
        f"{ticker} — Annual Return on Net Premium   "
        f"|   Cumulative {cum_pct:+.0f}%   "
        f"(\\${cum_pnl:,.0f} P&L on \\${cum_anp:,.0f} net premium)",
        fontsize=11, fontweight="bold", pad=12)
    ax.set_ylabel("Return on net premium")
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0f}%"))

    nonzero = [v for v in plot_vals if abs(v) > 1e-9]
    ymax    = max([abs(v) for v in nonzero] + [10])
    offset  = ymax * 0.04
    for bar, val, raw in zip(bars, plot_vals, pct.values):
        if pd.isna(raw) or abs(raw) < 0.5:
            continue
        ax.text(bar.get_x() + bar.get_width()/2,
                bar.get_height() + (offset if val > 0 else -offset),
                f"{val:+.0f}%",
                ha="center", va="bottom" if val > 0 else "top",
                color=TEXT, fontsize=8)

    plt.xticks(rotation=45)
    fig.savefig(OUT / f"{ticker}.png", dpi=170, bbox_inches="tight",
                facecolor=BG)
    plt.close(fig)

print(f"Saved {len(tickers)} charts -> charts/by_ticker_annual/")
