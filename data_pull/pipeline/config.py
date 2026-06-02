import os

DATABENTO_KEY = os.environ.get("DATABENTO_API_KEY", "")
if not DATABENTO_KEY:
    raise EnvironmentError(
        "Set DATABENTO_API_KEY in your environment before running any script."
    )

TICKERS = [
    "AAPL", "AMZN", "NVDA", "TSLA", "MSFT", "GOOGL", "META", "NFLX",
    "AVGO", "MU",   "ASML", "AMD",  "INTC", "CSCO", "PLTR", "AMAT",
    "PDD",  "BABA", "ABNB", "AMGN", "ORCL", "ACM",  "QCOM", "ADBE", "ZM",
]

BACKTEST_START = "2016-01-01"
BACKTEST_END   = "2026-05-01"   # through end of April 2026

ENTRY_DAYS_BEFORE = 7           # calendar days before earnings to enter position
SHORT_EXPIRY_TYPE  = "weekly"   # "weekly" or "monthly"

RISK_FREE_RATE = 0.04           # annualised, used only for Greeks computation

DATASET = "OPRA.PILLAR"
SCHEMA  = "cbbo-1m"          # consolidated best bid/offer, 1-min bars
EOD_UTC_HOUR = 20             # 3:00-4:00 PM ET in UTC; last bar of day used for pricing

DATA_DIR       = "data"
EARNINGS_FILE  = "earnings_history.csv"
NEXT_EARN_FILE = "earnings_dates.csv"
