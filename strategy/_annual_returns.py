import pandas as pd
import numpy as np
from pathlib import Path

ROOT = Path(__file__).parent.parent

t = pd.read_csv(ROOT / "results" / "trades.csv", parse_dates=['earn_dt'])
t['year'] = t['earn_dt'].dt.year

by_year = t.groupby('year').agg(
    trades       = ('total_pnl', 'count'),
    total_pnl    = ('total_pnl', 'sum'),
    long_cost    = ('long_debit', 'sum'),
    net_premium  = ('net_premium', 'sum'),
    short_credit = ('short_credit', 'sum'),
)

by_year['ret_net_pct']  = (by_year['total_pnl'] / by_year['net_premium'].abs() * 100).round(1)
by_year['ret_long_pct'] = (by_year['total_pnl'] / by_year['long_cost'] * 100).round(1)

print("Annual Returns -- Calendar Straddle Earnings Strategy")
print("=" * 68)
print(f"{'Year':<6} {'Trades':<8} {'P&L':>10}  {'Net Prem':>11}  {'Ret/NetPrem':>11}  {'Ret/LongCost':>12}")
print("-" * 68)
for yr, row in by_year.iterrows():
    pnl_str  = f"${row.total_pnl:>9,.0f}"
    np_str   = f"${row.net_premium:>9,.0f}"
    print(f"{yr:<6} {int(row.trades):<8} {pnl_str}  {np_str}  {row.ret_net_pct:>10.1f}%  {row.ret_long_pct:>11.1f}%")

print("-" * 68)
tp  = by_year['total_pnl'].sum()
tnp = by_year['net_premium'].abs().sum()
tlc = by_year['long_cost'].sum()
print(f"{'TOTAL':<6} {int(by_year.trades.sum()):<8} ${tp:>9,.0f}  ${tnp:>9,.0f}  {tp/tnp*100:>10.1f}%  {tp/tlc*100:>11.1f}%")

print()
print("Ret/NetPrem  = P&L / |long cost - short credit|  (your actual cash at risk)")
print("Ret/LongCost = P&L / gross long straddle cost    (ignoring short credit offset)")
