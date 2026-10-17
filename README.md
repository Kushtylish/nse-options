# NSE Kenya Options Forward-Testing Engine

Signal-only forward-testing engine for Options on Single Stock Futures
(NSE NEXT).  Implements the Black-76 model as specified by NSE Clear.

## Locked design decisions

- Model: Black-76 (not Black-Scholes 1973). Underlying is the futures price F.
- Synthetic F: `F = S·(1+r)^(t/364) − FVD` (NSE Mark-to-Market Methodology).
- Risk-free rate: Linear interpolation per NSE MMR across three brackets
  (0–91, 91–182, 182–364 days), using KESONIA + 91/182/364-day T-bill rates.
- T-bill source: CBK Format A "Results of Treasury Bills" PDFs only.
  Column: "Weighted Average Interest Rate of accepted bids".
  Format B (Weekly Bulletin) is deliberately skipped.
- KESONIA source: CBK "Money in Kenya" page. Fallback 8.75%.
- Fallback on any scrape failure: `macro_settings.json` (last known good).
- IV solver: Newton-Raphson on Black-76 with bisection fallback.
  Basis contamination from synthetic F is accepted and logged for Phase 2.
- Greeks: per contract, aggregated per underlying.
  Theta = per calendar day (annual / 365).
  Vega  = per 1% absolute vol change.
- Sizing: fixed notional (default KES 50,000), not 1 contract per strike.
  Contract multiplier = 100 (NSE Market Notice 004DER/NSE/2025).
- Spread filter: `max(5% × price, 2 × tick_size)`.
  Tick = KES 0.01 below 100, KES 0.05 at or above 100.
- MTM / margin: not modelled (Phase 1 is signal-only).

## Running
