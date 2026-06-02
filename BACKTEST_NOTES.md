# Calendar Straddle Backtest — Notes

Personal reference covering: data pull, Greeks, portfolio Greek charts,
data coverage, P&L attribution, and the equity curve.

---

## 1. How the data was pulled

**Source:** Databento `OPRA.PILLAR` dataset, `cbbo-1m` schema (consolidated
best bid/offer, 1-minute bars). We keep the **last minute bar of each trading
day** (UTC hour ≥ 20, i.e. ≥ 3 PM ET) as the EOD quote, then derive
`mid = (bid + ask) / 2`.

**What gets pulled per earnings cycle:** exactly 4 OSI contracts.

| Leg | Strike | Expiry |
|---|---|---|
| `short_call` / `short_put` | ATM of spot **7 calendar days before** earnings | First weekly Friday **after** earnings (`short_exp`) |
| `long_call`  / `long_put`  | Same ATM strike | First monthly third-Friday **after** next earnings (`long_exp`) |

ATM strike rounded to the standard increment ($0.50 / $1 / $2.50 / $5 / $10 …
depending on the spot). Spot is pulled from yfinance with split corrections
reversed (so strikes match the **un-adjusted price** as it traded that day —
critical for picking ATM correctly pre-2020 splits).

**Pipeline (`pipeline/`):**
1. `01_cost_estimate.py` — generates `trade_schedule.csv` (971 cycles) and
   `symbol_list.csv` (3,506 contracts), queries Databento for cost. Free.
2. `02_pull_data.py` — actual pull. Cost: ~$18. Writes
   `data/options_daily.parquet`.

**Cycles vs trades:** 971 cycles scheduled, **818 executed** as trades — the
rest skip when no quote is available at entry or at expiry settlement.

---

## 2. How the Greeks were calculated

**Pricing model:** Black-Scholes-Merton with continuous dividend yield
(`strategy/greeks.py`, `bs_price` + `implied_vol`).

For every **open leg, every trading day** the position is held:
1. Look up the option **mid price** (forward-filled if a quote is missing).
2. Solve for **implied volatility** by Brent's method (`brentq` from SciPy)
   against that mid price.
3. Plug the IV back into BS to compute **delta, gamma, vega, theta, rho**.

Inputs per evaluation: spot from `equity_prices.parquet`, risk-free rate from
the FRED 3-month T-bill (`data/tbill_rate.csv`), dividend yield from the
static `DIV_YIELD` table in `daily_greeks.py`.

**Sign convention.** Each row gets both the raw Greek *and* a position-signed
version:

| Leg | Position sign |
|---|---|
| `sc`, `sp` (short call, short put) | **−1** |
| `lc`, `lp` (long call,  long put)  | **+1** |

The signed columns (`pos_delta`, `pos_vega`, …) are what gets summed for
portfolio-level views. Output: `results/daily_greeks.parquet` (one row per
leg-day).

---

## 3. What the portfolio Greek charts mean

The whole point of the β-scaling is the **additive property** — divide each
ticker's Greek by the same common denominator (SPX or VIX) so they live in
the same units and can be **summed across positions** to a meaningful
portfolio number. Without this, AAPL's delta and GOOGL's delta measure
different things because their underlyings have different vols and prices;
after scaling, both are denominated in "$ P&L per 1% SPX move" and can be
added.

The portfolio Greeks are **β-scaled into SPX/VIX-equivalent dollars** so they
read like P&L sensitivities to a market-wide move
(`strategy/portfolio_greeks.py` → `results/charts/11_…14_…`).

Per-leg-day scaling:

| Quantity | Formula | Reads as | Common denominator |
|---|---|---|---|
| `delta_$` | `pos_delta × spot × β` | $ P&L per 1% SPX move | SPX |
| `gamma_$` | `pos_gamma × β² × spot² × 0.01` | $ Δdelta per 1% SPX move | SPX |
| `vega_$`  | `pos_vega × 100 × β_IV` | $ P&L per 1 vol point of VIX | VIX |
| `theta_$` | `pos_theta × 100` | $ P&L per calendar day | time (universal) |

Where:
- **β** = rolling 60-day **cov(stock log-return, SPX log-return) / var(SPX)** —
  per ticker, per date. The `/ var(SPX)` is the "divide by SPX" step that
  gives the additive denominator.
- **β_IV** = rolling 60-day **cov(Δ stock IV, Δ VIX) / var(Δ VIX)** — same
  idea for IV: divides by VIX variance so every ticker's vega is in
  "$/VIX-point" units. Stock IV is the mean of open-leg IVs (capped at 200%
  to drop numerical outliers), multiplied by 100 to match VIX's vol-point unit.

Aggregated by **summing across all open legs** each day. Because every leg
is in the same SPX-equivalent (or VIX-equivalent) unit, the sum is a real
portfolio sensitivity, not a meaningless sum of incompatible numbers.

