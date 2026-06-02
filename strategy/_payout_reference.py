"""
Textbook calendar straddle payout — idealised reference chart.

Shows the canonical "tent" shape: max profit at the strike, two breakevens,
loss capped near the net debit on either tail.

Assumptions (idealised):
  - Spot = strike at entry
  - Short straddle expires at intrinsic on short_exp
  - Long straddle priced via Black-Scholes at short_exp, IV held at entry IV
  - No dividends, no rate moves
"""
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path
import sys

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "strategy"))
from greeks import bs_price

# ---- Idealised parameters --------------------------------------------------
K          = 100.0           # strike
IV         = 0.30            # implied vol (30%)
r          = 0.04            # risk-free rate
q          = 0.0             # no divs
days_short = 7               # near-term straddle: 1 week
days_long  = 90              # far-term straddle: ~3 months
# Price the entry premiums at entry (spot = K)
T_short_entry = days_short / 365.25
T_long_entry  = days_long  / 365.25
short_credit  = (bs_price(K, K, T_short_entry, r, q, IV, "call")
                 + bs_price(K, K, T_short_entry, r, q, IV, "put"))
long_debit    = (bs_price(K, K, T_long_entry,  r, q, IV, "call")
                 + bs_price(K, K, T_long_entry,  r, q, IV, "put"))
net_debit_ps  = long_debit - short_credit

# Time remaining on the long leg at short_exp
days_long_at_short_exp = days_long - days_short
T_long_at_short_exp    = days_long_at_short_exp / 365.25

# ---- Payout curves at short_exp -------------------------------------------
S = np.linspace(K * 0.7, K * 1.3, 500)

short_pnl_ps = short_credit - np.abs(S - K)
long_value_ps = np.array([
    bs_price(s, K, T_long_at_short_exp, r, q, IV, "call")
    + bs_price(s, K, T_long_at_short_exp, r, q, IV, "put")
    for s in S
])
long_pnl_ps = long_value_ps - long_debit
combined_ps = short_pnl_ps + long_pnl_ps
combined    = combined_ps * 100

# Find breakevens (combined = 0)
sign_changes = np.where(np.diff(np.sign(combined_ps)))[0]
be_lower = be_upper = None
if len(sign_changes) >= 2:
    i_lo, i_hi = sign_changes[0], sign_changes[-1]
    be_lower = float(np.interp(0, combined_ps[i_lo:i_lo+2][::int(np.sign(combined_ps[i_lo+1]-combined_ps[i_lo]))],
                                S[i_lo:i_lo+2][::int(np.sign(combined_ps[i_lo+1]-combined_ps[i_lo]))]))
    be_upper = float(np.interp(0, combined_ps[i_hi:i_hi+2][::int(np.sign(combined_ps[i_hi+1]-combined_ps[i_hi]))],
                                S[i_hi:i_hi+2][::int(np.sign(combined_ps[i_hi+1]-combined_ps[i_hi]))]))

max_profit_ps = combined_ps.max()
max_profit    = max_profit_ps * 100
max_loss_left  = combined_ps[0]  * 100
max_loss_right = combined_ps[-1] * 100

# ---- Plot ------------------------------------------------------------------
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
    "text.usetex":     False,
    "mathtext.default":"regular",
    "axes.formatter.use_mathtext": False,
})
# Disable matplotlib's $-mathtext so plain dollar signs render correctly
import matplotlib as mpl
mpl.rcParams["text.parse_math"] = False

fig, ax = plt.subplots(figsize=(12, 7.5))
fig.patch.set_facecolor(BG); ax.set_facecolor(BG)
for s in ("top","right"): ax.spines[s].set_visible(False)
for s in ("bottom","left"): ax.spines[s].set_color(SPINE)
ax.grid(True, color=GRID, lw=0.7, alpha=0.7); ax.set_axisbelow(True)

