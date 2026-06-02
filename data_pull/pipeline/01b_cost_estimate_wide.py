"""
Step 1b -- Cost estimator for a WIDER strike range
==================================================
Same expiries as 01_cost_estimate.py (short_exp, long_exp from trade_schedule.csv)
but pulls a band of strikes around ATM so the entry/exit timing sweep has a
true ATM contract for every candidate date inside a 3-week window around each
earnings event.

Coverage windows (configurable):
  - 3 weeks BEFORE earn_dt    (short-leg entry sweep)
  - 3 weeks AFTER  earn_dt    (short-leg exit-timing experiments)
  - 3 weeks BEFORE next_earn  (long-leg exit sweep)

Knobs
-----
K_STRIKES        : minimum strikes to each side of original ATM (per cycle).
                   Total anchor strikes per cycle = 2*K + 1.
                   K=5  -> 11 anchor strikes (band may be wider due to drift)
WINDOW_TD        : additional strikes to cover actual spot range in a window
                   of +/- WINDOW_TD trading days around each earnings date.
                   ~15 TDs ~ 3 weeks.

Output
------
  Prints estimated cost and writes data/symbol_list_wide.csv (NOT pulled).
  Run pipeline/02b_pull_data_wide.py to actually pull.

This script does NOT spend money. metadata.get_cost is free.
"""
import sys
from pathlib import Path
import pandas as pd
import numpy as np
import databento as db

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(Path(__file__).parent))
from config import DATABENTO_KEY, BACKTEST_START, BACKTEST_END, DATASET, SCHEMA
from options_utils import atm_strike, osi_symbol

# ---- Knobs ------------------------------------------------------------------
K_STRIKES = 5     # min strikes either side of original ATM
WINDOW_TD = 15    # +/- TDs of spot-drift coverage around each earnings date (~3 weeks)
BATCH     = 500

# ---- Load --------------------------------------------------------------------
sched = pd.read_csv(ROOT / "data" / "trade_schedule.csv", parse_dates=[
    "earn_dt", "next_earn", "entry_dt", "short_exp", "long_exp"])
equity = pd.read_parquet(ROOT / "data" / "equity_prices.parquet")
equity["date"] = pd.to_datetime(equity["date"])
equity_idx = equity.set_index("date")
trading_days = sorted(equity["date"].unique())

def nth_td_before(dt, n):
    pos = next((i for i, d in enumerate(trading_days) if d >= dt), None)
    if pos is None: return None
    return trading_days[pos - n] if pos - n >= 0 else None

def nth_td_after(dt, n):
    pos = next((i for i, d in enumerate(trading_days) if d > dt), None)
    if pos is None: return None
    return trading_days[pos + n - 1] if pos + n - 1 < len(trading_days) else trading_days[-1]

def spot_range(ticker, center_dt, td_each_side):
    """Min/max equity close over [center_dt - N TDs, center_dt + N TDs]."""
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

# ---- Build expanded symbol set ----------------------------------------------
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

    # Anchor: original ATM +- K * inc
    strikes = {strike + k * inc for k in range(-K_STRIKES, K_STRIKES + 1)}

    # Widen for spot drift +/- 3 weeks around earn_dt AND next_earn
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
print(f"WINDOW_TD : +/- {WINDOW_TD} TDs around earn_dt AND next_earn (~3 weeks each)")
print(f"Cycles    : {len(sched):,}")
print(f"Avg contracts/cycle: {np.mean(per_cycle_counts):.1f}")
print(f"Max contracts/cycle: {max(per_cycle_counts)}")
print(f"Unique contracts   : {len(symbols):,}  (vs current 3,506)")
print(f"Multiplier vs current pull: {len(symbols)/3506:.1f}x\n")

# ---- Cost query -------------------------------------------------------------
client = db.Historical(key=DATABENTO_KEY)
total = 0.0
n_batches = (len(symbols) + BATCH - 1) // BATCH
print(f"Querying Databento cost in {n_batches} batches of {BATCH}...")
for i in range(0, len(symbols), BATCH):
    batch = symbols[i:i + BATCH]
    bn = i // BATCH + 1
    try:
        cost = client.metadata.get_cost(
            dataset=DATASET, symbols=batch, stype_in="raw_symbol",
            schema=SCHEMA, start=BACKTEST_START, end=BACKTEST_END,
        )
        total += cost
        print(f"  batch {bn:>3}/{n_batches}: {len(batch)} symbols -> ${cost:,.4f}")
    except Exception as exc:
        print(f"  batch {bn}: ERROR {exc}")

print()
print("=" * 65)
print(f"  ESTIMATED COST : ${total:,.2f} USD")
print(f"  vs current pull: $18 baseline (~{total/18:.1f}x)")
print("=" * 65)

# ---- Save symbol list (so 02_pull_data.py can consume it) -------------------
out = ROOT / "data" / "symbol_list_wide.csv"
pd.Series(symbols, name="symbol").to_csv(out, index=False)
print(f"\nWrote {len(symbols):,} symbols -> {out}")
print("To pull: run pipeline/02b_pull_data_wide.py after reviewing the cost above.")
