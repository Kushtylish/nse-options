from cross_market.bhavcopy_fetch import fetch_latest_bhavcopy, nifty_options
from cross_market.fit_smile import fit_smile_from_chain

df, d = fetch_latest_bhavcopy()
print(f"Latest bhavcopy: {d}  ({len(df)} rows)")

nifty = nifty_options(df)
print(f"Nifty options after liquidity filter: {len(nifty)}")
print(f"Expiries: {sorted(nifty['XpryDt'].unique())[:6]}")

print("\nFits per expiry:")
print(f"{'Expiry':<12} {'T_days':>7} {'strikes':>8} {'sigma_ATM':>10} "
      f"{'alpha':>8} {'beta_diag':>10} {'rmse':>7}")
print("-" * 70)

for expiry in sorted(nifty["XpryDt"].unique()):
    sub = nifty[nifty["XpryDt"] == expiry]
    result = fit_smile_from_chain(sub, d)
    if result is None:
        continue
    print(
        f"{str(expiry):<12} "
        f"{result['T_days']:>7.1f} "
        f"{result['n_strikes']:>8} "
        f"{result['sigma_atm']:>10.4f} "
        f"{result['alpha']:>+8.3f} "
        f"{result['beta_diagnostic']:>10.2f} "
        f"{result['residual_rmse']:>7.4f}"
    )