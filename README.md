# NSE Kenya Options Validation and Screening Framework

A Black-76 pricing engine for NSE Kenya's Options on Single Stock Futures,
with published-price validation, smile-based screening, and daily
automated reporting via GitHub Actions.

## What this is

A **screening tool** for a developing options market. The engine:

- Fetches the NSE Kenya Derivatives Pricelist daily
- Recomputes every option price with undiscounted Black-76 (NSE Clear convention)
- Validates our output against NSE's published indicative prices
- Screens for strikes where published prices deviate from a fitted smile
  by more than a threshold, **and** whose deviation is isolated from
  neighbouring strikes (isolation filter)
- Commits a daily report to `reports/` via GitHub Actions

## What this is *not*

This is **not a trading system**. NSE Kenya's options market currently has:

- **No observable bid-ask** — NSE publishes flat-vol indicative prices only
- **Negligible liquidity** — most strikes have no quotes or volume
- **No smile to calibrate against** — one vol per underlying, all strikes flat

A "flag" in a daily report means *"this strike's published price deviates
from a fitted smile by more than X, and its deviation is isolated from
its neighbours."* It does **not** mean *"this option is mispriced and
tradeable."* Without bid-ask, we cannot distinguish genuine mispricing
from model error or from spread.

When the Kenyan options market develops real quotes, the framework is
ready to accept real prices in place of indicative ones.

## The calibration prior

Because Kenya publishes flat-vol indicative prices only, the smile shape
(`alpha`) cannot be calibrated directly from Kenyan data. We use a
documented cross-market prior:

- **Nifty 50** was calibrated on NSE India bhavcopy (18–74 day expiries)
- Median fitted `alpha` across expiries was **−7.6**
- This value is used as the Kenya prior (`alpha = -7.0` in `config.py`),
  with documented ±50% uncertainty
- Methodology and code in `research/cross_market/`

`beta` is held at 1.0 (fixed convexity prior) because quadratic fits over
narrow moneyness bands are numerically unstable — empirical beta is not
reliably recoverable without deeper market structure.

Why Nifty as the proxy: it's an emerging-market equity index with liquid
options and free public data. Published research consistently shows
emerging-market skew is steeper than developed-market skew (SPY: alpha
typically −2 to −4; Nifty: −5 to −10), and Kenya's investor base and
risk-off flows more closely resemble India's than the US's.

## Validation results

The Black-76 implementation matches NSE Clear's published indicative
prices to **sub-cent precision** across all six target underlyings
(SCOM, KCBG, EQTY, COOP, IMHP, KEGN). Maximum validation error across
four consecutive daily reports: **< 0.02 KES**.

This is the strongest signal in the project: the pricer, the discounting
convention, the day-count, and the PDF parsing all reproduce a real
exchange's published output.

## The isolation filter

Flags in the daily report pass two tests:

1. **Threshold test** — absolute anomaly > 0.05 KES *and* relative
   anomaly > 5% (protects against flagging near-zero-priced options
   where a single tick is a large percentage)
2. **Isolation test** — the flagged strike's anomaly exceeds **2×**
   the average anomaly of its two nearest neighbours

The isolation test is the important one. A real mispricing should stand
out from its neighbours; a smile-model misfit tends to cluster across
adjacent strikes. Filtering out clustered flags removes the systematic
calibration error that dominates any hypothesis-driven smile model.

## Architecture
