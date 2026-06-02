"""
2D sensitivity: entry day (both legs) x long-exit day.

Grid (3 weeks ~ 15 trading days):
  N_entry = 1..15 trading days before earn_dt
  M_exit  = 1..15 trading days before next_earn

Per trade & cell:
  - Target entry = earn_dt - N_entry TDs.  Forward-scan up to 3 TDs (bounded by
    earn_dt - 1) for first day where all 4 leg symbols have quotes.
    Sell short straddle at BID, buy long straddle at ASK.
  - Short held to expiry (short_exp); settled at intrinsic using equity close.
  - Target long exit = next_earn - M_exit TDs.  Backward-scan up to 3 TDs for
    first day where both long legs have quotes.  Sell at BID.

Output:
  results/sensitivity_grid.csv
  results/sensitivity_grid.png  (4 heatmaps)
"""
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path

ROOT = Path(__file__).parent.parent

# ---- Load data --------------------------------------------------------------
sched = pd.read_csv(ROOT / "data" / "trade_schedule.csv", parse_dates=[
    "earn_dt", "next_earn", "entry_dt", "short_exp", "long_exp"])

opts = pd.read_parquet(ROOT / "data" / "options_daily.parquet")
opts["date"] = pd.to_datetime(opts["date"])

equity = pd.read_parquet(ROOT / "data" / "equity_prices.parquet")
equity["date"] = pd.to_datetime(equity["date"])
equity_idx = equity.set_index("date")

trading_days = sorted(equity["date"].unique())
td_pos = {d: i for i, d in enumerate(trading_days)}

# ---- Fast price lookup ------------------------------------------------------
# Nested dicts: sym -> {date -> price}.  ~O(1) lookup, much faster than
# MultiIndex.loc which would dominate the 218k-cell sweep.
sym_bid, sym_ask = {}, {}
for sym, grp in opts.groupby("symbol"):
    s = sym.strip()
    sym_bid[s] = dict(zip(grp["date"], grp["bid"]))
    sym_ask[s] = dict(zip(grp["date"], grp["ask"]))

def bid(sym, d):  return sym_bid.get(sym, {}).get(d, np.nan)
def ask(sym, d):  return sym_ask.get(sym, {}).get(d, np.nan)

def nth_td_before(dt, n):
    """Trading day n TDs strictly before dt; None if out of range."""
    pos = None
    for i, d in enumerate(trading_days):
        if d >= dt:
            pos = i
            break
    if pos is None:
        return None
    target = pos - n
    return trading_days[target] if target >= 0 else None

def get_spot(ticker, date):
    if ticker not in equity_idx.columns:
        return np.nan
    col = equity_idx[ticker].dropna()
    valid = col[col.index <= date]
    return float(valid.iloc[-1]) if not valid.empty else np.nan

# ---- Sweep ------------------------------------------------------------------
ENTRY_RANGE = list(range(1, 16))   # TDs before earn_dt
EXIT_RANGE  = list(range(1, 16))   # TDs before next_earn
SCAN_DAYS   = 3                     # forward/backward scan window for missing quotes

cells = {(n, m): [] for n in ENTRY_RANGE for m in EXIT_RANGE}
skipped_trades = 0

