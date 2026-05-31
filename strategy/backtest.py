"""
Backtest engine for the calendar straddle earnings strategy.

Per trade:
  - SELL near-term ATM straddle (short_call + short_put) at entry_dt mid
  - BUY  far-term ATM straddle  (long_call + long_put) on the first trading day
    >= entry_dt where both legs have an active quote (far-term contracts are often
    listed but not yet quoted at entry_dt; we wait for the market to form)
  - Close near-term straddle: first trading day after earn_dt with a quote
    (forward-scans up to short_exp)
  - Close far-term straddle:  one trading day before next_earn
    (backward-scans up to 3 days if that exact date has no quote)

Outputs results/trades.csv.
"""

import pandas as pd
import numpy as np
from pathlib import Path

# ---------------------------------------------------------------------------
# Continuous dividend yield per stock (annualised, decimal)
# ---------------------------------------------------------------------------
DIV_YIELD = {
    "AAPL": 0.0055, "ABNB": 0.0000, "ACM":  0.0070, "ADBE": 0.0000,
    "AMAT": 0.0070, "AMD":  0.0000, "AMGN": 0.0300, "AMZN": 0.0000,
    "ASML": 0.0080, "AVGO": 0.0180, "BABA": 0.0000, "CSCO": 0.0280,
    "GOOGL":0.0000, "INTC": 0.0320, "META": 0.0000, "MSFT": 0.0085,
    "MU":   0.0040, "NFLX": 0.0000, "NVDA": 0.0015, "ORCL": 0.0120,
    "PDD":  0.0000, "PLTR": 0.0000, "QCOM": 0.0250, "TSLA": 0.0000,
    "ZM":   0.0000,
}

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------
ROOT = Path(__file__).parent.parent

sched  = pd.read_csv(ROOT / "data" / "trade_schedule.csv", parse_dates=[
    "earn_dt", "next_earn", "entry_dt", "short_exp", "long_exp"])

opts   = pd.read_parquet(ROOT / "data" / "options_daily.parquet")
opts["date"] = pd.to_datetime(opts["date"])

equity = pd.read_parquet(ROOT / "data" / "equity_prices.parquet")
equity["date"] = pd.to_datetime(equity["date"])

tbill  = pd.read_csv(ROOT / "data" / "tbill_rate.csv",
                     parse_dates=["observation_date"])
tbill  = tbill.rename(columns={"observation_date": "date", "DTB3": "rate"})
tbill["rate"] = tbill["rate"] / 100          # percent -> decimal
tbill  = tbill.set_index("date")["rate"]
tbill  = tbill.reindex(pd.date_range(tbill.index.min(), tbill.index.max(), freq="D"))
tbill  = tbill.ffill()                       # fill weekends / holidays

# ---------------------------------------------------------------------------
# Build look-up structures
# ---------------------------------------------------------------------------
# Option mid prices: (symbol, date) -> mid
opts_idx = opts.set_index(["symbol", "date"])["mid"]

# Equity price lookup (for intrinsic settlement at expiry)
equity_idx = equity.set_index("date")

# Ordered set of trading days (from equity price dates)
trading_days = sorted(equity["date"].unique())
td_set       = set(trading_days)

def next_trading_day(dt):
    """First trading day strictly after dt."""
    for d in trading_days:
        if d > dt:
            return d
    return None

def prev_trading_day(dt):
    """Last trading day strictly before dt."""
    prev = None
    for d in trading_days:
        if d >= dt:
            return prev
        prev = d
    return prev

def get_mid(symbol, date):
    """Mid price for a symbol on a date. Returns NaN if missing."""
    try:
        return opts_idx.loc[(symbol, date)]
    except KeyError:
        return np.nan

MIN_OPTION_PRICE = 0.01   # floor for expired / deep-OTM legs

def first_quoted_date(sym_a, sym_b, from_dt, to_dt):
    """
    First trading day in [from_dt, to_dt] where both symbols have a quote.
    Returns (date, mid_a, mid_b) or (None, nan, nan).
    """
    for d in trading_days:
        if d < from_dt:
            continue
        if d > to_dt:
            break
        ma = get_mid(sym_a, d)
        mb = get_mid(sym_b, d)
        if not np.isnan(ma) and not np.isnan(mb):
            return d, ma, mb
    return None, np.nan, np.nan

def first_quoted_single(sym, from_dt, to_dt):
    """
    First trading day in [from_dt, to_dt] where sym has a quote.
    Returns (date, mid) or (None, nan).
    """
    for d in trading_days:
        if d < from_dt:
            continue
        if d > to_dt:
            break
        m = get_mid(sym, d)
        if not np.isnan(m):
            return d, m
    return None, np.nan

def short_exit_prices(sym_a, sym_b, from_dt, expiry_dt):
    """
    Close each short leg independently on the first date it has a quote after
    from_dt. If a leg has no quote before expiry, it expired worthless -> MIN_OPTION_PRICE.
    Returns (exit_dt, mid_a, mid_b) using the later of the two individual exit dates.
    """
    da, ma = first_quoted_single(sym_a, from_dt, expiry_dt)
    db, mb = first_quoted_single(sym_b, from_dt, expiry_dt)
    # Fall back to minimum (expired worthless) when no quote found
    if da is None:
        ma = MIN_OPTION_PRICE
        da = from_dt
    if db is None:
        mb = MIN_OPTION_PRICE
        db = from_dt
    # Use the later date as the representative exit date (both legs closed by then)
    exit_dt = max(da, db)
    return exit_dt, ma, mb

