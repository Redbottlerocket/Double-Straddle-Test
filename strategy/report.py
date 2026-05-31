"""
Strategy performance report for the calendar straddle earnings backtest.

Prints: overall stats, per-year breakdown, per-ticker breakdown.
Saves:  results/report_summary.csv, results/report_by_year.csv,
        results/report_by_ticker.csv
"""

import pandas as pd
import numpy as np
from pathlib import Path

ROOT   = Path(__file__).parent.parent
trades = pd.read_csv(ROOT / "results" / "trades.csv", parse_dates=["earn_dt"])

def sharpe(series, periods_per_year=4):
    """Annualised Sharpe (assume ~4 earnings cycles/year per stock)."""
    if series.std() == 0:
        return np.nan
    return (series.mean() / series.std()) * np.sqrt(periods_per_year)

def max_drawdown(cum_series):
    rolling_max = cum_series.cummax()
    dd = cum_series - rolling_max
    return dd.min()

# ---------------------------------------------------------------------------
# Overall stats
# ---------------------------------------------------------------------------
n          = len(trades)
n_win      = (trades["total_pnl"] > 0).sum()
win_rate   = n_win / n * 100
avg_pnl    = trades["total_pnl"].mean()
med_pnl    = trades["total_pnl"].median()
avg_ret    = trades["return_pct"].mean()
med_ret    = trades["return_pct"].median()
cum_pnl    = trades["total_pnl"].sum()
worst      = trades["total_pnl"].min()
best       = trades["total_pnl"].max()
avg_win    = trades.loc[trades["total_pnl"] > 0, "total_pnl"].mean()
avg_loss   = trades.loc[trades["total_pnl"] < 0, "total_pnl"].mean()
pf         = abs(avg_win / avg_loss) if avg_loss != 0 else np.nan
trades_cum = trades.sort_values("earn_dt")["total_pnl"].cumsum()
mdd        = max_drawdown(trades_cum)
sr         = sharpe(trades["return_pct"])

print("=" * 60)
print("CALENDAR STRADDLE EARNINGS BACKTEST  |  2016 - 2026")
print("=" * 60)
print(f"Trades executed     : {n:,}")
print(f"Win rate            : {win_rate:.1f}%  ({n_win}/{n})")
print(f"Avg P&L / trade     : ${avg_pnl:>10,.2f}")
print(f"Median P&L / trade  : ${med_pnl:>10,.2f}")
print(f"Avg return          : {avg_ret:>8.1f}%")
print(f"Median return       : {med_ret:>8.1f}%")
print(f"Avg win             : ${avg_win:>10,.2f}")
print(f"Avg loss            : ${avg_loss:>10,.2f}")
print(f"Profit factor       : {pf:>8.2f}x")
print(f"Best trade          : ${best:>10,.2f}")
print(f"Worst trade         : ${worst:>10,.2f}")
print(f"Cumulative P&L      : ${cum_pnl:>10,.2f}")
print(f"Max drawdown        : ${mdd:>10,.2f}")
print(f"Sharpe (annualised) : {sr:>8.2f}")

# ---------------------------------------------------------------------------
# Per-year breakdown
# ---------------------------------------------------------------------------
trades["year"] = trades["earn_dt"].dt.year
by_year = (
    trades.groupby("year")
    .agg(
        trades    = ("total_pnl", "count"),
        win_rate  = ("total_pnl", lambda x: (x > 0).mean() * 100),
        avg_pnl   = ("total_pnl", "mean"),
        cum_pnl   = ("total_pnl", "sum"),
        avg_ret   = ("return_pct", "mean"),
    )
    .round(1)
)

print("\n" + "=" * 60)
print("PER-YEAR BREAKDOWN")
print("=" * 60)
print(by_year.to_string())

# ---------------------------------------------------------------------------
# Per-ticker breakdown
# ---------------------------------------------------------------------------
by_ticker = (
    trades.groupby("ticker")
    .agg(
        trades    = ("total_pnl", "count"),
        win_rate  = ("total_pnl", lambda x: (x > 0).mean() * 100),
        avg_pnl   = ("total_pnl", "mean"),
        cum_pnl   = ("total_pnl", "sum"),
        avg_ret   = ("return_pct", "mean"),
        best      = ("total_pnl", "max"),
        worst     = ("total_pnl", "min"),
    )
    .sort_values("cum_pnl", ascending=False)
    .round(1)
)

print("\n" + "=" * 60)
print("PER-TICKER BREAKDOWN  (sorted by cumulative P&L)")
print("=" * 60)
print(by_ticker.to_string())

# ---------------------------------------------------------------------------
# Short vs long leg contribution
# ---------------------------------------------------------------------------
short_pnl_total = trades["short_pnl"].sum()
long_pnl_total  = trades["long_pnl"].sum()

print("\n" + "=" * 60)
print("LEG CONTRIBUTION")
print("=" * 60)
print(f"Short straddle total P&L : ${short_pnl_total:>10,.2f}")
print(f"Long straddle total P&L  : ${long_pnl_total:>10,.2f}")
print(f"Combined                 : ${short_pnl_total + long_pnl_total:>10,.2f}")

# ---------------------------------------------------------------------------
# Save CSVs
# ---------------------------------------------------------------------------
summary = pd.DataFrame([{
    "trades": n, "win_rate_pct": round(win_rate,1),
    "avg_pnl": round(avg_pnl,2), "median_pnl": round(med_pnl,2),
    "avg_return_pct": round(avg_ret,1), "profit_factor": round(pf,2),
    "cum_pnl": round(cum_pnl,2), "max_drawdown": round(mdd,2),
    "sharpe": round(sr,2), "best_trade": round(best,2), "worst_trade": round(worst,2),
}])
summary.to_csv(ROOT / "results" / "report_summary.csv", index=False)
by_year.to_csv(ROOT / "results" / "report_by_year.csv")
by_ticker.to_csv(ROOT / "results" / "report_by_ticker.csv")
print("\nSaved -> results/report_summary.csv, report_by_year.csv, report_by_ticker.csv")