for _, row in sched.iterrows():
    ticker    = row["ticker"]
    earn_dt   = row["earn_dt"]
    next_earn = row["next_earn"]
    short_exp = row["short_exp"]
    strike    = float(row["strike"])
    sc = row["short_call"].strip()
    sp = row["short_put"].strip()
    lc = row["long_call"].strip()
    lp = row["long_put"].strip()

    # Short intrinsic at expiry (constant across all cells for this trade)
    spot_exp = get_spot(ticker, short_exp)
    if np.isnan(spot_exp):
        skipped_trades += 1
        continue
    short_debit_exit = (max(spot_exp - strike, 0.0)
                       + max(strike - spot_exp, 0.0)) * 100

    # Pre-compute entry fills for each N (so they are reused across all M)
    entry_fills = {}  # N -> (entry_dt, short_credit, long_debit) or None
    for n in ENTRY_RANGE:
        target = nth_td_before(earn_dt, n)
        if target is None:
            entry_fills[n] = None
            continue
        pos = td_pos.get(target)
        hit = None
        for k in range(SCAN_DAYS + 1):
            if pos + k >= len(trading_days):
                break
            d = trading_days[pos + k]
            if d >= earn_dt:
                break
            sb, pb = bid(sc, d), bid(sp, d)
            la, pa = ask(lc, d), ask(lp, d)
            if not (np.isnan(sb) or np.isnan(pb) or np.isnan(la) or np.isnan(pa)):
                hit = (d, (sb + pb) * 100, (la + pa) * 100)
                break
        entry_fills[n] = hit

    # Pre-compute long exit fills for each M
    exit_fills = {}  # M -> (exit_dt, long_credit) or None
    for m in EXIT_RANGE:
        target = nth_td_before(next_earn, m)
        if target is None:
            exit_fills[m] = None
            continue
        pos = td_pos.get(target)
        hit = None
        for k in range(SCAN_DAYS + 1):
            if pos - k < 0:
                break
            d = trading_days[pos - k]
            lb, pb_ = bid(lc, d), bid(lp, d)
            if not (np.isnan(lb) or np.isnan(pb_)):
                hit = (d, (lb + pb_) * 100)
                break
        exit_fills[m] = hit

    # Build cells
    for n, e in entry_fills.items():
        if e is None:
            continue
        entry_dt_hit, short_credit, long_debit = e
        short_pnl   = short_credit - short_debit_exit
        net_premium = long_debit - short_credit
        for m, x in exit_fills.items():
            if x is None:
                continue
            exit_dt_hit, long_credit = x
            if exit_dt_hit <= entry_dt_hit:
                continue
            long_pnl  = long_credit - long_debit
            total_pnl = short_pnl + long_pnl
            ret_pct = (total_pnl / abs(net_premium) * 100) if net_premium != 0 else np.nan
            cells[(n, m)].append((total_pnl, ret_pct))

# ---- Aggregate --------------------------------------------------------------
rows = []
for (n, m), recs in cells.items():
    if not recs:
        rows.append({"n_entry": n, "m_exit": m, "n_trades": 0,
                     "cum_pnl": np.nan, "avg_pnl": np.nan,
                     "win_rate": np.nan, "avg_ret": np.nan, "med_ret": np.nan})
        continue
    arr = np.array(recs)
    pnl, ret = arr[:, 0], arr[:, 1]
    rows.append({
        "n_entry":  n,
        "m_exit":   m,
        "n_trades": len(recs),
        "cum_pnl":  float(np.nansum(pnl)),
        "avg_pnl":  float(np.nanmean(pnl)),
        "win_rate": float((pnl > 0).mean() * 100),
        "avg_ret":  float(np.nanmean(ret)),
        "med_ret":  float(np.nanmedian(ret)),
    })

grid = pd.DataFrame(rows).sort_values(["n_entry", "m_exit"]).reset_index(drop=True)
grid.to_csv(ROOT / "results" / "sensitivity_grid.csv", index=False)

# ---- Console summary --------------------------------------------------------
best_cum = grid.loc[grid["cum_pnl"].idxmax()]
best_ret = grid.loc[grid["avg_ret"].idxmax()]
best_win = grid.loc[grid["win_rate"].idxmax()]
print(f"Skipped trades (no equity close at short_exp): {skipped_trades}")
print(f"Grid cells populated: {(grid['n_trades']>0).sum()} / {len(grid)}")
print("\nBest cumulative P&L:")
print(f"  N={int(best_cum['n_entry'])}, M={int(best_cum['m_exit'])}, "
      f"trades={int(best_cum['n_trades'])}, "
      f"cum=${best_cum['cum_pnl']:,.0f}, win={best_cum['win_rate']:.1f}%, "
      f"avgRet={best_cum['avg_ret']:.1f}%")
