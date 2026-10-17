"""
Configuration for the NSE EOD Volatility Arbitrage Engine.

Phase 1 scope:
  • EOD batch processing (Direction C)
  • Model validation against NSE's indicative Black-76 output
  • Smile-adjusted anomaly detection (Direction A)

The engine no longer uses CBK rates or synthetic futures.
F, sigma, and expiry are read directly from the NSE Derivatives Pricelist.
"""
from __future__ import annotations
from pathlib import Path
from typing import Dict

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
LOG_PATH = BASE_DIR / "engine.log"
OUTPUT_DIR = BASE_DIR / "reports"
OUTPUT_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# NSE Derivatives Pricelist
# ---------------------------------------------------------------------------
NSE_PRICELIST_BASE_URL = "https://www.nse.co.ke/dataservices/wp-content/uploads/"
NSE_PRICELIST_FILENAME = "Derivatives_Pricelist_{dd}-{MON}-{YYYY}.pdf"
NSE_PRICELIST_LOOKBACK_DAYS = 10  # search window backwards from today

# Underlyings we care about (Options on Single Stock Futures)
TARGET_UNDERLYINGS = ["SCOM", "KCBG", "EQTY", "COOP", "IMHP", "KEGN"]

# ---------------------------------------------------------------------------
# Contract specs (still used for position sizing display)
# ---------------------------------------------------------------------------
NSE_CONTRACT_MULTIPLIER = 100
FIXED_NOTIONAL_KES = 50_000.0

# ---------------------------------------------------------------------------
# Day-count conventions
# ---------------------------------------------------------------------------
FUTURES_DAY_COUNT = 364   # NSE's official futures day-count
THETA_DAY_COUNT = 365     # Greeks convention: calendar-day theta

# ---------------------------------------------------------------------------
# # ---------------------------------------------------------------------------
# Smile model — quadratic in log-moneyness
#     sigma(K) = sigma_ATM * (1 + alpha * m + beta * m^2)
#     m = ln(K / F)
#
# alpha = -7.0 is derived from calibrating the smile on Nifty 50 options
# (bhavcopy source, 18-74 day expiries, 2026-10-16). The median fitted
# alpha across expiries was -7.6. Nifty is used as a documented proxy
# because NSE Kenya publishes flat-vol indicative prices only, with no
# observable smile to calibrate against.
#
# Uncertainty: alpha for the Kenyan smile is likely within +/-50% of this
# value. See research/cross_market/ for the calibration methodology.
#
# beta is kept at 1.0 (fixed convexity prior). Quadratically fitting beta
# on narrow moneyness bands is numerically unstable; empirical beta is
# not reliably recoverable without deeper market structure.
# ---------------------------------------------------------------------------
SMILE_PARAMS: Dict[str, Dict[str, float]] = {
    "default": {
        "alpha": -7.00,
        "beta": 1.00,
    },
}

def get_smile_params(underlying: str) -> Dict[str, float]:
    return SMILE_PARAMS.get(underlying, SMILE_PARAMS["default"])
# ---------------------------------------------------------------------------
# Newton-Raphson IV solver (retained for optional use; not used by the
# EOD engine, which reads sigma directly from the NSE PDF)
# ---------------------------------------------------------------------------
IV_MAX_ITER = 100
IV_TOLERANCE = 1e-6
IV_LOWER_BOUND = 1e-6
IV_UPPER_BOUND = 5.0

# ---------------------------------------------------------------------------
# Signal thresholds
# ---------------------------------------------------------------------------
# Minimum absolute KES anomaly (smile price − NSE flat price) to log a signal
SMILE_ANOMALY_THRESHOLD_KES = 0.05

# Minimum relative anomaly (|anomaly| / NSE flat price) to log
SMILE_ANOMALY_THRESHOLD_PCT = 0.05

# Ignore strikes so deep OTM that sigma(K) explodes past this bound
SMILE_MAX_SIGMA = 3.00
SMILE_MIN_SIGMA = 0.01

# Validation: our flat price must match NSE's to within this tolerance
VALIDATION_TOLERANCE_KES = 0.02