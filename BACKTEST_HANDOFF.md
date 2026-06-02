# Calendar Straddle Backtest — Sensitivity Findings & Wider Data Pull

**Prepared:** 2026-06-01  
**Project:** `g:\Finance Derivatives`  
**Strategy:** 25-stock earnings calendar straddle. Sell near-term ATM straddle for the earnings event, buy far-term ATM straddle held into the next earnings cycle.

---

## 1. Current data inventory

| File | Coverage |
|---|---|
| `data/options_daily.parquet` | 25 tickers, 2016-01-04 → 2026-04-30, **3,506 contracts**, 307K EOD bid/ask rows |
| `data/equity_prices.parquet` | Daily closes for the same 25 tickers, split-adjusted to actual traded prices |
| `data/trade_schedule.csv` | **971 earnings cycles** with the 4 OSI symbols per cycle |
| `data/tbill_rate.csv` | 3-month T-bill from FRED (for Greeks) |

**What's pulled per cycle today:** only **4 contracts** — ATM call + put at `short_exp` (first weekly after earnings) and ATM call + put at `long_exp` (first monthly after next earnings). The strike is set from the spot **7 calendar days before earnings** (`ENTRY_DAYS_BEFORE = 7` in `pipeline/config.py`).

Cost of the original pull: ~$18 from Databento.

---

## 2. Sensitivity sweep (already run)

Script: `strategy/_sensitivity_grid.py`  
Outputs: `results/sensitivity_grid.csv`, `results/sensitivity_grid.png`

**Sweep:** 15 × 15 grid of (entry day, long-exit day) using bid/ask fills, short held to expiry at intrinsic.

- `N_entry` = trading days before `earn_dt` (1–15, ≈ 3 weeks)
- `M_exit` = trading days before `next_earn` (1–15, ≈ 3 weeks)

**Top cells:**

| Optimum | N_entry | M_exit | Trades | Cum P&L | Win rate | Avg return on net premium |
|---|---|---|---|---|---|---|
| Best cumulative P&L | **14** | **7** | 451 | $155,962 | 45.5% | 15.4% |
| Best avg return | **14** | **2** | 448 | $152,964 | 46.9% | **18.0%** |
| Best win rate | **15** | **13** | 448 | $104,863 | 49.3% | 13.8% |

**Important caveat — boundary clipping.** All three optima sit on the **far edge** of the entry window (N = 14–15). Returns are still improving as we move entry earlier — the "true" optimum may lie beyond 3 weeks. Also: the current data only contains the **one** strike that was ATM 7 calendar days before earnings. When entry is shifted to ~3 weeks before, spot has drifted and that strike is no longer ATM. The sweep results are therefore *suggestive*, not definitive, until we have ATM contracts across the wider window.

---

## 3. Proposed next step — pull a wider strike band

To validate the sensitivity finding and unlock further timing/strike experiments, expand the Databento pull so that for each earnings cycle we have a band of strikes covering the spot range across:

- ±3 weeks around `earn_dt` (entry timing window and short-exit timing)
- ±3 weeks around `next_earn` (long-exit timing window)

Same two expiries as today (`short_exp`, `long_exp`) — only strikes are being widened.

Two configurable knobs:

| Knob | Default | Meaning |
|---|---|---|
| `K_STRIKES` | 5 | Minimum ±5 strikes around each cycle's original ATM |
| `WINDOW_TD` | 15 TDs (≈ 3 weeks) | Additional strikes covering the actual spot high/low over ±15 TDs around `earn_dt` AND `next_earn` |

