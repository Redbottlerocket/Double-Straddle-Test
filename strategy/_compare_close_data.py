"""
Compare the new cbbo-1h closing snapshots (data/options_close.parquet) against
the original cbbo-1m EOD pull (data/options_daily.parquet) for the same symbols.

Use after running `pipeline/03_pull_data_close.py --tickers AAPL` to see whether
the stale quote issue was material for AAPL.
"""
import pandas as pd
import numpy as np
from pathlib import Path

ROOT = Path(__file__).parent.parent

old = pd.read_parquet(ROOT / "data" / "options_daily.parquet")
old["date"] = pd.to_datetime(old["date"])
new_path = ROOT / "data" / "options_close.parquet"
if not new_path.exists():
    print(f"ERROR: {new_path.relative_to(ROOT)} not found.")
    print("Run: python pipeline/03_pull_data_close.py --tickers AAPL")
    raise SystemExit(1)
new = pd.read_parquet(new_path)
new["date"] = pd.to_datetime(new["date"])

# Limit comparison to tickers present in both
new_tickers = sorted({s.strip()[:6].strip() for s in new["symbol"]})
print(f"Tickers in new close file: {new_tickers}")
print()

prefixes = tuple(f"{t:<6}" for t in new_tickers)
old_sub = old[old["symbol"].str.startswith(prefixes)].copy()

# Join on (symbol, date)
merged = old_sub.merge(new, on=["symbol", "date"], how="inner",
                      suffixes=("_old", "_new"))

print(f"Matched rows for comparison: {len(merged):,}")
print()

merged["bid_diff"]  = merged["bid_new"] - merged["bid_old"]
merged["ask_diff"]  = merged["ask_new"] - merged["ask_old"]
merged["mid_diff"]  = merged["mid_new"] - merged["mid_old"]
merged["mid_pct"]   = (merged["mid_diff"] / merged["mid_old"].replace(0, np.nan)) * 100
merged["spread_old"] = merged["ask_old"] - merged["bid_old"]
merged["spread_new"] = merged["ask_new"] - merged["bid_new"]

print("=== AGGREGATE DIFFERENCES (new close - old EOD) ===")
print(f"  Mid:  mean ${merged['mid_diff'].mean():+.3f}  median ${merged['mid_diff'].median():+.3f}  "
      f"std ${merged['mid_diff'].std():.3f}")
print(f"  Bid:  mean ${merged['bid_diff'].mean():+.3f}  median ${merged['bid_diff'].median():+.3f}")
print(f"  Ask:  mean ${merged['ask_diff'].mean():+.3f}  median ${merged['ask_diff'].median():+.3f}")
print()
print(f"  % of rows where |mid_diff| > 5% of old mid : "
      f"{(merged['mid_pct'].abs() > 5).mean()*100:.1f}%")
print(f"  % of rows where |mid_diff| > 25% of old mid: "
      f"{(merged['mid_pct'].abs() > 25).mean()*100:.1f}%")
print(f"  Old avg spread : ${merged['spread_old'].mean():.3f}")
print(f"  New avg spread : ${merged['spread_new'].mean():.3f}")
print()

# Largest discrepancies
print("=== TOP 10 LARGEST PRICE DIFFERENCES (|mid_diff| highest) ===")
worst = merged.reindex(merged["mid_diff"].abs().sort_values(ascending=False).index).head(10)
for _, r in worst.iterrows():
    print(f"  {r['symbol'].strip():25s} {r['date'].date()}  "
          f"old mid ${r['mid_old']:7.2f}  ->  new mid ${r['mid_new']:7.2f}  "
          f"({r['mid_pct']:+6.1f}%)")

print()
print("=== INTERPRETATION ===")
mean_abs_pct = merged["mid_pct"].abs().mean()
if mean_abs_pct < 2:
    print(f"  Avg |% diff| = {mean_abs_pct:.2f}% -- old data was mostly fine for these tickers.")
    print(f"  Re-pulling the rest of the universe probably won't materially change P&L.")
elif mean_abs_pct < 10:
    print(f"  Avg |% diff| = {mean_abs_pct:.2f}% -- moderate stale-quote effect.")
    print(f"  Re-pulling the rest is probably worth the small cost.")
else:
    print(f"  Avg |% diff| = {mean_abs_pct:.2f}% -- significant stale-quote effect.")
    print(f"  Definitely re-pull the rest of the universe.")