**What you should see in each chart (the textbook calendar profile):**

- **Delta** (`11_portfolio_delta.png`): close to zero most of the time. ATM
  straddles are delta-neutral at entry; drift comes from spot moving between
  earnings events while positions are open. Spikes near earnings are mostly
  noise.
- **Gamma** (`12_portfolio_gamma.png`): **negative during the short-leg
  phase** (you're short gamma into earnings — a big move hurts), recovers to
  near zero once the short expires and the long leg's gamma dominates.
- **Vega** (`13_portfolio_vega.png`): **negative pre-earnings** (you sold IV;
  if VIX rises before earnings you lose), then **positive in the long-only
  phase** (you're long vega waiting for IV to expand into the next earnings).
  This is the strategy's core thesis in one chart.
- **Theta** (`14_portfolio_theta.png`): **positive pre-earnings** (short
  premium collecting decay), **negative post short-expiry** (paying theta on
  the long straddle for ~80 days). The strategy bleeds theta during the
  long-only window — that bleed is what IV expansion has to overcome.

---

## 4. How much data and the days around earnings

| Coverage | Value |
|---|---|
| Tickers | **25** (large-cap tech/growth — AAPL, NVDA, TSLA, MSFT, GOOGL, AMZN, META, …) |
| Date range | **2016-01-04 → 2026-04-30** (~10 years 4 months) |
| Earnings cycles scheduled | 971 |
| Trades actually executed | **818** |
| EOD option rows | 307,110 |
| Unique option contracts | 3,506 |
| Equity closes | 2,596 days |
| Risk-free rate | Daily 3-month T-bill from FRED |

**Where the trade dates sit relative to earnings (calendar days):**

| Date | Typical placement |
|---|---|
| `entry_dt` | ~7 calendar days **before** `earn_dt` |
| `short_entry_dt` | first day from `entry_dt` with a valid bid on both short legs |
| `earn_dt` | earnings event |
| `short_exit_dt` | `short_exp` = first Friday after earnings (settled at intrinsic) |
| `long_exit_dt` | one trading day **before** `next_earn` (~90 days later) |
| `long_exp` | first monthly Friday after `next_earn` |

**Holding periods (calendar days):**

| Leg | mean | median | p25 / p75 | min / max |
|---|---|---|---|---|
| Short | 9.0 | 9 | 8 / 10 | 8 / 14 |
| Long | 82.1 | 92 | 71 / 97 | 0 / 133 |

So the short is exposed for ~1 trading week (entry ~5 TDs before earnings,
exit at the post-earnings weekly), and the long sits open for ~3 months,
mostly *after* the short has expired.

---

## 5. Why trades made and lost money

Three sources of P&L on each trade:

| Driver | How it shows up | Sign on a "good" outcome |
|---|---|---|
| **IV crush on the short** | Short call+put implied move > realised move at expiry → keep more of the credit | Positive |
| **IV expansion on the long** | Long call+put rally as the next earnings approaches → exit above entry debit | Positive |
| **Spot drift** | Underlying moves while you're holding | Mixed — small moves help (short keeps credit, long gets some intrinsic); huge moves on the wrong side hurt |

**Empirical attribution (818 trades):**

| Leg | Cum P&L | Avg / trade | Win rate |
|---|---|---|---|
| **Short** | **+$58,193** | **+$71** | **55.9%** |
| **Long**  | **−$13,083** | **−$16** | 39.4% |
| **Combined** | **+$45,110** | **+$55** | 42.9% |

(Avg winner $2,539, avg loser −$1,812, median trade −$134.)

**Where the +$71/trade short edge actually comes from — IV crush, literally:**

| Avg implied move (short credit sold) | $18.90 / share |
|---|---|
| Avg realised move (intrinsic at short expiry) | $18.19 / share |
| **Edge** | **$0.71 / share × 100 = $71 / trade** |

The market over-prices the implied move by ~$0.71/share on average. The
stock stays inside the implied move in **55.9%** of trades — that's exactly
the short-leg win rate. **IV crush is what makes the short profitable, and
over 818 trades it added +$58k.**

The edge is small per trade because the options market is mostly efficient.
Wins are capped at the credit (~$1.1k avg); losses are unbounded (worst
single-trade short P&L: −$18k on GOOGL Feb-2022). So you collect a steady
small edge and occasionally give back a chunk on a huge earnings surprise.

- **The short leg is the reliable workhorse** — small positive expectancy
  every cycle, +$58k cumulative. Driven directly by implied > realised.
- **The long leg is the high-variance vega bet** — sub-40% win rate, −$13k
  cumulative. Theta usually wins in the long-only window; the strategy hopes
  IV expansion into the next earnings overcomes it.
- **Correlation between leg P&Ls: −0.07** (essentially zero). They're
  independent — one doesn't predict the other.

**Top 10 winners** are almost all driven by the **long leg blowing up to the
upside** (huge IV expansion or directional move):
- TSLA Apr-2020 (+$64k, long +$55k) — IV exploded post-COVID rally
- ASML Oct-2025 (+$31k, long +$26k)
- AMZN Oct-2017 (+$21k, long +$29k offsetting short −$8k)

**Top 10 losers** are mostly the **long leg getting crushed**:
- AMZN Oct-2020 (−$35k, long −$41k) — IV collapsed faster than spot moved
- GOOGL Feb-2022 (−$35k, both legs −$17k each) — earnings move clobbered short, IV collapse hurt long
- AMZN Feb-2022 (−$34k)

**Read this honestly:** the strategy's structural alpha is the short leg's
IV-crush edge — small, consistent, +$58k over a decade. The long leg is a
separate high-variance bet bolted on top: it's slightly negative on average
but provides the +$64k tails that pad the headline cumulative. Almost all
the variance in the equity curve — good and bad — comes from the long-leg
side.

---

## 6. How the equity curve by trade works

`strategy/_performance_dashboard.py` → `results/performance_dashboard.png`.

The equity curve is **indexed by trade**, not calendar date — each x-axis
point is one earnings event, sorted chronologically. Steps:

1. Sort `trades.csv` by `earn_dt`.
2. `cum_pnl = total_pnl.cumsum()` — running total of realised P&L.
3. `peak = cum_pnl.cummax()` — the high-water mark.
4. `drawdown = cum_pnl - peak` — distance below the running peak (≤ 0).

So at any trade *i* on the curve, the height is "$ you would have made if
you'd traded every cycle since 2016, settling each trade in full before the
next one starts." Drawdown is the dollar drop from the most recent peak.

**Key metrics on the dashboard:**
- Cumulative P&L, Avg P&L per trade
- Win rate, Avg winner / Avg loser, Profit factor
- Max drawdown (worst dollar peak-to-trough)
- Sharpe (annualised assuming 4 trades/stock/year)
- Annual P&L bars, monthly heatmap, per-ticker totals, return distribution

**Important distinction — equity-curve-by-trade vs portfolio-by-day:**

| View | File | Granularity | What it shows |
|---|---|---|---|
| By trade | `_performance_dashboard.py` | One point per earnings | Cumulative realised P&L between closed trades |
| By day | `portfolio_daily.py` → `portfolio_daily.csv` | One row per trading day | Mark-to-market book value while positions are *open* |

The day-by-day book marks shorts at ASK and longs at BID (liquidation marks)
and reconciles to the same total — sum of daily P&L equals the trades.csv
total. The day-level view shows mid-trade drawdowns the trade-level view
can't.

---

## 7. One-paragraph summary

You short the ATM straddle expiring just after each earnings event and buy
the ATM straddle expiring just after the *next* earnings event, entering both
~7 days before earnings. The data: ~10 years, 25 tickers, **818 trades**,
pulled from Databento OPRA at EOD. The short side captures **IV crush
(+$58k cumulative, +$71/trade, 55.9% wins)** — the implied move averages
$0.71/share above the realised move, and that gap is the edge. The long
side is a separate vega bet held ~80 more days hoping IV expands into the
next earnings (−$13k cumulative, −$16/trade, 39.4% wins). **Combined: +$45k
cumulative, +$55/trade, 42.9% win rate** — slightly positive expectancy
with the long-leg variance dominating both tails. Greeks are computed per
leg per day from implied-volatility-inverted mid prices, then β-scaled into
SPX/VIX-equivalent dollars to read as additive P&L sensitivities. The
portfolio Greek charts should show short-vega / short-gamma / positive-theta
in the pre-earnings window flipping to long-vega / negative-theta in the
long-only window — that's the entire strategy in one picture.

---

## Code references

| File | What it does |
|---|---|
| `pipeline/01_cost_estimate.py` | Generates trade schedule + symbol list, queries Databento cost |
| `pipeline/02_pull_data.py`     | Pulls EOD bid/ask from Databento → `options_daily.parquet` |
| `strategy/backtest.py`         | Builds trades.csv (P&L per cycle, bid/ask fills) |
| `strategy/greeks.py`           | BS price, implied vol (Brent), Greeks |
| `strategy/daily_greeks.py`     | Per-leg per-day IV and Greeks → `daily_greeks.parquet` |
| `strategy/portfolio_greeks.py` | β-scaled portfolio Greeks → `portfolio_greeks.parquet` |
| `strategy/portfolio_daily.py`  | Day-by-day mark-to-market book → `portfolio_daily.csv` |
| `strategy/_portfolio_greeks_charts.py` | The four portfolio-Greek charts |
| `strategy/_performance_dashboard.py`   | Equity curve, drawdown, annual P&L, per-ticker totals |
