import numpy as np
from scipy.stats import norm
from scipy.optimize import brentq


def _d1d2(S, K, T, r, q, sigma):
    """Merton (1973) d1/d2 with continuous dividend yield q."""
    d1 = (np.log(S / K) + (r - q + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    return d1, d1 - sigma * np.sqrt(T)


def bs_price(S: float, K: float, T: float, r: float, q: float,
             sigma: float, option_type: str = "call") -> float:
    """Black-Scholes price with continuous dividend yield q. T in years."""
    if T <= 0:
        return max(S - K, 0.0) if option_type == "call" else max(K - S, 0.0)
    d1, d2 = _d1d2(S, K, T, r, q, sigma)
    if option_type == "call":
        return S * np.exp(-q * T) * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
    return K * np.exp(-r * T) * norm.cdf(-d2) - S * np.exp(-q * T) * norm.cdf(-d1)


def implied_vol(market_price: float, S: float, K: float, T: float,
                r: float, q: float, option_type: str = "call") -> float:
    """Implied volatility via Brent's method. Returns NaN on failure."""
    if T <= 0 or S <= 0 or K <= 0 or market_price <= 0:
        return np.nan
    intrinsic = (max(S * np.exp(-q * T) - K * np.exp(-r * T), 0.0)
                 if option_type == "call"
                 else max(K * np.exp(-r * T) - S * np.exp(-q * T), 0.0))
    if market_price <= intrinsic * 1.0001:
        return np.nan
    try:
        return brentq(
            lambda sig: bs_price(S, K, T, r, q, sig, option_type) - market_price,
            1e-6, 20.0, xtol=1e-6, maxiter=200,
        )
    except (ValueError, RuntimeError):
        return np.nan


def greeks(S: float, K: float, T: float, r: float, q: float,
           iv: float, option_type: str = "call") -> dict:
    """
    Greeks for a single option position (one contract = 100 shares).

    Returns delta, gamma, vega (per 1% vol move), theta (per calendar day),
    rho (per 1% rate move). All NaN when inputs are invalid.
    """
    if T <= 0 or iv <= 0 or np.isnan(iv) or S <= 0 or K <= 0:
        return dict(delta=np.nan, gamma=np.nan, vega=np.nan, theta=np.nan, rho=np.nan)

    d1, d2 = _d1d2(S, K, T, r, q, iv)
    nd1 = norm.pdf(d1)
    sign = 1 if option_type == "call" else -1

    delta = sign * np.exp(-q * T) * norm.cdf(sign * d1)
    gamma = np.exp(-q * T) * nd1 / (S * iv * np.sqrt(T))
    vega  = S * np.exp(-q * T) * nd1 * np.sqrt(T) / 100
    theta = (
        -S * np.exp(-q * T) * nd1 * iv / (2 * np.sqrt(T))
        - sign * r * K * np.exp(-r * T) * norm.cdf(sign * d2)
        + sign * q * S * np.exp(-q * T) * norm.cdf(sign * d1)
    ) / 365
    rho = sign * K * T * np.exp(-r * T) * norm.cdf(sign * d2) / 100

    return dict(delta=delta, gamma=gamma, vega=vega, theta=theta, rho=rho)
