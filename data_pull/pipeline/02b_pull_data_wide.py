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
