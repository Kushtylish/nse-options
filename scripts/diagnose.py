import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

URLS = [
    "https://www.nse.co.ke/derivatives/",
    "https://www.nse.co.ke/derivatives",
    "https://nse.co.ke/derivatives/",
    "https://www.nse.co.ke/",
    "https://www.centralbank.go.ke/bills-bonds/treasury-bills/",
]

for url in URLS:
    print(f"\n{'='*70}\nURL: {url}")
    try:
        r = requests.get(url, headers=HEADERS, timeout=20, allow_redirects=True)
        print(f"  Status: {r.status_code}")
        print(f"  Final URL: {r.url}")
        print(f"  Content-Type: {r.headers.get('Content-Type')}")
        print(f"  Length: {len(r.content)} bytes")

        if "html" in r.headers.get("Content-Type", "").lower():
            soup = BeautifulSoup(r.text, "html.parser")
            print(f"  <title>: {soup.title.string if soup.title else '(none)'}")

            tables = soup.find_all("table")
            print(f"  Tables found: {len(tables)}")
            for i, t in enumerate(tables[:3]):
                rows = t.find_all("tr")
                if rows:
                    headers = [c.get_text(strip=True) for c in rows[0].find_all(["th", "td"])]
                    print(f"    Table {i}: {len(rows)} rows, headers = {headers}")

            pdfs = [a["href"] for a in soup.find_all("a", href=True)
                    if a["href"].lower().endswith(".pdf")]
            print(f"  PDF links: {len(pdfs)}")
            for p in pdfs[:5]:
                print(f"    {p}")
    except Exception as e:
        print(f"  ERROR: {type(e).__name__}: {e}")