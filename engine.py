"""
EOD Volatility Arbitrage Engine.

For each target underlying:
  1. Validate our undiscounted Black-76 against NSE's flat-vol output.
  2. Recompute every strike with a quadratic smile.
  3. Log every strike where the smile price differs from NSE's flat price
     by more than the configured threshold.

Runs as a batch job (typically 17:00 EAT).
"""
from __future__ import annotations
import csv
import logging
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from black76 import (
    black76_price, black76_delta, black76_gamma,
    black76_vega_per_pct, black76_theta_daily,
)
from smile import smile_sigma, moneyness
from nse_data import (
    load_pricelist, PricelistSnapshot, OptionChain, StrikeRow,
)
from config import (
    TARGET_UNDERLYINGS,
    get_smile_params,
    SMILE_ANOMALY_THRESHOLD_KES,
    SMILE_ANOMALY_THRESHOLD_PCT,
    VALIDATION_TOLERANCE_KES,
    OUTPUT_DIR,
)

log = logging.getLogger(__name__)


@dataclass
class StrikeReport:
    underlying: str
    name: str
    expiry_label: str
    days_to_expiry: int
    F: float
    K: float
    moneyness_m: float

    # NSE's published indicative prices (KES)
    nse_call: float
    nse_put: float

    # Our flat-vol Black-76 (should match NSE)
    flat_call: float
    flat_put: float
    validation_error_call: float
    validation_error_put: float

    # Our smile-model prices
    sigma_smile: float
    smile_call: float
    smile_put: float

    # Anomalies (smile - NSE)
    anomaly_call: float
    anomaly_put: float
    anomaly_call_pct: float
    anomaly_put_pct: float

    # Greeks on the smile-implied price (per contract)
    delta_call: float
    delta_put: float
    gamma: float
    vega_call: float
    vega_put: float
    theta_call: float
    theta_put: float

    flagged_call: bool
    flagged_put: bool


def _evaluate_strike(chain: OptionChain, row: StrikeRow,
                     alpha: float, beta: float) -> StrikeReport:
    F = chain.F
    K = row.strike
    T = chain.days_to_expiry / 365.0
    sigma_atm = chain.sigma_atm

    # --- Flat vol: should match NSE exactly ---
    flat_call = black76_price(F, K, T, sigma_atm, "CALL", undiscounted=True)
    flat_put = black76_price(F, K, T, sigma_atm, "PUT", undiscounted=True)

    # --- Smile vol ---
    sigma_K = smile_sigma(sigma_atm, K, F, alpha, beta)
    smile_call = black76_price(F, K, T, sigma_K, "CALL", undiscounted=True)
    smile_put = black76_price(F, K, T, sigma_K, "PUT", undiscounted=True)

    # --- Greeks on the smile price ---
    delta_call = black76_delta(F, K, T, sigma_K, "CALL", undiscounted=True)
    delta_put = black76_delta(F, K, T, sigma_K, "PUT", undiscounted=True)
    gamma = black76_gamma(F, K, T, sigma_K, undiscounted=True)
    vega_call = black76_vega_per_pct(F, K, T, sigma_K, undiscounted=True)
    vega_put = vega_call  # by Black-76 symmetry
    theta_call = black76_theta_daily(F, K, T, sigma_K, "CALL", undiscounted=True)
    theta_put = black76_theta_daily(F, K, T, sigma_K, "PUT", undiscounted=True)

    # --- Anomalies vs NSE ---
    anomaly_call = smile_call - row.call_prem
    anomaly_put = smile_put - row.put_prem
    anomaly_call_pct = anomaly_call / row.call_prem if row.call_prem > 0 else 0.0
    anomaly_put_pct = anomaly_put / row.put_prem if row.put_prem > 0 else 0.0

    flagged_call = (
        abs(anomaly_call) > SMILE_ANOMALY_THRESHOLD_KES
        and abs(anomaly_call_pct) > SMILE_ANOMALY_THRESHOLD_PCT
    )
    flagged_put = (
        abs(anomaly_put) > SMILE_ANOMALY_THRESHOLD_KES
        and abs(anomaly_put_pct) > SMILE_ANOMALY_THRESHOLD_PCT
    )

    return StrikeReport(
        underlying=chain.underlying,
        name=chain.name,
        expiry_label=chain.expiry_label,
        days_to_expiry=chain.days_to_expiry,
        F=F, K=K, moneyness_m=moneyness(K, F),
        nse_call=row.call_prem, nse_put=row.put_prem,
        flat_call=flat_call, flat_put=flat_put,
        validation_error_call=flat_call - row.call_prem,
        validation_error_put=flat_put - row.put_prem,
        sigma_smile=sigma_K,
        smile_call=smile_call, smile_put=smile_put,
        anomaly_call=anomaly_call, anomaly_put=anomaly_put,
        anomaly_call_pct=anomaly_call_pct,
        anomaly_put_pct=anomaly_put_pct,
        delta_call=delta_call, delta_put=delta_put,
        gamma=gamma,
        vega_call=vega_call, vega_put=vega_put,
        theta_call=theta_call, theta_put=theta_put,
        flagged_call=flagged_call, flagged_put=flagged_put,
    )


def run_eod(snapshot: PricelistSnapshot) -> List[StrikeReport]:
    reports: List[StrikeReport] = []
    for underlying in TARGET_UNDERLYINGS:
        chain = snapshot.chains.get(underlying)
        if chain is None:
            log.warning("No options chain for %s", underlying)
            continue
        fut = snapshot.futures.get(underlying)
        if fut is None:
            log.warning("No futures row for %s", underlying)
            continue
        if abs(fut.mtm_price - chain.F) > 0.01:
            log.warning(
                "%s: futures MTM %.2f differs from chain header F %.2f",
                underlying, fut.mtm_price, chain.F,
            )
        params = get_smile_params(underlying)
        for row in chain.strikes:
            reports.append(_evaluate_strike(
                chain, row, params["alpha"], params["beta"],
            ))
    return reports


