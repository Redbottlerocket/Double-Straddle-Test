"""
López de Prado backtest statistics (Advances in Financial ML, Ch. 14).

Reads results/portfolio_daily.csv + results/trades.csv and reports:

  General characteristics (14.3):
    - Time range
    - Average AUM           (gross notional, liquidation marks)
    - Maximum AUM
    - Avg net exposure
    - Leverage              (gross notional / |net exposure|, market-neutral framing)
    - Ratio of longs        (% of position-days where net exposure > 0)
    - Frequency of bets     (trades per year)
    - Avg holding period    (calendar days)
    - Annualized turnover   ($ traded per year / avg AUM)

  Performance (14.4):
    - Total PnL
    - PnL from long leg / short leg
    - TWRR cumulative + annualized
    - Hit ratio
    - Avg return on hits / misses (%)

Saves results/lopez_stats.csv.
"""

import pandas as pd
import numpy as np
from pathlib import Path

ROOT   = Path(__file__).parent.parent
daily  = pd.read_csv(ROOT / "results" / "portfolio_daily.csv", parse_dates=["date"]).set_index("date")
trades = pd.read_csv(ROOT / "results" / "trades.csv", parse_dates=[
    "earn_dt", "short_entry_dt", "long_entry_dt",
    "short_exit_dt", "long_exit_dt"])

TPY = 252  # trading days per year

# ---------------------------------------------------------------------------
# General characteristics
# ---------------------------------------------------------------------------
start_dt = daily.index.min()
end_dt   = daily.index.max()
n_days   = len(daily)
years    = n_days / TPY

avg_aum  = daily["gross_notional"].mean()
max_aum  = daily["gross_notional"].max()
avg_net  = daily["net_exposure"].mean()
# Leverage as gross/|net|: how much gross position per unit of directional risk.
# (With the gross-notional AUM choice, classical "leverage = gross/equity" = 1 by
# construction, so this framing surfaces the offsetting structure of the book.)
leverage = avg_aum / abs(avg_net) if avg_net != 0 else np.nan

ratio_longs = (daily["net_exposure"] > 0).mean()

n_trades  = len(trades)
freq_bets = n_trades / years if years > 0 else np.nan

hp_short = (trades["short_exit_dt"] - trades["short_entry_dt"]).dt.days.mean()
hp_long  = (trades["long_exit_dt"]  - trades["long_entry_dt"]).dt.days.mean()
hp_full  = (trades[["short_exit_dt", "long_exit_dt"]].max(axis=1)
            - trades[["short_entry_dt", "long_entry_dt"]].min(axis=1)
           ).dt.days.mean()

total_flow   = daily["daily_trade_flow"].sum()
ann_turnover = (total_flow / years) / avg_aum if avg_aum > 0 else np.nan

# ---------------------------------------------------------------------------
# Performance
# ---------------------------------------------------------------------------
total_pnl     = daily["daily_pnl"].sum()
pnl_long_leg  = trades["long_pnl"].sum()
pnl_short_leg = trades["short_pnl"].sum()

# TWRR: daily return = day_pnl / previous-day gross notional, then geometrically link
prev_aum  = daily["gross_notional"].shift(1).replace(0, np.nan)
daily_ret = (daily["daily_pnl"] / prev_aum).fillna(0)
twrr_cum  = (1 + daily_ret).prod() - 1
ann_twrr  = (1 + twrr_cum) ** (TPY / n_days) - 1 if n_days > 0 else np.nan

hits   = trades[trades["total_pnl"] > 0]
misses = trades[trades["total_pnl"] < 0]
hit_ratio      = len(hits) / len(trades) if len(trades) else np.nan
avg_ret_hits   = hits["return_pct"].mean()
avg_ret_misses = misses["return_pct"].mean()

# ---------------------------------------------------------------------------
# Print
# ---------------------------------------------------------------------------
print("=" * 64)
print("LÓPEZ DE PRADO BACKTEST STATISTICS   (Ch. 14)")
print("=" * 64)
print("\n-- General characteristics --")
print(f"Time range            : {start_dt.date()}  ->  {end_dt.date()}   ({years:.2f} yrs)")
print(f"Average AUM           : ${avg_aum:>16,.0f}   (gross notional, liq. marks)")
print(f"Maximum AUM           : ${max_aum:>16,.0f}")
print(f"Avg net exposure      : ${avg_net:>16,.0f}")
print(f"Leverage (gross/|net|): {leverage:>17.2f}x")
print(f"Ratio of longs        : {ratio_longs*100:>16.1f}%   (% of days net long)")
print(f"Frequency of bets     : {freq_bets:>17.1f}    (trades / year)")
print(f"Avg holding period    : {hp_full:>17.1f}    (calendar days, full straddle)")
print(f"  short leg           : {hp_short:>17.1f}")
print(f"  long  leg           : {hp_long:>17.1f}")
print(f"Annualized turnover   : {ann_turnover:>17.2f}x")

print("\n-- Performance --")
print(f"Total PnL             : ${total_pnl:>16,.2f}")
print(f"  short-leg PnL       : ${pnl_short_leg:>16,.2f}")
print(f"  long-leg  PnL       : ${pnl_long_leg:>16,.2f}")
print(f"TWRR (cumulative)     : {twrr_cum*100:>16.2f}%")
print(f"TWRR (annualized)     : {ann_twrr*100:>16.2f}%")
print(f"Hit ratio             : {hit_ratio*100:>16.1f}%")
print(f"Avg return on hits    : {avg_ret_hits:>16.1f}%")
print(f"Avg return on misses  : {avg_ret_misses:>16.1f}%")

# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------
summary = pd.DataFrame([{
    "start_dt": start_dt.date(), "end_dt": end_dt.date(), "years": round(years, 2),
    "avg_aum": round(avg_aum, 2), "max_aum": round(max_aum, 2),
    "avg_net_exposure": round(avg_net, 2),
    "leverage_gross_over_net": round(leverage, 2),
    "ratio_longs_pct": round(ratio_longs * 100, 2),
    "frequency_bets_per_year": round(freq_bets, 2),
    "avg_holding_days_trade": round(hp_full, 2),
    "avg_holding_days_short": round(hp_short, 2),
    "avg_holding_days_long":  round(hp_long, 2),
    "annualized_turnover": round(ann_turnover, 2),
    "total_pnl": round(total_pnl, 2),
    "pnl_short_leg": round(pnl_short_leg, 2),
    "pnl_long_leg":  round(pnl_long_leg, 2),
    "twrr_cumulative_pct": round(twrr_cum * 100, 2),
    "twrr_annualized_pct": round(ann_twrr * 100, 2),
    "hit_ratio_pct": round(hit_ratio * 100, 2),
    "avg_return_hits_pct":   round(avg_ret_hits, 2),
    "avg_return_misses_pct": round(avg_ret_misses, 2),
}])
summary.to_csv(ROOT / "results" / "lopez_stats.csv", index=False)
print("\nSaved -> results/lopez_stats.csv")
