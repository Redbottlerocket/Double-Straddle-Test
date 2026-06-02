"""
Build data/symbol_list_wide.csv without any Databento calls.

This is the symbol-expansion portion of 01b_cost_estimate_wide.py, lifted out
so it can run without DATABENTO_API_KEY (useful when you just want the CSV to
ship to a Colab notebook for someone else to pull).

Same knobs and same logic as 01b -- output is identical.
"""
import sys
from pathlib import Path
import pandas as pd
import numpy as np

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(Path(__file__).parent))
from options_utils import atm_strike, osi_symbol

K_STRIKES = 5
WINDOW_TD = 15

sched = pd.read_csv(ROOT / "data" / "trade_schedule.csv", parse_dates=[
    "earn_dt", "next_earn", "entry_dt", "short_exp", "long_exp"])
equity = pd.read_parquet(ROOT / "data" / "equity_prices.parquet")
equity["date"] = pd.to_datetime(equity["date"])
equity_idx = equity.set_index("date")
trading_days = sorted(equity["date"].unique())


def nth_td_before(dt, n):
    pos = next((i for i, d in enumerate(trading_days) if d >= dt), None)
    if pos is None:
        return None
    return trading_days[pos - n] if pos - n >= 0 else None


def nth_td_after(dt, n):
    pos = next((i for i, d in enumerate(trading_days) if d > dt), None)
    if pos is None:
        return None
    return trading_days[pos + n - 1] if pos + n - 1 < len(trading_days) else trading_days[-1]


def spot_range(ticker, center_dt, td_each_side):
    if ticker not in equity_idx.columns:
        return None, None
    start_dt = nth_td_before(center_dt, td_each_side) or trading_days[0]
    end_dt   = nth_td_after(center_dt,  td_each_side) or trading_days[-1]
    col = equity_idx[ticker].dropna()
    window = col[(col.index >= start_dt) & (col.index <= end_dt)]
    if window.empty:
        return None, None
    return float(window.min()), float(window.max())


def strike_increment(price: float) -> float:
    if   price <=   5:  return 0.50
    elif price <=  25:  return 1.00
    elif price <=  50:  return 2.50
    elif price <= 200:  return 5.00
    elif price <= 500:  return 10.0
    elif price <= 1000: return 25.0
    elif price <= 2000: return 50.0
    else:               return 100.0


symbol_set = set()
per_cycle_counts = []

for _, row in sched.iterrows():
    ticker     = row["ticker"]
    earn_dt    = row["earn_dt"]
    next_earn  = row["next_earn"]
    strike     = float(row["strike"])
    spot       = float(row["spot"])
    short_exp  = row["short_exp"].date()
    long_exp   = row["long_exp"].date()
    inc        = strike_increment(spot)

    strikes = {strike + k * inc for k in range(-K_STRIKES, K_STRIKES + 1)}

    if WINDOW_TD > 0:
        for center in (earn_dt, next_earn):
            lo, hi = spot_range(ticker, center, WINDOW_TD)
            if lo is None:
                continue
            lo_atm, hi_atm = atm_strike(lo), atm_strike(hi)
            k = lo_atm
            while k <= hi_atm:
                strikes.add(round(k, 4))
                k += inc

    strikes = {round(s, 4) for s in strikes if s > 0}

    cycle_syms = set()
    for s in strikes:
        for exp in (short_exp, long_exp):
            cycle_syms.add(osi_symbol(ticker, exp, s, "call"))
            cycle_syms.add(osi_symbol(ticker, exp, s, "put"))
    symbol_set.update(cycle_syms)
    per_cycle_counts.append(len(cycle_syms))

symbols = sorted(symbol_set)
print(f"K_STRIKES : +/- {K_STRIKES}  ({2*K_STRIKES+1} anchor strikes)")
print(f"WINDOW_TD : +/- {WINDOW_TD} TDs around earn_dt AND next_earn")
print(f"Cycles    : {len(sched):,}")
print(f"Avg contracts/cycle: {np.mean(per_cycle_counts):.1f}")
print(f"Max contracts/cycle: {max(per_cycle_counts)}")
print(f"Unique contracts   : {len(symbols):,}")

out = ROOT / "data" / "symbol_list_wide.csv"
pd.Series(symbols, name="symbol").to_csv(out, index=False)
print(f"\nWrote {len(symbols):,} symbols -> {out}")
