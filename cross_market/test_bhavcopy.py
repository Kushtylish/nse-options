"""
Access test for NSE India's Bhavcopy archive.

The archives subdomain is more permissive than the live API — it serves
static daily files rather than dynamic responses.
"""
import requests
import zipfile
import io
import pandas as pd
from datetime import date, timedelta

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/all-reports",
}


def fetch_bhavcopy(target_date):
    date_str = target_date.strftime("%Y%m%d")
    url = (
        "https://nsearchives.nseindia.com/content/fo/"
        f"BhavCopy_NSE_FO_0_0_0_{date_str}_F_0000.csv.zip"
    )
    print(f"Trying {target_date} ...")
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        print(f"  status: {r.status_code}, size: {len(r.content)} bytes")
        if r.status_code != 200:
            return None
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            name = z.namelist()[0]
            print(f"  zip contents: {name}")
            with z.open(name) as f:
                df = pd.read_csv(f)
        print(f"  parsed: {df.shape[0]} rows x {df.shape[1]} cols")
        return df
    except Exception as e:
        print(f"  FAILED: {type(e).__name__}: {e}")
        return None


if __name__ == "__main__":
    today = date.today()
    for i in range(1, 12):
        d = today - timedelta(days=i)
        df = fetch_bhavcopy(d)
        if df is not None:
            print(f"\n{'=' * 60}")
            print(f"SUCCESS for {d}")
            print(f"{'=' * 60}")
            print(f"\nColumns ({len(df.columns)}):")
            for c in df.columns:
                print(f"  {c}")
            print(f"\nFirst 3 rows:")
            print(df.head(3).to_string())
            break
    else:
        print("\nFailed for all 11 recent dates.")