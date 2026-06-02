# Wide Strike Data Pull

Self-contained Databento options pull. Wider strike band than the original —
covers ±3 weeks of spot drift around each earnings event (`earn_dt` and
`next_earn`).

## Setup

```bash
python -m venv venv
./venv/Scripts/activate           # Windows
# or:  source venv/bin/activate   # macOS/Linux

pip install -r requirements.txt
export DATABENTO_API_KEY="your-key-here"   # Windows: setx DATABENTO_API_KEY "..."
```

## Run

```bash
# 1. Free cost preview (calls Databento metadata.get_cost — no charge)
python pipeline/01b_cost_estimate_wide.py

# 2. Only after reviewing the printed cost — this CHARGES the Databento account
python pipeline/02b_pull_data_wide.py
```

## Configuration

Knobs at the top of `pipeline/01b_cost_estimate_wide.py`:

| Knob | Default | Meaning |
|---|---|---|
| `K_STRIKES` | 5 | Minimum ±5 strikes around each cycle's original ATM |
| `WINDOW_TD` | 15 (~3 weeks) | Extra strikes covering actual spot high/low over ±15 trading days around `earn_dt` AND `next_earn` |

## Files

```
data_pull/
  README.md
  requirements.txt
  pipeline/
    01b_cost_estimate_wide.py   # cost preview, writes data/symbol_list_wide.csv
    02b_pull_data_wide.py       # actual pull, writes data/options_daily_wide.parquet
    config.py                   # dataset/period/keys
    options_utils.py            # atm_strike, osi_symbol helpers
  data/
    trade_schedule.csv          # 971 earnings cycles (input)
    equity_prices.parquet       # daily closes for 25 tickers (input)
```

## Outputs

- `data/symbol_list_wide.csv` — written by 01b
- `data/options_daily_wide.parquet` — written by 02b, columns `symbol, date, bid, ask, mid`
