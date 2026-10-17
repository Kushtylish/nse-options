import requests
from bs4 import BeautifulSoup
import re
import json

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}

def dump_tables(url, label, max_tables=20, raw_rows=3):
    print("=" * 78)
    print(f"{label}\n{url}")
    print("=" * 78)
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        print(f"Status: {r.status_code}  Length: {len(r.content)}")
        soup = BeautifulSoup(r.text, "html.parser")
        tables = soup.find_all("table")
        print(f"Tables: {len(tables)}")
        for i, t in enumerate(tables[:max_tables]):
            rows = t.find_all("tr")
            print(f"\n  Table {i}: {len(rows)} rows")
            for j, row in enumerate(rows[:raw_rows]):
                cells = row.find_all(["th", "td"])
                vals = [c.get_text(strip=True)[:35] for c in cells]
                print(f"    Row {j} ({len(cells)} cells): {vals}")
            if rows:
                raw = str(rows[0])[:400]
                print(f"    Raw row 0: {raw}")
        # Find PDF / JSON / CSV / XHR hints in scripts
        print(f"\n  PDF/JSON/CSV links:")
        found = set()
        for a in soup.find_all("a", href=True):
            h = a["href"].lower()
            if any(h.endswith(ext) for ext in (".pdf", ".json", ".csv", ".xls", ".xlsx")):
                found.add(a["href"])
        for f in list(found)[:15]:
            print(f"    {f}")
        # DataTables / AJAX hints
        print(f"\n  AJAX/DataTables hints in inline scripts:")
        for s in soup.find_all("script"):
            txt = s.string or ""
            for pat in ["ajax", "dataSrc", "processing", "serverSide", "wp-json"]:
                if pat.lower() in txt.lower():
                    snippet = txt[max(0, txt.lower().find(pat.lower()) - 60):][:200]
                    print(f"    [{pat}] ...{snippet.strip()}...")
                    break
    except Exception as e:
        print(f"  ERROR: {type(e).__name__}: {e}")
    print()

# ---------------------------------------------------------------------------
# CBK probes
# ---------------------------------------------------------------------------
dump_tables("https://www.centralbank.go.ke/bills-bonds/treasury-bills/",
            "CBK T-Bills page — raw row structure")
dump_tables("https://www.centralbank.go.ke/books/money-in-kenya/",
            "CBK Money in Kenya — Key Rates")
dump_tables("https://www.centralbank.go.ke/",
            "CBK homepage — Key Rates widget")

# ---------------------------------------------------------------------------
# NSE probes — subpages
# ---------------------------------------------------------------------------
dump_tables("https://www.nse.co.ke/derivatives/single-stock-futures/",
            "NSE Single Stock Futures")
dump_tables("https://www.nse.co.ke/derivatives/options-on-futures/",
            "NSE Options on Futures")
dump_tables("https://www.nse.co.ke/derivatives/pl-calculator/",
            "NSE P&L Calculator")
dump_tables("https://www.nse.co.ke/dataservices/market-statistics/",
            "NSE Market Statistics")

# ---------------------------------------------------------------------------
# Try common JSON endpoints
# ---------------------------------------------------------------------------
print("=" * 78)
print("JSON endpoint probes")
print("=" * 78)
json_probes = [
    "https://www.centralbank.go.ke/bills-bonds/treasury-bills/?format=json",
    "https://www.centralbank.go.ke/wp-json/wp/v2/pages",
    "https://www.nse.co.ke/wp-json/wp/v2/pages?search=derivatives",
    "https://www.nse.co.ke/derivatives/wp-json/wp/v2/pages",
]
for u in json_probes:
    try:
        r = requests.get(u, headers=HEADERS, timeout=15)
        ctype = r.headers.get("Content-Type", "")
        print(f"  {r.status_code}  {ctype[:40]:40s}  {u}")
        if "json" in ctype and r.status_code < 400:
            try:
                data = r.json()
                print(f"      Keys: {list(data.keys())[:10] if isinstance(data, dict) else f'list len={len(data)}'}")
            except Exception:
                print(f"      (not parseable JSON)")
    except Exception as e:
        print(f"  ERR  {type(e).__name__}: {e}  {u}")