"""
Fit the smile to an NSE India options chain.

Linear fit (iv = a + b*m) for reliable alpha extraction.
Quadratic fit (iv = a + b*m + c*m^2) for beta diagnostic only —
beta is numerically unstable over narrow moneyness bands, so it is
reported but not used for calibration.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Add project root to path so we can import the existing black76 module
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from black76 import implied_vol  # noqa: E402


def fit_smile_from_chain(options_df, valuation_date, r=0.065):
    """
    Fit the smile to one expiry's chain.

    Parameters
    ----------
    options_df : DataFrame
        Rows from Nifty bhavcopy, all with the same expiry.
    valuation_date : date or str
        The bhavcopy date (for computing T).
    r : float
        Risk-free rate.

    Returns
    -------
    dict with keys sigma_atm, alpha, beta_diagnostic, n_strikes,
    residual_rmse, T_days — or None if there are too few valid strikes.
    """
    val_dt = pd.to_datetime(valuation_date)
    rows = []

    for _, row in options_df.iterrows():
        try:
            expiry = pd.to_datetime(row["XpryDt"])
            days = (expiry - val_dt).days

            # Filter 0: only calibrate on 14-180 day expiries
            # (weekly options are too noisy to fit a smile reliably)
            if days < 14 or days > 180:
                continue

            T = days / 365.0
            F = float(row["UndrlygPric"])
            K = float(row["StrkPric"])
            price = float(row["ClsPric"])
            otype = row["OptnTp"]

            # Filter 1: minimum premium (avoid tick-size noise on 0.05 quotes)
            if price < 1.0:
                continue

            # Filter 2: moneyness within a sensible band
            m = np.log(K / F)
            if abs(m) > 0.15:
                continue

            # Filter 3: reject obviously bad IVs
            iv = implied_vol(price, F, K, T, otype, undiscounted=False, r=r)
            if iv < 0.02 or iv > 2.0:
                continue

            rows.append({
                "K": K, "F": F, "T": T, "m": m, "iv": iv, "type": otype,
            })
        except (ValueError, KeyError):
            continue

    if len(rows) < 6:
        return None

    df = pd.DataFrame(rows)

    # Use OTM options only (puts below F, calls above) — standard practice
    otm = pd.concat([
        df[(df["type"] == "PE") & (df["m"] < 0)],
        df[(df["type"] == "CE") & (df["m"] >= 0)],
    ])
    if len(otm) < 6:
        otm = df

    # Linear OLS: iv = a + b*m
    m = otm["m"].values
    iv = otm["iv"].values
    X_lin = np.column_stack([np.ones(len(m)), m])
    coefs_lin, _, _, _ = np.linalg.lstsq(X_lin, iv, rcond=None)
    a, b = coefs_lin

    if a <= 0:
        return None

    # Quadratic fit for DIAGNOSTIC only (do not use beta for calibration)
    X_quad = np.column_stack([np.ones(len(m)), m, m * m])
    coefs_quad, _, _, _ = np.linalg.lstsq(X_quad, iv, rcond=None)
    _, _, c_quad = coefs_quad
    beta_diagnostic = float(c_quad / a) if a > 0 else float("nan")

    residuals = iv - X_lin @ coefs_lin
    return {
        "sigma_atm": float(a),
        "alpha": float(b / a),
        "beta_diagnostic": beta_diagnostic,
        "n_strikes": len(otm),
        "residual_rmse": float(np.sqrt(np.mean(residuals ** 2))),
        "T_days": float(otm["T"].mean() * 365),
    }