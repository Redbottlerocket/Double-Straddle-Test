"""
Portfolio greeks charts (SPX-equivalent dollar terms).

Renders four time-series charts into results/charts/:
  11_portfolio_delta.png  -- $ per 1% SPX move
  12_portfolio_gamma.png  -- change in $delta per 1% SPX move
  13_portfolio_vega.png   -- $ per 1 vol point of VIX
  14_portfolio_theta.png  -- $ per calendar day (no scaling)

Plus a combined 4-panel summary:
  15_portfolio_greeks_dashboard.png
"""

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from pathlib import Path

ROOT = Path(__file__).parent.parent
OUT  = ROOT / "results" / "charts"
OUT.mkdir(parents=True, exist_ok=True)

# Anthropic-cream palette
BG, TEXT, GRID, SPINE = "#F5F1EB", "#2C2A26", "#D6CFC2", "#A39B8E"
BLUE, GREEN, RED, ORANGE, MUTED = "#4A6FA5", "#4A7C59", "#B0413E", "#D97757", "#8C857A"

plt.rcParams.update({
    "font.family":     "DejaVu Sans",
    "axes.edgecolor":  SPINE,
    "axes.labelcolor": TEXT,
    "xtick.color":     TEXT,
    "ytick.color":     TEXT,
    "text.color":      TEXT,
    "axes.titlecolor": TEXT,
})

def style(ax):
    ax.set_facecolor(BG)
    for s in ("top", "right"):  ax.spines[s].set_visible(False)
    for s in ("bottom", "left"): ax.spines[s].set_color(SPINE)
    ax.grid(True, color=GRID, lw=0.7, alpha=0.7)
    ax.set_axisbelow(True)

def new_fig(figsize=(12, 5)):
    fig, ax = plt.subplots(figsize=figsize)
    fig.patch.set_facecolor(BG)
    style(ax)
    return fig, ax

def save(fig, name):
    fig.savefig(OUT / f"{name}.png", dpi=170, bbox_inches="tight", facecolor=BG)
    plt.close(fig)
    print(f"  saved -> charts/{name}.png")

# --- Load ---
port = pd.read_parquet(ROOT / "results" / "portfolio_greeks.parquet")
port.index = pd.to_datetime(port.index)

# Smoothed 5-day rolling line for visual clarity (raw is very spiky around earnings)
SMOOTH = 5
def panel(ax, series, label, color, unit_label, title):
    raw = series
    smooth = series.rolling(SMOOTH).mean()
    ax.fill_between(raw.index, raw, 0, where=(raw >= 0),
                    color=color, alpha=0.15)
    ax.fill_between(raw.index, raw, 0, where=(raw < 0),
                    color=RED if color != RED else MUTED, alpha=0.15)
    ax.plot(raw.index, raw, color=color, lw=0.6, alpha=0.45,
            label=f"daily")
    ax.plot(smooth.index, smooth, color=color, lw=1.6,
            label=f"{SMOOTH}-day avg")
    avg = raw.mean()
    ax.axhline(avg, color=ORANGE, lw=1.0, ls="--",
               label=f"Avg {avg:+,.0f}")
    ax.axhline(0, color=SPINE, lw=0.6)
    ax.set_ylabel(unit_label)
    ax.set_title(title, fontsize=12, fontweight="bold", pad=12)
    ax.legend(loc="upper left", frameon=False, fontsize=9)

CHARTS = [
    ("11_portfolio_delta",  "delta_dollars", BLUE,
        "$ P&L per 1% SPX move",
        "Portfolio Delta  (SPX-equivalent $)"),
    ("12_portfolio_gamma",  "gamma_dollars", GREEN,
        "$ Δdelta per 1% SPX move",
        "Portfolio Gamma  (SPX-equivalent $)"),
    ("13_portfolio_vega",   "vega_dollars",  ORANGE,
        "$ P&L per 1 vol point of VIX",
        "Portfolio Vega   (VIX-equivalent $)"),
    ("14_portfolio_theta",  "theta_dollars", RED,
        "$ P&L per calendar day",
        "Portfolio Theta  ($ per day)"),
]

for name, col, color, unit, title in CHARTS:
    fig, ax = new_fig((12, 5))
    panel(ax, port[col], col, color, unit, title)
    save(fig, name)

# --- Combined 4-panel dashboard ---
fig = plt.figure(figsize=(18, 10))
fig.patch.set_facecolor(BG)
gs = gridspec.GridSpec(2, 2, figure=fig, hspace=0.40, wspace=0.20)

for (name, col, color, unit, title), pos in zip(CHARTS, [(0,0),(0,1),(1,0),(1,1)]):
    ax = fig.add_subplot(gs[pos])
    style(ax)
    panel(ax, port[col], col, color, unit, title)

fig.suptitle("Portfolio Greeks Over Time   (SPX/VIX-equivalent dollars, β-scaled)",
             color=TEXT, fontsize=14, fontweight="bold", y=0.995)
fig.savefig(OUT / "15_portfolio_greeks_dashboard.png",
            dpi=170, bbox_inches="tight", facecolor=BG)
plt.close(fig)
print("  saved -> charts/15_portfolio_greeks_dashboard.png")

print(f"\nAll portfolio greek charts in {OUT.relative_to(ROOT)}/")