def last_quoted_exit(sym_a, sym_b, target_dt, max_back=3):
    """
    Most recent trading day <= target_dt (back up to max_back days) where both
    symbols have a quote. Used for far-term exit backward-scan.
    """
    candidates = [d for d in trading_days if d <= target_dt]
    for d in reversed(candidates[-(max_back + 1):]):
        ma = get_mid(sym_a, d)
        mb = get_mid(sym_b, d)
        if not np.isnan(ma) and not np.isnan(mb):
            return d, ma, mb
    return None, np.nan, np.nan

def get_spot_at(ticker, date):
    """Equity close on date, or the last available close before date."""
    if ticker not in equity_idx.columns:
        return np.nan
    col   = equity_idx[ticker].dropna()
    valid = col[col.index <= date]
    return float(valid.iloc[-1]) if not valid.empty else np.nan

def get_rate(date):
    """3-month T-bill rate on date (decimal). Forward-fills."""
    try:
        return tbill.loc[date]
    except KeyError:
        return tbill.asof(date)

# ---------------------------------------------------------------------------
# Run trades
# ---------------------------------------------------------------------------
records = []
skipped = 0

for _, row in sched.iterrows():
    ticker    = row["ticker"]
    entry_dt  = row["entry_dt"]
    earn_dt   = row["earn_dt"]
    next_earn = row["next_earn"]

    sc = row["short_call"].strip()
    sp = row["short_put"].strip()
    lc = row["long_call"].strip()
    lp = row["long_put"].strip()

    # --- Short leg entry: first date both legs are quoted in [entry_dt, earn_dt) ---
    short_entry_dt, sc_entry, sp_entry = first_quoted_date(sc, sp, entry_dt, earn_dt - pd.Timedelta(days=1))
    if short_entry_dt is None:
        skipped += 1
        continue

    # --- Long leg entry: first quoted date on or after entry_dt, up to long_exit_dt ---
    # Far-term contracts often start trading weeks after the intended entry date.
    # We wait for the first active quote, up to the long exit date.
    target_long_exit = prev_trading_day(next_earn)
    if target_long_exit is None:
        skipped += 1
        continue
    long_entry_dt, lc_entry, lp_entry = first_quoted_date(lc, lp, entry_dt, target_long_exit)
    if long_entry_dt is None:
        skipped += 1
        continue

    # --- Near-term exit: held to expiry, settled at intrinsic value ---
    strike        = float(row["strike"])
    short_exp_dt  = row["short_exp"]
    spot_at_exp   = get_spot_at(ticker, short_exp_dt)
    if np.isnan(spot_at_exp):
        skipped += 1
        continue
    sc_exit       = max(spot_at_exp - strike, 0.0)   # call intrinsic
    sp_exit       = max(strike - spot_at_exp, 0.0)   # put intrinsic
    short_exit_dt = short_exp_dt

    # --- Far-term exit: last quoted date on or before (next_earn - 1 trading day) ---
    long_exit_dt, lc_exit, lp_exit = last_quoted_exit(lc, lp, target_long_exit, max_back=5)
    if long_exit_dt is None:
        skipped += 1
        continue

    # --- P&L (per contract = 100 shares) ---
    # Short straddle: sold at entry, bought back at exit
    short_credit = (sc_entry + sp_entry) * 100
    short_debit  = (sc_exit  + sp_exit)  * 100
    short_pnl    = short_credit - short_debit

    # Long straddle: bought at entry, sold at exit
    long_debit   = (lc_entry + lp_entry) * 100
    long_credit  = (lc_exit  + lp_exit)  * 100
    long_pnl     = long_credit - long_debit

    net_premium     = long_debit - short_credit   # positive = net spend
    total_pnl       = short_pnl + long_pnl
    abs_net_premium = abs(net_premium)
    return_pct      = (total_pnl / abs_net_premium * 100) if abs_net_premium > 0 else np.nan

    records.append({
        "ticker":          ticker,
        "earn_dt":         earn_dt.date(),
        "short_entry_dt":  short_entry_dt.date(),
        "long_entry_dt":   long_entry_dt.date(),
        "short_exit_dt":   short_exit_dt.date() if hasattr(short_exit_dt, 'date') else short_exit_dt,
        "long_exit_dt":    long_exit_dt.date(),
        # entry prices
        "sc_entry": sc_entry, "sp_entry": sp_entry,
        "lc_entry": lc_entry, "lp_entry": lp_entry,
        # exit prices
        "sc_exit":  sc_exit,  "sp_exit":  sp_exit,
        "lc_exit":  lc_exit,  "lp_exit":  lp_exit,
        # P&L breakdown
        "short_credit":  short_credit,
        "short_debit":   short_debit,
        "short_pnl":     short_pnl,
        "long_debit":    long_debit,
        "long_credit":   long_credit,
        "long_pnl":      long_pnl,
        "net_premium":   net_premium,
        "total_pnl":     total_pnl,
        "return_pct":    return_pct,
    })

trades = pd.DataFrame(records)
trades.to_csv(ROOT / "results" / "trades.csv", index=False)

# ---------------------------------------------------------------------------
# Quick summary
# ---------------------------------------------------------------------------
n        = len(trades)
n_win    = (trades["total_pnl"] > 0).sum()
avg_pnl  = trades["total_pnl"].mean()
avg_ret  = trades["return_pct"].mean()
cum_pnl  = trades["total_pnl"].sum()

print(f"Trades executed : {n}  (skipped {skipped})")
print(f"Win rate        : {n_win/n*100:.1f}%  ({n_win}/{n})")
print(f"Avg P&L/trade   : ${avg_pnl:,.2f}")
print(f"Avg return      : {avg_ret:.1f}%")
print(f"Cumulative P&L  : ${cum_pnl:,.2f}")
print("\nSaved -> results/trades.csv")
