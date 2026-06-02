"""
Single-trade calendar straddle payout — at short-leg expiry.

This is the "what you know at entry" payout: combined P&L if held to
short_exp, with the long leg priced via Black-Scholes using the entry-
implied IV held constant. At short expiry the long leg still has
(long_exp - short_exp) days of time value, which is exactly why this
strategy can be profitable.

Configurable at top: TICKER, EARN_YEAR, EARN_INDEX.
"""
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path
import sys

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "strategy"))
from greeks import bs_price, implied_vol

# ---- Pick a trade ----------------------------------------------------------
TICKER     = "GOOGL"
EARN_YEAR  = 2022
EARN_INDEX = 1    # 0 = first earnings of that year, 1 = second, etc.

DIV_YIELD = {
    "AAPL": 0.0055, "ABNB": 0.0000, "ACM":  0.0070, "ADBE": 0.0000,
    "AMAT": 0.0070, "AMD":  0.0000, "AMGN": 0.0300, "AMZN": 0.0000,
    "ASML": 0.0080, "AVGO": 0.0180, "BABA": 0.0000, "CSCO": 0.0280,
    "GOOGL":0.0000, "INTC": 0.0320, "META": 0.0000, "MSFT": 0.0085,
    "MU":   0.0040, "NFLX": 0.0000, "NVDA": 0.0015, "ORCL": 0.0120,
    "PDD":  0.0000, "PLTR": 0.0000, "QCOM": 0.0250, "TSLA": 0.0000,
    "ZM":   0.0000,
}

# ---- Load ------------------------------------------------------------------
trades = pd.read_csv(ROOT / "results" / "trades.csv", parse_dates=[
    "earn_dt", "short_entry_dt", "long_entry_dt", "short_exit_dt", "long_exit_dt"])
sched  = pd.read_csv(ROOT / "data" / "trade_schedule.csv", parse_dates=[
    "earn_dt", "next_earn", "short_exp", "long_exp"])
tbill  = pd.read_csv(ROOT / "data" / "tbill_rate.csv",
                     parse_dates=["observation_date"])
tbill  = tbill.rename(columns={"observation_date": "date", "DTB3": "rate"})
tbill["rate"] = tbill["rate"] / 100
tbill  = tbill.set_index("date")["rate"]
tbill  = tbill.reindex(pd.date_range(tbill.index.min(), tbill.index.max(),
                                     freq="D")).ffill()

m = trades.merge(sched[["ticker","earn_dt","next_earn","strike","spot",
                        "short_exp","long_exp"]], on=["ticker","earn_dt"])
candidates = m[(m["ticker"]==TICKER) & (m["earn_dt"].dt.year==EARN_YEAR)]
if candidates.empty:
    raise SystemExit(f"No trade found for {TICKER} {EARN_YEAR}")
row = candidates.iloc[EARN_INDEX]

# ---- Pull numbers ----------------------------------------------------------
K          = float(row["strike"])
spot_entry = float(row["spot"])
sc_entry, sp_entry = float(row["sc_entry"]), float(row["sp_entry"])
lc_entry, lp_entry = float(row["lc_entry"]), float(row["lp_entry"])
lc_exit,  lp_exit  = float(row["lc_exit"]),  float(row["lp_exit"])
short_credit = sc_entry + sp_entry          # per share
long_debit   = lc_entry + lp_entry          # per share
long_credit_actual = lc_exit + lp_exit      # per share

entry_dt    = pd.to_datetime(row["long_entry_dt"])
short_exp   = pd.to_datetime(row["short_exp"])
long_exp    = pd.to_datetime(row["long_exp"])
long_exit_dt = pd.to_datetime(row["long_exit_dt"])

r = float(tbill.asof(long_exit_dt))
q = DIV_YIELD.get(TICKER, 0.0)

# IV at entry, implied from entry mid prices on the long straddle
T_entry = max((long_exp - entry_dt).days / 365.25, 1/365.25)
iv_call = implied_vol(lc_entry, spot_entry, K, T_entry, r, q, "call")
iv_put  = implied_vol(lp_entry, spot_entry, K, T_entry, r, q, "put")
iv_use  = np.nanmean([iv_call, iv_put])
if np.isnan(iv_use):
    iv_use = 0.30  # fallback

# Time remaining on the long leg AT SHORT EXPIRY (this is the "at entry" payout view)
T_short_exp = max((long_exp - short_exp).days / 365.25, 1/365.25)
days_long_remaining = (long_exp - short_exp).days

# ---- Build payout curves ---------------------------------------------------
S_range = np.linspace(spot_entry * 0.75, spot_entry * 1.25, 400)

# Short straddle P&L at short_exp (held to expiry, intrinsic settlement)
short_pnl_ps = short_credit - np.abs(S_range - K)
short_pnl    = short_pnl_ps * 100

