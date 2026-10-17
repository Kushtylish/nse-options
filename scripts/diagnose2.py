import requests
from bs4 import BeautifulSoup
import re
from datetime import date, timedelta

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}

# ---------------------------------------------------------------------------
# PART 1 — CBK: dump the actual table structure
# ---------------------------------------------------------------------------
print("=" * 78)
print("PART 1: CBK Treasury Bills HTML table structure")
print("=" * 78)
r = requests.get(
    "https://www.centralbank.go.ke/bills-bonds/treasury-bills/",
    headers=HEADERS, timeout=30,
)
soup = BeautifulSoup(r.text, "html.parser")
tables = soup.find_all("table")
print(f"Total tables: {len(tables)}")

for i, t in enumerate(tables):
    rows = t.find_all("tr")
    print(f"\n--- Table {i}: {len(rows)} rows ---")
    for j, row in enumerate(rows[:5]):
        cells = row.find_all(["th", "td"])
        vals = [c.get_text(strip=True)[:45] for c in cells]
        print(f"  Row {j}: {vals}")
    if len(rows) > 5:
        print(f"  ... ({len(rows) - 5} more rows)")

# ---------------------------------------------------------------------------
# PART 2 — NSE: probe direct PDF URL patterns
# ---------------------------------------------------------------------------
print("\n" + "=" * 78)
print("PART 2: NSE Derivatives Pricelist — direct URL probes")
print("=" * 78)
today = date.today()
MONTHS = ["JAN","FEB","MAR","APR","MAY","JUN","JUL","AUG","SEP","OCT","NOV","DEC"]

# Try several naming patterns for recent days
patterns = [
    "Derivatives_Pricelist_{d}-{mon}-{y}.pdf",
    "Derivatives-Pricelist-{d}-{mon}-{y}.pdf",
    "derivatives_pricelist_{d}-{mon}-{y}.pdf",
    "Derivatives_Pricelist_{y}-{mm}-{dd}.pdf",
]
found_any = False
for back in range(0, 14):  # last two weeks
    d = today - timedelta(days=back)
    for pat in patterns:
        fname = pat.format(
            d=f"{d.day:02d}",
            dd=f"{d.day:02d}",
            mon=MONTHS[d.month - 1],
            mm=f"{d.month:02d}",
            y=d.year,
        )
        url = f"https://www.nse.co.ke/wp-content/uploads/{fname}"
        try:
            r = requests.head(url, headers=HEADERS, timeout=10, allow_redirects=True)
            if r.status_code < 400:
                print(f"  ✓ {r.status_code}  {url}")
                found_any = True
        except Exception:
            pass

if not found_any:
    print("  No direct PDF URL pattern matched for the last 14 days.")

# ---------------------------------------------------------------------------
# PART 3 — NSE derivatives page: hunt for hidden data URLs
# ---------------------------------------------------------------------------
print("\n" + "=" * 78)
print("PART 3: NSE derivatives page — hidden data sources")
print("=" * 78)
r = requests.get("https://www.nse.co.ke/derivatives/", headers=HEADERS, timeout=30)
soup = BeautifulSoup(r.text, "html.parser")

print("\nAll <a> links on the derivatives page:")
for a in soup.find_all("a", href=True):
    txt = a.get_text(strip=True)[:50]
    href = a["href"]
    print(f"  {href[:90]:90s}  {txt}")

print("\nScripts referencing 'deriv', 'price', 'pdf', or 'json':")
for s in soup.find_all("script"):
    src = s.get("src", "")
    if any(k in src.lower() for k in ["deriv", "price", "pdf", "json"]):
        print(f"  SRC: {src}")
    text = s.string or ""
    if "deriv" in text.lower() or "pricelist" in text.lower():
        urls = re.findall(r'["\'](https?://[^"\']+|/[^"\']+\.(?:pdf|json|csv))["\']', text)
        for u in urls[:20]:
            print(f"  INLINE: {u}")

print("\nIframes on derivatives page:")
for i in soup.find_all("iframe"):
    print(f"  {i.get('src')}")