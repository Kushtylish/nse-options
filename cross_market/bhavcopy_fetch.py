"""
NSE India Bhavcopy fetcher.

Downloads the daily F&O archive (a ZIP containing one CSV) and extracts
Nifty index options. Bhavcopy has EOD close prices, open interest, and
volume — enough to fit a smile.
"""
import io
import zipfile
from datetime import date, timedelta

import pandas as pd
import requests

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Referer": "https://www.nseindia.com/all-reports",
}


def fetch_bhavcopy(target_date: date):
    """Download one day's bhavcopy as a DataFrame, or None if unavailable."""
    ds = target_date.strftime("%Y%m%d")
    url = (
        "https://nsearchives.nseindia.com/content/fo/"
        f"BhavCopy_NSE_FO_0_0_0_{ds}_F_0000.csv.zip"
    )
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        if r.status_code != 200:
            return None
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            name = z.namelist()[0]
            with z.open(name) as f:
                return pd.read_csv(f)
    except Exception:
        return None


def fetch_latest_bhavcopy(max_lookback=12):
    """Find the most recent trading day with a downloadable bhavcopy."""
    today = date.today()
    for i in range(1, max_lookback + 1):
        d = today - timedelta(days=i)
        df = fetch_bhavcopy(d)
        if df is not None:
            return df, d
    return None, None


def nifty_options(df, min_volume=100, min_oi=500):
    """Filter a bhavcopy DataFrame to liquid Nifty index options."""
    d = df[df["TckrSymb"] == "NIFTY"].copy()
    if d.empty:
        d = df[df["FinInstrmTp"] == "IDO"].copy()
    d = d[d["OptnTp"].isin(["CE", "PE"])]
    d = d[d["ClsPric"] > 0]
    d = d[d["TtlTradgVol"] >= min_volume]
    d = d[d["OpnIntrst"] >= min_oi]
    return d