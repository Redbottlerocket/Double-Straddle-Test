"""
Backtest variant that reads from data/options_close.parquet (cbbo-1h closing
snapshots) instead of data/options_daily.parquet (cbbo-1m EOD).

For tickers present in options_close.parquet, uses the cleaner close data.
For tickers NOT present (i.e. those we haven't re-pulled yet), falls back
to the original options_daily.parquet so the backtest still runs end-to-end.

Outputs results/trades_close.csv -- compare this against results/trades.csv
to see the P&L impact of fixing the stale quote issue.
"""

import pandas as pd
import numpy as np
from pathlib import Path

DIV_YIELD = {
    "AAPL": 0.0055, "ABNB": 0.0000, "ACM":  0.0070, "ADBE": 0.0000,
    "AMAT": 0.0070, "AMD":  0.0000, "AMGN": 0.0300, "AMZN": 0.0000,
    "ASML": 0.0080, "AVGO": 0.0180, "BABA": 0.0000, "CSCO": 0.0280,
    "GOOGL":0.0000, "INTC": 0.0320, "META": 0.0000, "MSFT": 0.0085,
    "MU":   0.0040, "NFLX": 0.0000, "NVDA": 0.0015, "ORCL": 0.0120,
    "PDD":  0.0000, "PLTR": 0.0000, "QCOM": 0.0250, "TSLA": 0.0000,
    "ZM":   0.0000,
}

ROOT = Path(__file__).parent.parent

sched  = pd.read_csv(ROOT / "data" / "trade_schedule.csv", parse_dates=[
    "earn_dt", "next_earn", "entry_dt", "short_exp", "long_exp"])

# Load both data sources; close-file takes precedence for tickers it covers
old = pd.read_parquet(ROOT / "data" / "options_daily.parquet")
old["date"] = pd.to_datetime(old["date"])

close_file = ROOT / "data" / "options_close.parquet"
if close_file.exists():
    new = pd.read_parquet(close_file)
    new["date"] = pd.to_datetime(new["date"])
    new_tickers = {s.strip()[:6].strip() for s in new["symbol"]}
    prefixes = tuple(f"{t:<6}" for t in new_tickers)
    old_remaining = old[~old["symbol"].str.startswith(prefixes)]
    opts = pd.concat([old_remaining, new], ignore_index=True)
    print(f"Using NEW close data for: {sorted(new_tickers)}")
    print(f"Falling back to OLD data for everyone else.")
else:
    opts = old
    print("No options_close.parquet found, using OLD data only.")
print()

equity = pd.read_parquet(ROOT / "data" / "equity_prices.parquet")
equity["date"] = pd.to_datetime(equity["date"])

tbill  = pd.read_csv(ROOT / "data" / "tbill_rate.csv", parse_dates=["observation_date"])
tbill  = tbill.rename(columns={"observation_date": "date", "DTB3": "rate"})
tbill["rate"] = tbill["rate"] / 100
tbill  = tbill.set_index("date")["rate"]
tbill  = tbill.reindex(pd.date_range(tbill.index.min(), tbill.index.max(), freq="D")).ffill()

opts_idx = opts.set_index(["symbol", "date"])[["bid", "ask", "mid"]]
equity_idx = equity.set_index("date")
trading_days = sorted(equity["date"].unique())

def next_trading_day(dt):
    for d in trading_days:
        if d > dt: return d
    return None

def prev_trading_day(dt):
    prev = None
    for d in trading_days:
        if d >= dt: return prev
        prev = d
    return prev

def get_price(symbol, date, side="mid"):
    try:
        return opts_idx.loc[(symbol, date), side]
    except KeyError:
        return np.nan

def first_quoted_date(sym_a, sym_b, from_dt, to_dt, side="mid"):
    for d in trading_days:
        if d < from_dt: continue
        if d > to_dt: break
        ma = get_price(sym_a, d, side)
        mb = get_price(sym_b, d, side)
        if not np.isnan(ma) and not np.isnan(mb):
            return d, ma, mb
    return None, np.nan, np.nan

def last_quoted_exit(sym_a, sym_b, target_dt, max_back=5, side="mid"):
    candidates = [d for d in trading_days if d <= target_dt]
    for d in reversed(candidates[-(max_back + 1):]):
        ma = get_price(sym_a, d, side)
        mb = get_price(sym_b, d, side)
        if not np.isnan(ma) and not np.isnan(mb):
            return d, ma, mb
    return None, np.nan, np.nan