print("\nBest avg return on net premium:")
print(f"  N={int(best_ret['n_entry'])}, M={int(best_ret['m_exit'])}, "
      f"trades={int(best_ret['n_trades'])}, "
      f"cum=${best_ret['cum_pnl']:,.0f}, win={best_ret['win_rate']:.1f}%, "
      f"avgRet={best_ret['avg_ret']:.1f}%")
print("\nBest win rate:")
print(f"  N={int(best_win['n_entry'])}, M={int(best_win['m_exit'])}, "
      f"trades={int(best_win['n_trades'])}, "
      f"cum=${best_win['cum_pnl']:,.0f}, win={best_win['win_rate']:.1f}%, "
      f"avgRet={best_win['avg_ret']:.1f}%")

# ---- Heatmaps ---------------------------------------------------------------
def pivot(metric):
    return grid.pivot(index="n_entry", columns="m_exit", values=metric)

panels = [
    ("cum_pnl",  "Cumulative P&L ($)",            "RdYlGn"),
    ("win_rate", "Win Rate (%)",                  "RdYlGn"),
    ("avg_ret",  "Avg Return on Net Premium (%)", "RdYlGn"),
    ("med_ret",  "Median Return (%)",             "RdYlGn"),
]

fig, axes = plt.subplots(2, 2, figsize=(14, 11))
fig.patch.set_facecolor("#1a1a2e")
fig.suptitle("Sensitivity Grid: Entry timing  x  Long-leg exit timing\n"
             "N = trading days before earn_dt (entry)   |   "
             "M = trading days before next_earn (long exit)",
             color="white", fontsize=12, fontweight="bold")

for ax, (col, label, cmap) in zip(axes.flat, panels):
    Z = pivot(col)
    vals = Z.values.astype(float)
    if col == "cum_pnl" or "Ret" in label or "Return" in label:
        vmax = np.nanmax(np.abs(vals))
        vmin = -vmax
    else:
        vmin, vmax = np.nanmin(vals), np.nanmax(vals)
    im = ax.imshow(vals, origin="lower", aspect="auto", cmap=cmap,
                   vmin=vmin, vmax=vmax,
                   extent=[Z.columns.min() - 0.5, Z.columns.max() + 0.5,
                           Z.index.min()   - 0.5, Z.index.max()   + 0.5])
    # Mark best cell
    if np.isfinite(vals).any():
        bi, bj = np.unravel_index(np.nanargmax(vals), vals.shape)
        bn, bm = Z.index[bi], Z.columns[bj]
        ax.plot(bm, bn, "*", color="white", ms=20, mec="black", mew=1.0)
        title = f"{label}  -  best at N={bn}, M={bm}"
    else:
        title = label
    ax.set_title(title, color="white", fontsize=10)
    ax.set_xlabel("M = TDs before next_earn (long exit)", color="#aaa")
    ax.set_ylabel("N = TDs before earn_dt (entry)",       color="#aaa")
    ax.set_xticks(EXIT_RANGE)
    ax.set_yticks(ENTRY_RANGE)
    ax.tick_params(colors="#aaa")
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("bottom", "left"):
        ax.spines[s].set_color("#444")
    cb = fig.colorbar(im, ax=ax, shrink=0.85)
    cb.ax.yaxis.set_tick_params(color="#aaa")
    plt.setp(plt.getp(cb.ax.axes, "yticklabels"), color="#aaa")

plt.tight_layout()
plt.savefig(ROOT / "results" / "sensitivity_grid.png", dpi=150,
            bbox_inches="tight", facecolor="#1a1a2e")
print("\nSaved -> results/sensitivity_grid.csv")
print("Saved -> results/sensitivity_grid.png")
