import bisect
from datetime import date, timedelta

import numpy as np
import pandas as pd
import yfinance as yf


# ---------------------------------------------------------------------------
# Expiry helpers
# ---------------------------------------------------------------------------

def _next_friday_on_or_after(d: date) -> date:
    days = (4 - d.weekday()) % 7
    return d + timedelta(days=days)


def _third_friday(year: int, month: int) -> date:
    first = date(year, month, 1)
    first_fri = _next_friday_on_or_after(first)
    return first_fri + timedelta(weeks=2)


def _next_monthly_on_or_after(d: date) -> date:
    tf = _third_friday(d.year, d.month)
    if tf >= d:
        return tf
    nxt_month = d.month % 12 + 1
    nxt_year  = d.year + (1 if d.month == 12 else 0)
    return _third_friday(nxt_year, nxt_month)


def short_expiry_date(earnings_date: date, expiry_type: str = "weekly") -> date:
    """Expiry for the short straddle — first valid expiry *after* earnings."""
    day_after = earnings_date + timedelta(days=1)
    if expiry_type == "weekly":
        return _next_friday_on_or_after(day_after)
    return _next_monthly_on_or_after(day_after)


def long_expiry_date(next_earnings_date: date) -> date:
    """Expiry for the long straddle — first monthly expiry *after* next earnings."""
    return _next_monthly_on_or_after(next_earnings_date + timedelta(days=1))


# ---------------------------------------------------------------------------
# Strike rounding
# ---------------------------------------------------------------------------

def atm_strike(price: float) -> float:
    """Round a stock price to the nearest standard option strike increment."""
    if   price <=   5:  inc = 0.50
    elif price <=  25:  inc = 1.00
    elif price <=  50:  inc = 2.50
    elif price <= 200:  inc = 5.00
    elif price <= 500:  inc = 10.0
    elif price <= 1000: inc = 25.0
    elif price <= 2000: inc = 50.0
    else:               inc = 100.0
    return round(price / inc) * inc


# ---------------------------------------------------------------------------
# OSI symbol builder
# ---------------------------------------------------------------------------

def osi_symbol(ticker: str, expiry: date, strike: float, option_type: str) -> str:
    """
    Build an OSI/OCC option symbol for Databento raw_symbol queries.
    Format:  {root:6}{YYMMDD}{C|P}{strike*1000:08d}
    Example: 'AAPL  160115C00097500'
    """
    root       = f"{ticker:<6}"
    exp        = expiry.strftime("%y%m%d")
    cp         = "C" if option_type.upper().startswith("C") else "P"
    strike_int = int(round(strike * 1000))
    return f"{root}{exp}{cp}{strike_int:08d}"


# ---------------------------------------------------------------------------
# Actual (unadjusted) stock prices
# ---------------------------------------------------------------------------

def fetch_actual_prices(tickers: list, start: str, end: str) -> pd.DataFrame:
    """
    Download actual (pre-split-adjustment) stock close prices via yfinance.

    yfinance 'Close' is always backward-adjusted for ALL historical splits,
    including splits that occurred AFTER the price date. This function reverses
    those future-split adjustments so each row reflects what the stock actually
    traded at on that day — which is what option strikes were set against.

    Example: AAPL Close on 2016-01-19 from yfinance = $24.17.
             Actual traded price = $24.17 * 4 (Aug-2020 4:1 split) = $96.68.
    """
    raw = yf.download(tickers, start=start, end=end,
                      auto_adjust=False, progress=False, threads=True)

    close = raw["Close"]
    if isinstance(close.columns, pd.MultiIndex):
        close = close.droplevel(0, axis=1)
    close.index = pd.to_datetime(close.index).date
    result = close.copy().astype(float)

    for ticker in tickers:
        if ticker not in result.columns:
            continue
        try:
            splits = yf.Ticker(ticker).splits
            if splits.empty:
                continue
            # Normalise split index to plain date objects
            splits.index = pd.to_datetime(splits.index).tz_localize(None).date
            split_dates  = sorted(splits.index.tolist())
            split_vals   = [float(splits.loc[d]) for d in split_dates]

            # Build suffix product array: suffix[i] = product of splits[i:]
            n      = len(split_vals)
            suffix = [1.0] * (n + 1)
            for i in range(n - 1, -1, -1):
                suffix[i] = suffix[i + 1] * split_vals[i]

            # For every price date, find splits that occurred AFTER it and
            # multiply the yfinance price by their product to undo the
            # backward adjustment.
            for d in result.index:
                idx = bisect.bisect_right(split_dates, d)  # first split > d
                adj = suffix[idx]
                if adj != 1.0 and not pd.isna(result.loc[d, ticker]):
                    result.loc[d, ticker] = result.loc[d, ticker] * adj

        except Exception as exc:
            print(f"  Warning: split correction failed for {ticker}: {exc}")

    return result