# Profit/loss shading
ax.fill_between(S, combined, 0, where=(combined > 0), color=GREEN, alpha=0.18, zorder=1)
ax.fill_between(S, combined, 0, where=(combined < 0), color=RED,   alpha=0.18, zorder=1)

ax.plot(S, short_pnl_ps * 100, color=RED,  lw=2.0, ls="--", label="Short straddle (intrinsic at expiry)", zorder=4)
ax.plot(S, long_pnl_ps  * 100, color=BLUE, lw=2.0, ls="--",
        label=f"Long straddle (BS, {days_long_at_short_exp}d remaining, IV={IV:.0%})", zorder=4)
ax.plot(S, combined,            color=ORANGE, lw=3.0, label="Combined calendar straddle", zorder=5)

ax.axhline(0, color=MUTED, lw=0.8, ls="--")
ax.axvline(K, color=ORANGE, lw=1.0, ls=":", alpha=0.8)

# Annotate max profit at strike
ax.annotate(f"Max profit\n+${max_profit:.0f}", xy=(K, max_profit),
            xytext=(K, max_profit + 80),
            ha="center", color=GREEN, fontsize=10, fontweight="bold",
            arrowprops=dict(arrowstyle="->", color=GREEN, lw=1.2))

# Annotate breakevens
if be_lower is not None and be_upper is not None:
    ax.axvline(be_lower, color=MUTED, lw=0.7, ls=":", alpha=0.7)
    ax.axvline(be_upper, color=MUTED, lw=0.7, ls=":", alpha=0.7)
    ax.text(be_lower, 0, f" BE\n ${be_lower:.1f}", color=MUTED, fontsize=9,
            va="bottom", ha="left")
    ax.text(be_upper, 0, f"BE\n${be_upper:.1f} ", color=MUTED, fontsize=9,
            va="bottom", ha="right")

# Annotate max loss zones
ax.annotate(f"Max loss → ~-net debit\n(${max_loss_left:.0f})",
            xy=(S[0], max_loss_left), xytext=(S[0] + 4, max_loss_left + 50),
            color=RED, fontsize=9,
            arrowprops=dict(arrowstyle="->", color=RED, lw=1.0))
ax.annotate(f"Max loss → ~-net debit\n(${max_loss_right:.0f})",
            xy=(S[-1], max_loss_right), xytext=(S[-1] - 4, max_loss_right + 50),
            color=RED, fontsize=9, ha="right",
            arrowprops=dict(arrowstyle="->", color=RED, lw=1.0))

ax.set_title(f"Textbook Calendar Straddle Payout — at short expiry\n"
             f"Strike ${K:.0f}  |  IV {IV:.0%}  |  Short: {days_short}d  Long: {days_long}d  |  "
             f"Net debit ${net_debit_ps*100:.0f}",
             fontsize=11)
ax.set_xlabel("Stock price at short expiry", fontsize=10)
ax.set_ylabel("P&L per 1-contract position ($)", fontsize=10)
ax.legend(loc="lower center", facecolor=BG, edgecolor=SPINE, fontsize=9, framealpha=0.95)

out = ROOT / "results" / "payout_reference_calendar.png"
plt.tight_layout()
plt.savefig(out, dpi=170, bbox_inches="tight", facecolor=BG)
print(f"Saved -> {out}")
print()
print(f"Idealised calendar straddle, K=${K:.0f}, IV={IV:.0%}")
print(f"  Short straddle credit (entry) : ${short_credit:.2f}/sh = ${short_credit*100:.0f}")
print(f"  Long straddle  debit  (entry) : ${long_debit:.2f}/sh  = ${long_debit*100:.0f}")
print(f"  Net debit                      : ${net_debit_ps:.2f}/sh  = ${net_debit_ps*100:.0f}")
print(f"  Max profit at strike (at short_exp): +${max_profit:.0f}")
if be_lower is not None:
    print(f"  Breakevens                       : ${be_lower:.2f}  /  ${be_upper:.2f}")
print(f"  Max loss in far tails            : ~-${net_debit_ps*100:.0f} (bounded at net debit)")
