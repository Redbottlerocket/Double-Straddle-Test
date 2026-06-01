# Double Straddle Earnings Backtest

Backtesting a calendar straddle strategy across 25 stocks using historical options data (2016–2026). Each earnings cycle opens a short near-term straddle and a long far-term straddle simultaneously.

## Language

**Calendar Straddle**:
The combined position opened each earnings cycle: short the near-term straddle and long the far-term straddle simultaneously on the entry date. Also called a "double straddle" in this project.
_Avoid_: double straddle, vol spread, diagonal

**Near-Term Straddle**:
The short leg of the calendar straddle — a sold ATM call and sold ATM put expiring 3–4 days after the earnings date. Profits from IV crush after earnings.
_Avoid_: short straddle, front leg, short-dated straddle

**Far-Term Straddle**:
The long leg of the calendar straddle — a bought ATM call and bought ATM put expiring past the next earnings date. Held into the next earnings cycle to capture IV expansion.
_Avoid_: long straddle, back leg, long-dated straddle

**Entry Date**:
The date both straddle legs are opened simultaneously — 7 calendar days before the earnings date. Short legs are sold at the bid, long legs are bought at the ask, using the end-of-day closing snapshot.
_Avoid_: open date, trade date, start date

**Earnings Date**:
The date the company reports earnings (`earn_dt` in the trade schedule). Earnings are typically released after market close.
_Avoid_: report date, announcement date

**Near-Term Exit**:
The expiry of the near-term straddle (typically 2–7 days after earnings). Settled at intrinsic value using the underlying's close on expiry day — `max(spot - strike, 0)` for the call, `max(strike - spot, 0)` for the put. No bid/ask needed.
_Avoid_: expiry, short exit, earnings exit, buyback

**Far-Term Exit**:
One trading day before the next earnings date. The far-term straddle is sold at the bid using the end-of-day closing snapshot.
_Avoid_: long exit, expiry exit, next earnings close

**Closing Snapshot**:
The bid/ask quote captured at or near the 4:00 PM ET market close for each option contract each trading day. The single point-in-time quote we use for all fills. Pulled from Databento OPRA.PILLAR as one row per (symbol, date) in `data/options_daily.parquet` (or `options_close.parquet` for the cbbo-1h re-pull).
_Avoid_: EOD price, daily mid, market close

**Raw Data**:
The unprocessed Databento response saved to `data/raw/` before any reduction. Preserved on disk so that alternative EOD filters or schemas can be re-derived without re-paying for the same data.
_Avoid_: source data, original data, dump

**Net Premium**:
The net cash outlay per trade: far-term straddle cost minus near-term straddle credit, in dollars (1 contract = 100 shares).
_Avoid_: cost basis, debit, net debit

**Trade P&L**:
Total dollar profit or loss for a single earnings cycle: near-term straddle P&L plus far-term straddle P&L.
_Avoid_: profit, return, gain/loss

**Return on Net Premium**:
Trade P&L divided by the absolute net premium paid. The headline percentage metric normalizing performance across stocks.
_Avoid_: ROI, percent return, yield

**IV (Implied Volatility)**:
The volatility value solved from the Black-Scholes model that reproduces the observed mid price for a given option. Calculated daily for all 4 legs while positions are open.
_Avoid_: vol, realized vol, historical vol

**Greeks**:
Delta, gamma, vega, theta, and rho — calculated daily using Black-Scholes with time-varying risk-free rate and per-stock continuous dividend yield.
_Avoid_: sensitivities, risk measures
