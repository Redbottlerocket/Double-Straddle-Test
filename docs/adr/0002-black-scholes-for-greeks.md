# Black-Scholes for IV and Greeks

IV and all Greeks (delta, gamma, vega, theta, rho) are calculated using the Black-Scholes European option model rather than a binomial or Barone-Adesi-Whaley American model.

These are American-style equity options, but the strategy only trades near-ATM options where the early exercise premium is negligible. Black-Scholes IV and Greeks match thinkorswim Think Back values within 1–2% for this regime. The simpler model avoids a binomial tree dependency and runs in milliseconds per calculation using scipy.

Risk-free rate: time-varying 3-month T-bill rate from FRED, merged by date.
Dividends: continuous yield approximation, static per-stock table.
