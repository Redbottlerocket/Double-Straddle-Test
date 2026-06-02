"""
Daily portfolio book using liquidation marks.

For each open leg, each trading day it is held:
  - LONG legs marked at BID  (price you would receive selling)
  - SHORT legs marked at ASK (price you would pay to buy back)
  - Forward-fill at the leg level if a quote is missing that day
  - Entry-day mark = entry execution price, exit-day mark = exit execution price
    (so the daily PnL series ties out exactly to trades.csv total_pnl)

Daily aggregates:
  - gross_notional   : sum of |signed market value| across open legs (AUM proxy)
  - net_exposure     : signed market value (longs +, shorts -)
  - open_legs        : leg count
  - daily_pnl        : sum of per-leg day-over-day mark changes
  - daily_trade_flow : |entry $| + |exit $| of any legs that opened or closed today
  - cum_pnl          : cumulative daily_pnl

Outputs results/portfolio_daily.csv.
"""

import pandas as pd
import numpy as np
from pathlib import Path

ROOT = Path(__file__).parent.parent

trades = pd.read_csv(ROOT / "results" / "trades.csv", parse_dates=[
    "earn_dt", "short_entry_dt", "long_entry_dt",
    "short_exit_dt", "long_exit_dt"])

sched = pd.read_csv(ROOT / "data" / "trade_schedule.csv")
sched["earn_dt"] = pd.to_datetime(sched["earn_dt"])
trades = trades.merge(
    sched[["ticker", "earn_dt", "short_call", "short_put", "long_call", "long_put"]],
    on=["ticker", "earn_dt"], how="left"
)

opts = pd.read_parquet(ROOT / "data" / "options_daily.parquet")
opts["date"] = pd.to_datetime(opts["date"])

equity = pd.read_parquet(ROOT / "data" / "equity_prices.parquet")
equity["date"] = pd.to_datetime(equity["date"])
trading_days = sorted(equity["date"].unique())

# Per-symbol sorted bid/ask series for forward-fill lookups
sym_series = {}
for sym, grp in opts.sort_values("date").groupby("symbol"):
    sym_series[sym] = grp.set_index("date")[["bid", "ask"]]

def get_liq_mark(symbol, date, side):
    """Liquidation mark on date; forward-fills from last available quote."""
    s = sym_series.get(symbol)
    if s is None:
        return np.nan
    col = s[side]
    if date in col.index:
        v = col.loc[date]
        if not np.isnan(v):
            return v
    prior = col[col.index <= date]
    return prior.iloc[-1] if len(prior) else np.nan

# (leg_label, sign, liq_side, sym_col, entry_px_col, exit_px_col, entry_dt_col, exit_dt_col)
LEG_SPECS = [
    ("sc", -1, "ask", "short_call", "sc_entry", "sc_exit", "short_entry_dt", "short_exit_dt"),
    ("sp", -1, "ask", "short_put",  "sp_entry", "sp_exit", "short_entry_dt", "short_exit_dt"),
    ("lc", +1, "bid", "long_call",  "lc_entry", "lc_exit", "long_entry_dt",  "long_exit_dt"),
    ("lp", +1, "bid", "long_put",   "lp_entry", "lp_exit", "long_entry_dt",  "long_exit_dt"),
]

rows = []
n_trades = len(trades)

for tid, t in trades.iterrows():
    if tid % 100 == 0:
        print(f"  {tid}/{n_trades} trades...", end="\r")

    for leg, sign, side, sym_col, ent_px_col, ext_px_col, ent_dt_col, ext_dt_col in LEG_SPECS:
        symbol   = t[sym_col].strip()
        entry_dt = t[ent_dt_col]
        exit_dt  = t[ext_dt_col]
        ent_px   = float(t[ent_px_col])
        ext_px   = float(t[ext_px_col])

        # include entry_dt and exit_dt even if they fall on non-trading days
        # (e.g. Saturday option expirations) so the telescope closes correctly
        days_set = {d for d in trading_days if entry_dt <= d <= exit_dt}
        days_set.add(entry_dt)
        days_set.add(exit_dt)
        days = sorted(days_set)
        if not days:
            continue

        prev_mark = ent_px
        for d in days:
            if d == entry_dt:
                mark = ent_px
            elif d == exit_dt:
                mark = ext_px
            else:
                m = get_liq_mark(symbol, d, side)
                mark = m if not np.isnan(m) else prev_mark

            day_pnl   = sign * (mark - prev_mark) * 100
            signed_mv = sign * mark * 100

            flow = 0.0
            if d == entry_dt: flow += abs(ent_px) * 100
            if d == exit_dt:  flow += abs(ext_px) * 100

            rows.append({
                "date":      d,
                "signed_mv": signed_mv,
                "day_pnl":   day_pnl,
                "flow":      flow,
            })
            prev_mark = mark

print(f"\n  {n_trades}/{n_trades} trades. Aggregating...")

book = pd.DataFrame(rows)
daily = book.groupby("date").agg(
    gross_notional   = ("signed_mv", lambda s: s.abs().sum()),
    net_exposure     = ("signed_mv", "sum"),
    open_legs        = ("signed_mv", "count"),
    daily_pnl        = ("day_pnl",   "sum"),
    daily_trade_flow = ("flow",      "sum"),
).sort_index()
daily["cum_pnl"] = daily["daily_pnl"].cumsum()

out = ROOT / "results" / "portfolio_daily.csv"
daily.to_csv(out)

# Reconciliation: daily_pnl total should equal trades.csv total_pnl
recon_daily = daily["daily_pnl"].sum()
recon_trade = trades["total_pnl"].sum()
print(f"Saved {len(daily):,} daily rows -> results/portfolio_daily.csv")
print(f"Reconciliation: sum(daily_pnl)=${recon_daily:,.2f}  vs  sum(trades.total_pnl)=${recon_trade:,.2f}  diff=${recon_daily - recon_trade:,.2f}")
