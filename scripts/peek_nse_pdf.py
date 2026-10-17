"""
Download the newest NSE Derivatives Pricelist PDF and dump its contents.
"""
import io
import re
from datetime import date, timedelta
import requests
import pdfplumber

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}

MONTHS = ["JAN","FEB","MAR","APR","MAY","JUN","JUL","AUG","SEP","OCT","NOV","DEC"]

def try_download(back_days=7):
    today = date.today()
    for back in range(back_days + 1):
        d = today - timedelta(days=back)
        name = f"Derivatives_Pricelist_{d.day:02d}-{MONTHS[d.month-1]}-{d.year}.pdf"
        url = f"https://www.nse.co.ke/dataservices/wp-content/uploads/{name}"
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            if r.status_code == 200 and r.content[:4] == b"%PDF":
                print(f"FOUND: {url}  ({len(r.content)} bytes)")
                return url, r.content
        except Exception:
            pass
    return None, None

url, content = try_download()
if not url:
    print("No Derivatives_Pricelist PDF found in the last 7 days.")
    raise SystemExit(1)

print(f"\nDumping contents of {url}\n")

with pdfplumber.open(io.BytesIO(content)) as pdf:
    print(f"Pages: {len(pdf.pages)}")
    for i, page in enumerate(pdf.pages):
        print(f"\n--- PAGE {i+1} ---")
        txt = page.extract_text() or ""
        print(txt)

        tables = page.extract_tables() or []
        print(f"\n(extracted {len(tables)} tables on this page)")
        for ti, t in enumerate(tables):
            print(f"\n  Table {ti}: {len(t)} rows")
            for r in t[:8]:
                print(f"    {r}")