def print_report(reports: List[StrikeReport],
                 snapshot: PricelistSnapshot) -> None:
    by_u: Dict[str, List[StrikeReport]] = {}
    for r in reports:
        by_u.setdefault(r.underlying, []).append(r)

    for u, rows in by_u.items():
        rows.sort(key=lambda r: r.K)
        ch = rows[0]
        params = get_smile_params(u)
        chain_sigma = snapshot.chains[u].sigma_atm if u in snapshot.chains else float("nan")

        print(f"\n=== {u} - {ch.name} ===")
        print(f"    F={ch.F:.2f}  sigma_ATM={chain_sigma:.4f}"
              f"  expiry={ch.expiry_label}  days={ch.days_to_expiry}")
        print(f"    smile: alpha={params['alpha']:+.2f}  beta={params['beta']:+.2f}")

        max_ve = max(abs(r.validation_error_call) for r in rows)
        max_vp = max(abs(r.validation_error_put) for r in rows)
        ok = "PASS" if max(max_ve, max_vp) <= VALIDATION_TOLERANCE_KES else "FAIL"
        print(f"    validation: max|dCall|={max_ve:.4f}  max|dPut|={max_vp:.4f}  [{ok}]")
        print(f"    {'K':>7} {'NSE C':>8} {'Smile C':>8} {'dC':>8}"
              f"  {'NSE P':>8} {'Smile P':>8} {'dP':>8}  flags")
        for r in rows:
            flags = ("C" if r.flagged_call else "-") + ("P" if r.flagged_put else "-")
            print(f"    {r.K:>7.2f} {r.nse_call:>8.4f} {r.smile_call:>8.4f} "
                  f"{r.anomaly_call:>+8.4f}  "
                  f"{r.nse_put:>8.4f} {r.smile_put:>8.4f} "
                  f"{r.anomaly_put:>+8.4f}  {flags}")


def print_top_discrepancies(reports: List[StrikeReport],
                            top_n: int = 10) -> None:
    """Print the largest discrepancies by absolute KES and by percentage."""
    # --- By absolute KES ---
    all_anomalies = []
    for r in reports:
        all_anomalies.append((abs(r.anomaly_call), r, "CALL", r.anomaly_call))
        all_anomalies.append((abs(r.anomaly_put), r, "PUT", r.anomaly_put))
    all_anomalies.sort(key=lambda x: x[0], reverse=True)

    print("\n" + "=" * 78)
    print(f"TOP {top_n} DISCREPANCIES (absolute KES)")
    print("=" * 78)
    print(f"  {'Rank':<5} {'Underlying':<12} {'Strike':>8} {'Side':<5} "
          f"{'NSE Price':>10} {'Smile Price':>12} {'Discrepancy':>12}")
    for i, (_, r, side, delta) in enumerate(all_anomalies[:top_n], 1):
        nse_price = r.nse_call if side == "CALL" else r.nse_put
        smile_price = r.smile_call if side == "CALL" else r.smile_put
        print(f"  {i:<5} {r.underlying:<12} {r.K:>8.2f} {side:<5} "
              f"{nse_price:>10.4f} {smile_price:>12.4f} {delta:>+12.4f}")

    # --- By relative % ---
    rel = []
    for r in reports:
        if r.nse_call > 0:
            rel.append((abs(r.anomaly_call_pct), r, "CALL",
                        r.anomaly_call, r.anomaly_call_pct))
        if r.nse_put > 0:
            rel.append((abs(r.anomaly_put_pct), r, "PUT",
                        r.anomaly_put, r.anomaly_put_pct))
    rel.sort(key=lambda x: x[0], reverse=True)

    print("\n" + "=" * 78)
    print(f"TOP {top_n} DISCREPANCIES (relative %)")
    print("=" * 78)
    print(f"  {'Rank':<5} {'Underlying':<12} {'Strike':>8} {'Side':<5} "
          f"{'NSE Price':>10} {'Smile Price':>12} {'Delta %':>10}")
    for i, (_, r, side, delta, pct) in enumerate(rel[:top_n], 1):
        nse_price = r.nse_call if side == "CALL" else r.nse_put
        smile_price = r.smile_call if side == "CALL" else r.smile_put
        print(f"  {i:<5} {r.underlying:<12} {r.K:>8.2f} {side:<5} "
              f"{nse_price:>10.4f} {smile_price:>12.4f} {pct:>+10.2%}")


def write_csv(reports: List[StrikeReport], path: Path) -> None:
    if not reports:
        return
    fields = list(asdict(reports[0]).keys())
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in reports:
            w.writerow(asdict(r))


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    log.info("Loading NSE Derivatives Pricelist...")
    snapshot = load_pricelist()
    log.info("Pricelist as-of %s (%s)", snapshot.as_of, snapshot.pdf_url)
    log.info("Futures parsed: %d   Chains parsed: %d",
             len(snapshot.futures), len(snapshot.chains))

    reports = run_eod(snapshot)
    print_report(reports, snapshot)
    print_top_discrepancies(reports, top_n=10)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = OUTPUT_DIR / f"strike_report_{stamp}.csv"
    write_csv(reports, csv_path)
    print(f"\nCSV written: {csv_path}")

    flagged = [r for r in reports if r.flagged_call or r.flagged_put]
    print(f"Flagged anomalies: {len(flagged)} of {len(reports)} strikes")


if __name__ == "__main__":
    main()