The cost estimator is free to run (Databento's `metadata.get_cost` is a metadata call). Run it first, review the bill, then trigger the actual pull.

---

## 4. Pipeline location & run order

Everything is in `pipeline/`. The new wider pull is **additive** — it does not touch the existing `options_daily.parquet`.

| Step | Script | Output | Charges? |
|---|---|---|---|
| 1 (existing — already done) | `pipeline/01_cost_estimate.py` | `data/symbol_list.csv`, `data/trade_schedule.csv` | No |
| 2 (existing — already done) | `pipeline/02_pull_data.py` | `data/options_daily.parquet` | Yes (~$18, already paid) |
| **1b (new)** | **`pipeline/01b_cost_estimate_wide.py`** | `data/symbol_list_wide.csv` + printed cost | **No** |
| **2b (new)** | **`pipeline/02b_pull_data_wide.py`** | `data/options_daily_wide.parquet` | **Yes — review 1b's estimate first** |

```bash
# from the project root, with the venv activated:

# 1b. Free cost preview
./venv/Scripts/python.exe pipeline/01b_cost_estimate_wide.py

# 2b. Only run if the printed cost is acceptable
./venv/Scripts/python.exe pipeline/02b_pull_data_wide.py
```

---

## 5. The two new scripts (full source)

### 5.1 `pipeline/01b_cost_estimate_wide.py`

```python
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
K_STRIKES : minimum strikes to each side of original ATM (per cycle).
            Total anchor strikes per cycle = 2*K + 1.
WINDOW_TD : additional strikes to cover actual spot range in a window of
            +/- WINDOW_TD trading days around each earnings date (~15 TDs ~ 3 weeks).

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

# ---- Save symbol list (so 02b_pull_data_wide.py can consume it) ------------
out = ROOT / "data" / "symbol_list_wide.csv"
pd.Series(symbols, name="symbol").to_csv(out, index=False)
print(f"\nWrote {len(symbols):,} symbols -> {out}")
print("To pull: run pipeline/02b_pull_data_wide.py after reviewing the cost above.")
```

### 5.2 `pipeline/02b_pull_data_wide.py`

```python
"""
Step 2b -- Pull options data for the WIDER symbol set
=====================================================
Reads data/symbol_list_wide.csv (produced by 01b_cost_estimate_wide.py) and
pulls cbbo-1m from Databento, reducing to one EOD bid/ask/mid row per
(symbol, date).

IMPORTANT
---------
Run 01b_cost_estimate_wide.py first and review the cost. This script spends
real money against your Databento account.

Output
------
  data/options_daily_wide.parquet   (does NOT overwrite options_daily.parquet)
    columns: symbol, date, bid, ask, mid
"""
import sys
from pathlib import Path
import pandas as pd
import databento as db

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(Path(__file__).parent))
from config import (
    DATABENTO_KEY, BACKTEST_START, BACKTEST_END,
    DATASET, SCHEMA, DATA_DIR, EOD_UTC_HOUR,
)

DATA_PATH    = ROOT / DATA_DIR
SYMBOL_FILE  = DATA_PATH / "symbol_list_wide.csv"
OUT_FILE     = DATA_PATH / "options_daily_wide.parquet"
BATCH_SIZE   = 1000


def load_symbols() -> list[str]:
    if not SYMBOL_FILE.exists():
        raise FileNotFoundError(
            f"{SYMBOL_FILE.name} not found. Run pipeline/01b_cost_estimate_wide.py first."
        )
    return pd.read_csv(SYMBOL_FILE)["symbol"].tolist()


def pull_in_batches(client, symbols, start, end, batch_size=BATCH_SIZE):
    frames = []
    n_batches = (len(symbols) + batch_size - 1) // batch_size
    for i, start_idx in enumerate(range(0, len(symbols), batch_size), 1):
        batch = symbols[start_idx:start_idx + batch_size]
        print(f"  [{i:>3}/{n_batches}] {len(batch)} symbols ...", end=" ", flush=True)
        try:
            store = client.timeseries.get_range(
                dataset=DATASET, symbols=batch, stype_in="raw_symbol",
                schema=SCHEMA, start=start, end=end,
            )
            df = store.to_df(pretty_ts=False, map_symbols=True)
            if df.empty:
                print("0 records")
                continue
            print(f"{len(df):,} raw records")
            frames.append(df)
        except Exception as exc:
            print(f"ERROR: {exc}")

    if not frames:
        return pd.DataFrame()

    combined = pd.concat(frames).reset_index()
    combined["ts_recv"] = pd.to_datetime(combined["ts_recv"], utc=True)
    combined["date"]    = combined["ts_recv"].dt.date
    combined["hour"]    = combined["ts_recv"].dt.hour

    eod = combined[combined["hour"] >= EOD_UTC_HOUR].copy()
    if eod.empty:
        eod = combined.copy()

    eod = (
        eod.sort_values("ts_recv")
        .groupby(["symbol", "date"])
        .last()
        .reset_index()
    )
    eod["bid"] = eod["bid_px_00"].astype(float)
    eod["ask"] = eod["ask_px_00"].astype(float)
    eod["mid"] = (eod["bid"] + eod["ask"]) / 2
    eod = eod[(eod["bid"] > 0) & (eod["ask"] > 0)].copy()
    return eod[["symbol", "date", "bid", "ask", "mid"]].sort_values(
        ["symbol", "date"]
    ).reset_index(drop=True)


def main():
    auto_yes = "--yes" in sys.argv or "-y" in sys.argv
    DATA_PATH.mkdir(exist_ok=True)

    print("=" * 65)
    print("  Wider-strike Databento Pull  (3-week window around earnings)")
    print("=" * 65)

    symbols = load_symbols()
    print(f"\nLoaded {len(symbols):,} option symbols from {SYMBOL_FILE.name}")
    print(f"Dataset : {DATASET}   Schema : {SCHEMA}")
    print(f"Period  : {BACKTEST_START} -> {BACKTEST_END}")

    if OUT_FILE.exists() and not auto_yes:
        print(f"\nWARNING: {OUT_FILE.name} already exists.")
        if input("Overwrite? [y/N] ").strip().lower() != "y":
            print("Aborted.")
            return

    if not auto_yes:
        msg = ("\nThis WILL charge your Databento account. Did you review the "
               "cost from 01b_cost_estimate_wide.py? Proceed? [y/N] ")
        if input(msg).strip().lower() != "y":
            print("Aborted.")
            return
    else:
        print("\nRunning with --yes, skipping confirmation prompt.")

    client = db.Historical(key=DATABENTO_KEY)
    print("\nPulling data in batches...")
    opts = pull_in_batches(client, symbols, BACKTEST_START, BACKTEST_END)

    if opts.empty:
        print("\nNo data returned. Check symbol format and dataset availability.")
        return

    opts.to_parquet(OUT_FILE, index=False)
    size_mb = OUT_FILE.stat().st_size / 1e6
    print(f"\nSaved {len(opts):,} EOD rows -> {OUT_FILE}  ({size_mb:.1f} MB)")
    print(f"Unique symbols with data : {opts['symbol'].nunique():,}")
    print(f"Date range in data       : {opts['date'].min()} -> {opts['date'].max()}")
    print("\nWider data is now available at data/options_daily_wide.parquet.")
    print("Original data/options_daily.parquet is untouched.")


if __name__ == "__main__":
    main()
```

---

## 6. Dependencies

Both scripts rely on existing files already in the repo:

- `pipeline/config.py` — `DATABENTO_KEY`, `BACKTEST_START`, `BACKTEST_END`, `DATASET`, `SCHEMA`, `EOD_UTC_HOUR`
- `pipeline/options_utils.py` — `atm_strike`, `osi_symbol`
- `data/trade_schedule.csv`, `data/equity_prices.parquet` — already generated by step 1

Python packages: `pandas`, `numpy`, `databento` (all in `requirements.txt`).

Environment variable: `DATABENTO_API_KEY` must be set.