def get_spot_at(ticker, date):
    if ticker not in equity_idx.columns: return np.nan
    col = equity_idx[ticker].dropna()
    valid = col[col.index <= date]
    return float(valid.iloc[-1]) if not valid.empty else np.nan

records = []
skipped = 0

for _, row in sched.iterrows():
    ticker, entry_dt, earn_dt, next_earn = row["ticker"], row["entry_dt"], row["earn_dt"], row["next_earn"]
    sc, sp, lc, lp = row["short_call"].strip(), row["short_put"].strip(), row["long_call"].strip(), row["long_put"].strip()

    short_entry_dt, sc_entry, sp_entry = first_quoted_date(sc, sp, entry_dt, earn_dt - pd.Timedelta(days=1), side="bid")
    if short_entry_dt is None: skipped += 1; continue

    target_long_exit = prev_trading_day(next_earn)
    if target_long_exit is None: skipped += 1; continue
    long_entry_dt, lc_entry, lp_entry = first_quoted_date(lc, lp, entry_dt, target_long_exit, side="ask")
    if long_entry_dt is None: skipped += 1; continue

    strike, short_exp_dt = float(row["strike"]), row["short_exp"]
    spot_at_exp = get_spot_at(ticker, short_exp_dt)
    if np.isnan(spot_at_exp): skipped += 1; continue
    sc_exit = max(spot_at_exp - strike, 0.0)
    sp_exit = max(strike - spot_at_exp, 0.0)
    short_exit_dt = short_exp_dt

    long_exit_dt, lc_exit, lp_exit = last_quoted_exit(lc, lp, target_long_exit, max_back=5, side="bid")
    if long_exit_dt is None: skipped += 1; continue

    short_credit = (sc_entry + sp_entry) * 100
    short_debit  = (sc_exit  + sp_exit)  * 100
    short_pnl    = short_credit - short_debit
    long_debit   = (lc_entry + lp_entry) * 100
    long_credit  = (lc_exit  + lp_exit)  * 100
    long_pnl     = long_credit - long_debit
    net_premium  = long_debit - short_credit
    total_pnl    = short_pnl + long_pnl
    return_pct   = (total_pnl / abs(net_premium) * 100) if abs(net_premium) > 0 else np.nan

    records.append({
        "ticker": ticker, "earn_dt": earn_dt.date(),
        "short_entry_dt": short_entry_dt.date(), "long_entry_dt": long_entry_dt.date(),
        "short_exit_dt": short_exit_dt.date() if hasattr(short_exit_dt, 'date') else short_exit_dt,
        "long_exit_dt": long_exit_dt.date(),
        "sc_entry": sc_entry, "sp_entry": sp_entry, "lc_entry": lc_entry, "lp_entry": lp_entry,
        "sc_exit": sc_exit, "sp_exit": sp_exit, "lc_exit": lc_exit, "lp_exit": lp_exit,
        "short_credit": short_credit, "short_debit": short_debit, "short_pnl": short_pnl,
        "long_debit": long_debit, "long_credit": long_credit, "long_pnl": long_pnl,
        "net_premium": net_premium, "total_pnl": total_pnl, "return_pct": return_pct,
    })

trades = pd.DataFrame(records)
trades.to_csv(ROOT / "results" / "trades_close.csv", index=False)

n = len(trades)
print(f"Trades executed : {n}  (skipped {skipped})")
print(f"Win rate        : {(trades['total_pnl']>0).mean()*100:.1f}%")
print(f"Cumulative P&L  : ${trades['total_pnl'].sum():,.2f}")
print()

# Compare against the existing trades.csv
existing = pd.read_csv(ROOT / "results" / "trades.csv")
if "earn_dt" in existing.columns and len(trades) > 0:
    new_tickers_in_trades = trades.merge(
        sched[["ticker", "earn_dt"]], on=["ticker", "earn_dt"], how="left"
    )
    if close_file.exists():
        new_pulled = {s.strip()[:6].strip() for s in new["symbol"]}
        sub_new = trades[trades["ticker"].isin(new_pulled)]
        sub_old = existing[existing["ticker"].isin(new_pulled)]
        print(f"=== TICKERS WITH NEW CLOSE DATA: {sorted(new_pulled)} ===")
        print(f"  Old (cbbo-1m EOD) cum P&L for these tickers: ${sub_old['total_pnl'].sum():,.0f}")
        print(f"  New (cbbo-1h close) cum P&L for these tickers: ${sub_new['total_pnl'].sum():,.0f}")
        print(f"  Difference: ${sub_new['total_pnl'].sum() - sub_old['total_pnl'].sum():,.0f}")

print("\nSaved -> results/trades_close.csv")