# Long straddle MARK at short_exp (BS value with time still remaining)
# This is what you'd realise if you closed both legs simultaneously at short_exp.
long_value_ps = np.array([
    bs_price(s, K, T_short_exp, r, q, iv_use, "call")
    + bs_price(s, K, T_short_exp, r, q, iv_use, "put")
    for s in S_range
])
long_pnl_ps = long_value_ps - long_debit
long_pnl    = long_pnl_ps * 100

combined = short_pnl + long_pnl

# Actual realised total P&L (final outcome, after holding long to long_exit_dt)
actual_total  = float(row["total_pnl"])
actual_return = float(row["return_pct"])

# ---- Plot (cream/parchment palette to match newer charts) -------------------
BG     = "#F5F1EB"
TEXT   = "#2C2A26"
GRID   = "#D6CFC2"
SPINE  = "#A39B8E"
BLUE   = "#4A6FA5"
GREEN  = "#4A7C59"
RED    = "#B0413E"
ORANGE = "#D97757"
MUTED  = "#8C857A"

plt.rcParams.update({
    "font.family":     "DejaVu Sans",
    "axes.edgecolor":  SPINE,
    "axes.labelcolor": TEXT,
    "xtick.color":     TEXT,
    "ytick.color":     TEXT,
    "text.color":      TEXT,
    "axes.titlecolor": TEXT,
})

fig, ax = plt.subplots(figsize=(12, 7.5))
fig.patch.set_facecolor(BG)
ax.set_facecolor(BG)
for s in ("top", "right"):  ax.spines[s].set_visible(False)
for s in ("bottom", "left"): ax.spines[s].set_color(SPINE)
ax.grid(True, color=GRID, lw=0.7, alpha=0.7)
ax.set_axisbelow(True)

# Combined first, behind
ax.plot(S_range, combined, color=ORANGE, lw=3.0,
        label="Combined (calendar straddle)", zorder=3)
ax.fill_between(S_range, combined, 0, where=(combined > 0),
                color=GREEN, alpha=0.12, zorder=1)
ax.fill_between(S_range, combined, 0, where=(combined < 0),
                color=RED,   alpha=0.12, zorder=1)

# Legs
ax.plot(S_range, short_pnl, color=RED, lw=2.0, ls="--",
        label=f"Short straddle — intrinsic at expiry", zorder=4)
ax.plot(S_range, long_pnl,  color=BLUE, lw=2.0, ls="--",
        label=f"Long straddle — BS mark with {days_long_remaining}d remaining "
              f"(IV={iv_use:.0%})", zorder=4)

# Reference lines
ax.axhline(0, color=MUTED, lw=0.8, ls="--")
ax.axvline(K,          color=ORANGE, lw=1.0, ls=":", alpha=0.8)
ax.axvline(spot_entry, color=TEXT,   lw=1.0, ls=":", alpha=0.4)

ymin, ymax = ax.get_ylim()
ax.text(K, ymax * 0.95, f" Strike  ${K:.0f}", color=ORANGE,
        fontsize=9, va="top", ha="left", fontweight="bold")
ax.text(spot_entry, ymin + (ymax - ymin) * 0.04,
        f"Spot @ entry\n${spot_entry:.2f}",
        color=TEXT, fontsize=8.5, va="bottom", ha="center")

realised_str = (f"Actual outcome (held long to {long_exit_dt:%Y-%m-%d}): "
                f"total ${actual_total:.0f}  ({actual_return:+.1f}% on net premium)")
ax.set_title(f"{TICKER}  earnings {row['earn_dt']:%Y-%m-%d}  —  Calendar straddle payout "
             f"AT SHORT EXPIRY ({short_exp:%Y-%m-%d})\n"
             f"Net premium paid: ${(long_debit - short_credit)*100:,.0f}   |   "
             + realised_str,
             fontsize=11)
ax.set_xlabel(f"Stock price at short expiry ({short_exp:%Y-%m-%d})", fontsize=10)
ax.set_ylabel("P&L per 1-contract position ($)", fontsize=10)

ax.legend(loc="upper right", facecolor=BG, edgecolor=SPINE, fontsize=9,
          framealpha=0.95)

out = ROOT / "results" / f"payout_example_{TICKER}_{row['earn_dt']:%Y%m%d}.png"
plt.tight_layout()
plt.savefig(out, dpi=170, bbox_inches="tight", facecolor=BG)
print(f"Saved -> {out}")
print()
print(f"Trade: {TICKER} earnings {row['earn_dt']:%Y-%m-%d}")
print(f"  Strike            : ${K:.2f}")
print(f"  Spot at entry     : ${spot_entry:.2f}")
print(f"  Short credit (ps) : ${short_credit:.2f}")
print(f"  Long  debit  (ps) : ${long_debit:.2f}")
print(f"  Net premium       : ${(long_debit-short_credit)*100:.0f} per position")
print(f"  Entry IV used     : {iv_use:.1%}")
print(f"  Days to long_exp at exit: {(long_exp-long_exit_dt).days}")
print(f"  Realised P&L      : ${actual_total:.0f}  ({actual_return:+.1f}%)")
