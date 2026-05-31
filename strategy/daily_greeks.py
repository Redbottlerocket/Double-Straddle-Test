"""
Compute daily IV and Greeks for all 4 legs of every executed trade.

For each trade in results/trades.csv, for each calendar day the position
is open, for each leg (sc, sp, lc, lp):
  - look up mid price (forward-fill if missing)
  - solve Black-Scholes IV from mid
  - compute delta, gamma, vega, theta, rho

Position sign convention (for net portfolio Greeks):
  sc / sp : SHORT  (-1)
  lc / lp : LONG   (+1)

Outputs results/daily_greeks.parquet.
"""

import sys
import pandas as pd
import numpy as np
from pathlib import Path

ROOT = Path(__file__).parent.parent

sys.path.insert(0, str(Path(__file__).parent))
from greeks import implied_vol, greeks as bs_greeks

# ---------------------------------------------------------------------------
# Dividend yields (same table as backtest.py)
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
trades = pd.read_csv(ROOT / "results" / "trades.csv", parse_dates=[
    "earn_dt", "short_entry_dt", "long_entry_dt",
    "short_exit_dt", "long_exit_dt"])

opts   = pd.read_parquet(ROOT / "data" / "options_daily.parquet")
opts["date"] = pd.to_datetime(opts["date"])

equity = pd.read_parquet(ROOT / "data" / "equity_prices.parquet")
equity["date"] = pd.to_datetime(equity["date"])
equity = equity.set_index("date")

tbill  = pd.read_csv(ROOT / "data" / "tbill_rate.csv",
                     parse_dates=["observation_date"])
tbill  = tbill.rename(columns={"observation_date": "date", "DTB3": "rate"})
tbill["rate"] = tbill["rate"] / 100
tbill  = tbill.set_index("date")["rate"]
tbill  = tbill.reindex(pd.date_range(tbill.index.min(), tbill.index.max(), freq="D"))
tbill  = tbill.ffill()

trading_days = sorted(equity.index.unique())

# Forward-fill option mid prices within each symbol's date range
opts_ffill = (
    opts.sort_values(["symbol", "date"])
    .set_index(["symbol", "date"])["mid"]
)

def get_mid_ffill(symbol, date):
    """Mid price on date; forward-fills from last available quote."""
    try:
        sym_data = opts_ffill.loc[symbol]
    except KeyError:
        return np.nan
    try:
        return sym_data.loc[date]
    except KeyError:
        prior = sym_data[sym_data.index <= date]
        return prior.iloc[-1] if len(prior) else np.nan

def get_spot(ticker, date):
    try:
        return equity.loc[date, ticker]
    except KeyError:
        return np.nan

def get_rate(date):
    try:
        return tbill.loc[date]
    except KeyError:
        return tbill.asof(date)

def parse_option_type(symbol):
    """Extract 'call' or 'put' from OSI symbol (e.g. AAPL  160129C00095000)."""
    s = symbol.strip()
    # OSI format: 6-char ticker (padded) + 6-digit date + C/P + 8-digit strike
    # Find the C or P after the date portion
    for ch in reversed(s):
        if ch == 'C':
            return 'call'
        if ch == 'P':
            return 'put'
    return 'call'

def parse_strike(symbol):
    """Extract strike price from OSI symbol (last 8 digits / 1000)."""
    s = symbol.strip()
    return float(s[-8:]) / 1000.0

def parse_expiry(symbol):
    """Extract expiry date from OSI symbol (YYMMDD in positions 6-11)."""
    s = symbol.strip()
    # Find the date portion: 6 digits before the C/P character
    # Reverse search for C or P
    for i in range(len(s) - 1, -1, -1):
        if s[i] in ('C', 'P'):
            date_str = s[i-6:i]
            return pd.Timestamp("20" + date_str[:2] + "-" + date_str[2:4] + "-" + date_str[4:6])
    return pd.NaT

# ---------------------------------------------------------------------------
# Build leg definitions for each trade
# ---------------------------------------------------------------------------
# Legs: (column_name, position_sign, symbol_col)
LEGS = [
    ("sc", -1, "short_call"),
    ("sp", -1, "short_put"),
    ("lc", +1, "long_call"),
    ("lp", +1, "long_put"),
]

# Read trade schedule to get symbols
sched = pd.read_csv(ROOT / "data" / "trade_schedule.csv")

# Merge symbols into trades on ticker + earn_dt
sched["earn_dt"] = pd.to_datetime(sched["earn_dt"])
trades_with_syms = trades.merge(
    sched[["ticker", "earn_dt", "short_call", "short_put", "long_call", "long_put"]],
    on=["ticker", "earn_dt"], how="left"
)

# ---------------------------------------------------------------------------
# Compute daily Greeks
# ---------------------------------------------------------------------------
records = []
total = len(trades_with_syms)

for idx, trade in trades_with_syms.iterrows():
    if idx % 50 == 0:
        print(f"  {idx}/{total} trades...", end="\r")

    ticker   = trade["ticker"]
    q        = DIV_YIELD.get(ticker, 0.0)
    earn_dt  = trade["earn_dt"]

    leg_specs = [
        ("sc", -1, trade["short_call"].strip(), trade["short_entry_dt"], trade["short_exit_dt"]),
        ("sp", -1, trade["short_put"].strip(),  trade["short_entry_dt"], trade["short_exit_dt"]),
        ("lc", +1, trade["long_call"].strip(),  trade["long_entry_dt"],  trade["long_exit_dt"]),
        ("lp", +1, trade["long_put"].strip(),   trade["long_entry_dt"],  trade["long_exit_dt"]),
    ]

    for leg_name, sign, symbol, open_dt, close_dt in leg_specs:
        opt_type = parse_option_type(symbol)
        strike   = parse_strike(symbol)
        expiry   = parse_expiry(symbol)

        # All trading days this leg is open (inclusive on both ends)
        leg_days = [d for d in trading_days if open_dt <= d <= close_dt]

        for d in leg_days:
            mid  = get_mid_ffill(symbol, d)
            spot = get_spot(ticker, d)
            rate = get_rate(d)

            if np.isnan(mid) or np.isnan(spot) or spot <= 0:
                continue

            T = (expiry - d).days / 365.0
            iv = implied_vol(mid, spot, strike, T, rate, q, opt_type)
            g  = bs_greeks(spot, strike, T, rate, q, iv, opt_type)

            records.append({
                "ticker":    ticker,
                "earn_dt":   earn_dt.date(),
                "leg":       leg_name,
                "sign":      sign,          # -1 short, +1 long
                "symbol":    symbol,
                "date":      d.date(),
                "mid":       mid,
                "spot":      spot,
                "strike":    strike,
                "T":         round(T, 6),
                "rate":      round(rate, 6),
                "iv":        iv,
                "delta":     g["delta"],
                "gamma":     g["gamma"],
                "vega":      g["vega"],
                "theta":     g["theta"],
                "rho":       g["rho"],
                # signed Greeks (position direction applied)
                "pos_delta": sign * g["delta"],
                "pos_gamma": sign * g["gamma"],
                "pos_vega":  sign * g["vega"],
                "pos_theta": sign * g["theta"],
                "pos_rho":   sign * g["rho"],
            })

print(f"\nTotal Greek rows: {len(records):,}")

daily = pd.DataFrame(records)
daily.to_parquet(ROOT / "results" / "daily_greeks.parquet", index=False)
print("Saved -> results/daily_greeks.parquet")

# Quick sanity check
print("\nSample (first 3 rows):")
print(daily.head(3)[["ticker","earn_dt","leg","date","mid","iv","delta","vega","theta"]].to_string())
