"""
SPX-equivalent portfolio greeks per day.

Methodology (matches the handwritten note):
  - β   (return beta to SPX): rolling 60-day cov(stock_ret, SPX_ret)/var(SPX_ret)
  - β_IV (IV beta to VIX):    rolling 60-day cov(ΔstockIV, ΔVIX)/var(ΔVIX)
                              stockIV = mean of open-leg IVs (capped at 200% to drop
                              numerical-artifact outliers); converted to vol points
                              (× 100) to match VIX units.

Per leg-day (sign already in pos_* columns):
  delta_$  = pos_delta × spot × β              ($ P&L per 1% SPX move)
  gamma_$  = pos_gamma × β² × spot² × 0.01      (change in $delta per 1% SPX move)
  vega_$   = pos_vega  × 100 × β_IV            ($ P&L per 1 vol pt of VIX)
  theta_$  = pos_theta × 100                    ($ P&L per day; no scaling)

Aggregated per date and written to results/portfolio_greeks.parquet.
"""

import pandas as pd
import numpy as np
from pathlib import Path

ROOT     = Path(__file__).parent.parent
WIN      = 60        # rolling window for both betas
IV_CAP   = 2.0       # cap stock IV at 200% before averaging (drops bogus outliers)

# --- Load --------------------------------------------------------------------
greeks  = pd.read_parquet(ROOT / "results" / "daily_greeks.parquet")
greeks["date"] = pd.to_datetime(greeks["date"])

equity  = pd.read_parquet(ROOT / "data" / "equity_prices.parquet")
equity["date"] = pd.to_datetime(equity["date"])

spx_vix = pd.read_parquet(ROOT / "data" / "spx_vix.parquet")
spx_vix.index = pd.to_datetime(spx_vix.index)

# --- Returns + VIX changes ---------------------------------------------------
spx_ret = np.log(spx_vix["spx"]).diff()
vix_chg = spx_vix["vix"].diff()           # vol points

equity_wide = equity.set_index("date").sort_index()
stock_ret   = np.log(equity_wide).diff()  # wide: date × ticker

# Align on common trading days
common = stock_ret.index.intersection(spx_ret.index)
stock_ret = stock_ret.loc[common]
spx_ret_a = spx_ret.loc[common]
vix_chg_a = vix_chg.loc[common]

# --- Rolling β (returns) -----------------------------------------------------
mkt_var = spx_ret_a.rolling(WIN).var()
beta_ret = pd.DataFrame(index=common, columns=stock_ret.columns, dtype=float)
for tk in stock_ret.columns:
    beta_ret[tk] = stock_ret[tk].rolling(WIN).cov(spx_ret_a) / mkt_var

# --- Stock daily IV (mean of open-leg IVs, capped) and β_IV ------------------
iv_clean = greeks.assign(iv_capped=greeks["iv"].clip(upper=IV_CAP))
stock_iv = (iv_clean.dropna(subset=["iv_capped"])
            .groupby(["ticker", "date"])["iv_capped"].mean()
            .unstack("ticker")
            .sort_index())
# Convert decimal → vol points to match VIX unit
stock_iv_pts = stock_iv * 100
iv_chg = stock_iv_pts.diff()

# Align IV index with SPX/VIX
common_iv = iv_chg.index.intersection(vix_chg_a.index)
iv_chg = iv_chg.loc[common_iv]
vix_chg_iv = vix_chg_a.loc[common_iv]

vix_var = vix_chg_iv.rolling(WIN).var()
beta_iv = pd.DataFrame(index=common_iv, columns=iv_chg.columns, dtype=float)
for tk in iv_chg.columns:
    beta_iv[tk] = iv_chg[tk].rolling(WIN).cov(vix_chg_iv) / vix_var

# --- Tidy long-form betas for merge -----------------------------------------
beta_ret_long = beta_ret.stack().rename("beta").reset_index()
beta_ret_long.columns = ["date", "ticker", "beta"]
beta_iv_long  = beta_iv.stack().rename("beta_iv").reset_index()
beta_iv_long.columns = ["date", "ticker", "beta_iv"]

g = greeks.merge(beta_ret_long, on=["date", "ticker"], how="left")
g = g.merge(beta_iv_long,  on=["date", "ticker"], how="left")

# Forward-fill betas within stock for isolated NaN trading days
g = g.sort_values(["ticker", "date"])
g["beta"]    = g.groupby("ticker")["beta"].ffill()
g["beta_iv"] = g.groupby("ticker")["beta_iv"].ffill()

# --- Scaled greeks per leg-day ----------------------------------------------
g["delta_$"] = g["pos_delta"] * g["spot"]            * g["beta"]
g["gamma_$"] = g["pos_gamma"] * g["beta"]**2 * g["spot"]**2 * 0.01
g["vega_$"]  = g["pos_vega"]  * 100                  * g["beta_iv"]
g["theta_$"] = g["pos_theta"] * 100

# --- Aggregate per date ------------------------------------------------------
port = g.groupby("date").agg(
    delta_dollars = ("delta_$", "sum"),
    gamma_dollars = ("gamma_$", "sum"),
    vega_dollars  = ("vega_$",  "sum"),
    theta_dollars = ("theta_$", "sum"),
    open_legs     = ("delta_$", "count"),
    n_tickers     = ("ticker",  "nunique"),
).sort_index()

out = ROOT / "results" / "portfolio_greeks.parquet"
port.to_parquet(out)
out_csv = ROOT / "results" / "portfolio_greeks.csv"
port.to_csv(out_csv)
print(f"Saved {len(port):,} daily rows -> {out.relative_to(ROOT)} + .csv")
print(f"\nLast 5 rows:")
print(port.tail(5).round(2).to_string())
print(f"\nSummary stats:")
print(port[["delta_dollars","gamma_dollars","vega_dollars","theta_dollars"]]
      .describe().round(2).to_string())
