"""
Quadratic-in-log-moneyness volatility smile.

    sigma(K) = sigma_ATM * (1 + alpha * m + beta * m^2),  m = ln(K / F)

Guarantees:
  * sigma(F) == sigma_ATM   (when K = F, m = 0)
  * Bounded within [SMILE_MIN_SIGMA, SMILE_MAX_SIGMA]
"""
from __future__ import annotations

import math
from typing import List

from config import SMILE_MAX_SIGMA, SMILE_MIN_SIGMA


def smile_sigma(
    sigma_atm: float,
    K: float,
    F: float,
    alpha: float,
    beta: float,
) -> float:
    """Return the smile-adjusted implied volatility for strike K."""
    if F <= 0 or K <= 0:
        raise ValueError(f"F and K must be positive (F={F}, K={K})")

    m = math.log(K / F)
    raw = sigma_atm * (1.0 + alpha * m + beta * m * m)

    return max(SMILE_MIN_SIGMA, min(SMILE_MAX_SIGMA, raw))


def moneyness(K: float, F: float) -> float:
    """Return log-moneyness ln(K / F)."""
    return math.log(K / F)


def smile_surface(
    F: float,
    sigma_atm: float,
    strikes: List[float],
    alpha: float,
    beta: float,
) -> List[float]:
    """Return the smile IV for a list of strikes."""
    return [smile_sigma(sigma_atm, K, F, alpha, beta) for K in strikes]