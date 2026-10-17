"""
Undiscounted Black-76 pricer, IV solver, and Greeks.

The NSE prices options as "Undiscounted (fully-margined futures options)".
That means e^(-rT) = 1 in every equation.  All functions here default to
this convention via the `undiscounted=True` flag.

Greeks conventions:
  • Theta: per calendar day (annual / 365)
  • Vega:  per 1% absolute vol change (raw / 100)
"""
from __future__ import annotations
import math
from typing import Literal

from scipy.stats import norm

from config import (
    IV_MAX_ITER,
    IV_TOLERANCE,
    IV_LOWER_BOUND,
    IV_UPPER_BOUND,
    THETA_DAY_COUNT,
)

OptionType = Literal["CALL", "PUT"]


def _d1_d2(F: float, K: float, T: float, sigma: float) -> tuple[float, float]:
    if T <= 0 or sigma <= 0:
        raise ValueError("T and sigma must be strictly positive")
    vol_sqrt_t = sigma * math.sqrt(T)
    d1 = (math.log(F / K) + 0.5 * sigma * sigma * T) / vol_sqrt_t
    d2 = d1 - vol_sqrt_t
    return d1, d2


# ---------------------------------------------------------------------------
# Pricing
# ---------------------------------------------------------------------------
def black76_price(F: float, K: float, T: float, sigma: float,
                  option_type: OptionType, undiscounted: bool = True,
                  r: float = 0.0) -> float:
    if T <= 0:
        return max(F - K, 0.0) if option_type == "CALL" else max(K - F, 0.0)
    d1, d2 = _d1_d2(F, K, T, sigma)
    if undiscounted:
        if option_type == "CALL":
            return F * norm.cdf(d1) - K * norm.cdf(d2)
        return K * norm.cdf(-d2) - F * norm.cdf(-d1)
    disc = math.exp(-r * T)
    if option_type == "CALL":
        return disc * (F * norm.cdf(d1) - K * norm.cdf(d2))
    return disc * (K * norm.cdf(-d2) - F * norm.cdf(-d1))


# ---------------------------------------------------------------------------
# Greeks
# ---------------------------------------------------------------------------
def black76_delta(F: float, K: float, T: float, sigma: float,
                  option_type: OptionType, undiscounted: bool = True,
                  r: float = 0.0) -> float:
    d1, _ = _d1_d2(F, K, T, sigma)
    if undiscounted:
        return norm.cdf(d1) if option_type == "CALL" else -norm.cdf(-d1)
    disc = math.exp(-r * T)
    return (disc * norm.cdf(d1)) if option_type == "CALL" else (-disc * norm.cdf(-d1))


def black76_gamma(F: float, K: float, T: float, sigma: float,
                  undiscounted: bool = True, r: float = 0.0) -> float:
    d1, _ = _d1_d2(F, K, T, sigma)
    base = norm.pdf(d1) / (F * sigma * math.sqrt(T))
    return base if undiscounted else math.exp(-r * T) * base


def black76_vega_raw(F: float, K: float, T: float, sigma: float,
                     undiscounted: bool = True, r: float = 0.0) -> float:
    """dV/d(sigma), where sigma is decimal (e.g. 0.2176)."""
    d1, _ = _d1_d2(F, K, T, sigma)
    base = F * norm.pdf(d1) * math.sqrt(T)
    return base if undiscounted else math.exp(-r * T) * base


def black76_vega_per_pct(F: float, K: float, T: float, sigma: float,
                         undiscounted: bool = True, r: float = 0.0) -> float:
    """dV/d(sigma) with sigma expressed per 1% (25% -> 26%)."""
    return black76_vega_raw(F, K, T, sigma, undiscounted, r) / 100.0


def black76_theta_annual(F: float, K: float, T: float, sigma: float,
                         option_type: OptionType, undiscounted: bool = True,
                         r: float = 0.0) -> float:
    """
    dV/dt as time advances (calendar T decreases).
    For undiscounted (r=0):
        Theta = -F * n(d1) * sigma / (2 * sqrt(T))
    """
    if T <= 0:
        return 0.0
    d1, _ = _d1_d2(F, K, T, sigma)
    decay = F * norm.pdf(d1) * sigma / (2.0 * math.sqrt(T))
    if undiscounted:
        return -decay
    # Discounted variant includes the r*V term
    disc = math.exp(-r * T)
    V = black76_price(F, K, T, sigma, option_type, undiscounted=False, r=r)
    return r * V - disc * decay


def black76_theta_daily(F: float, K: float, T: float, sigma: float,
                        option_type: OptionType, undiscounted: bool = True,
                        r: float = 0.0) -> float:
    return black76_theta_annual(F, K, T, sigma, option_type,
                                undiscounted, r) / THETA_DAY_COUNT


# ---------------------------------------------------------------------------
# Implied volatility — Newton-Raphson with bisection fallback
# ---------------------------------------------------------------------------
def _bisect_iv(target: float, F: float, K: float, T: float,
               option_type: OptionType, undiscounted: bool, r: float,
               lo: float, hi: float, tol: float, max_iter: int = 200) -> float:
    for _ in range(max_iter):
        mid = 0.5 * (lo + hi)
        price = black76_price(F, K, T, mid, option_type, undiscounted, r)
        if abs(price - target) < tol:
            return mid
        if price > target:
            hi = mid
        else:
            lo = mid
    return 0.5 * (lo + hi)


def implied_vol(market_price: float, F: float, K: float, T: float,
                option_type: OptionType, undiscounted: bool = True,
                r: float = 0.0,
                max_iter: int = IV_MAX_ITER, tol: float = IV_TOLERANCE,
                lo: float = IV_LOWER_BOUND, hi: float = IV_UPPER_BOUND) -> float:
    if T <= 0:
        raise ValueError("Cannot solve IV for expired contract")

    # No-arb bounds
    if option_type == "CALL":
        lower = max(F - K, 0.0)
        upper = F if undiscounted else F * math.exp(-r * T)
    else:
        lower = max(K - F, 0.0)
        upper = K if undiscounted else K * math.exp(-r * T)

    if market_price < lower - tol:
        raise ValueError(f"Price {market_price:.4f} below intrinsic {lower:.4f}")
    if market_price > upper + tol:
        raise ValueError(f"Price {market_price:.4f} above upper bound {upper:.4f}")
    if abs(market_price - lower) < tol:
        return lo

    # Brenner-Subrahmanyam seed
    denom = F if undiscounted else F * math.exp(-r * T)
    sigma = math.sqrt(2.0 * math.pi / T) * market_price / max(denom, 1e-9)
    sigma = min(max(sigma, 0.05), 2.0)

    for _ in range(max_iter):
        price = black76_price(F, K, T, sigma, option_type, undiscounted, r)
        diff = price - market_price
        if abs(diff) < tol:
            return sigma
        vega = black76_vega_raw(F, K, T, sigma, undiscounted, r)
        if vega < 1e-10:
            break
        sigma_new = sigma - diff / vega
        if not (lo < sigma_new < hi):
            return _bisect_iv(market_price, F, K, T, option_type,
                              undiscounted, r, lo, hi, tol)
        sigma = new_sigma if (new_sigma := sigma_new) else sigma
    return _bisect_iv(market_price, F, K, T, option_type,
                      undiscounted, r, lo, hi, tol)