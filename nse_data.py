"""
NSE Derivatives Pricelist parser.

Downloads the newest Derivatives_Pricelist_DD-MON-YYYY.pdf from the NSE
Data Services directory and parses:

  • Page 1  — Futures MTM prices (front contract per underlying)
  • Pages 2+ — Options chain (indicative Black-76, one vol per name)

Values in the options chain are quoted in cents and must be divided by 100.
"""
from __future__ import annotations
import io
import logging
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict, List, Optional

import requests

try:
    import pdfplumber
except ImportError:
    pdfplumber = None

from config import (
    NSE_PRICELIST_BASE_URL,
    NSE_PRICELIST_FILENAME,
    NSE_PRICELIST_LOOKBACK_DAYS,
)

log = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}

_MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN",
           "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]

_CENTS = 100.0

# ---------------------------------------------------------------------------
# Regexes
# ---------------------------------------------------------------------------
# "SCOM — Safaricom Plc | Underlying future MTM 36.32 | 252-day vol 21.76% | ..."
_HEADER_RE = re.compile(
    r"^([A-Z]{2,6})\s+[—\-–]\s+(.+?)\s*\|\s*"
    r"Underlying future MTM\s+([\d,]+\.?\d*)\s*\|\s*"
    r"252-day vol\s+([\d.]+)\s*%",
    re.MULTILINE,
)

# Futures section header: "SINGLE STOCK FUTURE (SCOM)" or "INDEX (N25I)"
_FUTURES_SECTION_RE = re.compile(
    r"^(SINGLE STOCK FUTURE|INDEX)\s*\(([A-Z0-9]+)\)\s*$"
)

# Futures data row:
#   17-Dec-26 KE9900003980 December 19, 2025 December 17, 2026 69 36.32 3 6.32 4 ,630
_FUTURES_ROW_RE = re.compile(
    r"^(\d{1,2}-[A-Za-z]{3}-\d{2})\s+"          # contract code
    r"(KE\w+)\s+"                                 # ISIN
    r"([A-Za-z]+ \d{1,2}, \d{4})\s+"             # listing date
    r"([A-Za-z]+ \d{1,2}, \d{4})\s+"             # expiry date
    r"(\d+)\s+"                                   # days to expiry
    r"([\d,]+\.\d+)"                              # MTM price
)

# Options ladder row: 6 values, space-separated
#   6 532 538 31.00 6 0 6
_LADDER_ROW_RE = re.compile(
    r"^([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+([\d.]+)\s+"
    r"([\d,]+)\s+([\d,]+)\s+([\d,]+)\s*$"
)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------
@dataclass
class FuturesRow:
    underlying: str
    contract_code: str
    isin: str
    listing_date: str
    expiry_date: str
    days_to_expiry: int
    mtm_price: float


@dataclass
class StrikeRow:
    strike: float
    call_extr: float
    call_intr: float
    call_prem: float
    put_prem: float
    put_intr: float
    put_extr: float


@dataclass
class OptionChain:
    underlying: str
    name: str
    F: float
    sigma_atm: float
    expiry_label: str
    days_to_expiry: int
    strikes: List[StrikeRow] = field(default_factory=list)


@dataclass
class PricelistSnapshot:
    as_of: str
    pdf_url: str
    futures: Dict[str, FuturesRow] = field(default_factory=dict)
    chains: Dict[str, OptionChain] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------
def _candidate_urls() -> List[str]:
    today = date.today()
    out = []
    for back in range(NSE_PRICELIST_LOOKBACK_DAYS + 1):
        d = today - timedelta(days=back)
        name = NSE_PRICELIST_FILENAME.format(
            dd=f"{d.day:02d}",
            MON=_MONTHS[d.month - 1],
            YYYY=d.year,
        )
        out.append(NSE_PRICELIST_BASE_URL + name)
    return out


def fetch_latest_pricelist_bytes() -> tuple[str, bytes]:
    """Return (url, content) of the newest available PDF."""
    last_err = None
    for url in _candidate_urls():
        try:
            r = requests.get(url, headers=_HEADERS, timeout=30)
            if r.status_code == 200 and r.content[:4] == b"%PDF":
                log.info("Fetched pricelist: %s (%d bytes)", url, len(r.content))
                return url, r.content
        except Exception as e:
            last_err = e
    raise RuntimeError(
        f"No Derivatives_Pricelist PDF found in the last "
        f"{NSE_PRICELIST_LOOKBACK_DAYS} days. Last error: {last_err}"
    )


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------
def _clean_number(s: str) -> float:
    """Remove spaces and commas from a numeric string and parse it."""
    return float(s.replace(",", "").replace(" ", "").strip())


def _parse_futures(pages_text: List[str]) -> Dict[str, FuturesRow]:
    """
    Parse page 1.  Track section headers like 'SINGLE STOCK FUTURE (SCOM)'
    and take the first (front) contract row per underlying.
    """
    futures: Dict[str, FuturesRow] = {}
    current_underlying: Optional[str] = None
    for page_text in pages_text:
        for raw in page_text.split("\n"):
            line = raw.strip()
            if not line:
                continue

            m = _FUTURES_SECTION_RE.match(line)
            if m:
                category, symbol = m.group(1), m.group(2)
                current_underlying = symbol
                continue

            if current_underlying is None:
                continue

            m = _FUTURES_ROW_RE.match(line)
            if m and current_underlying not in futures:
                futures[current_underlying] = FuturesRow(
                    underlying=current_underlying,
                    contract_code=m.group(1),
                    isin=m.group(2),
                    listing_date=m.group(3),
                    expiry_date=m.group(4),
                    days_to_expiry=int(m.group(5)),
                    mtm_price=_clean_number(m.group(6)),
                )
    return futures


def _parse_chains(full_text: str) -> Dict[str, OptionChain]:
    """
    Parse the OPTIONS CHAIN section.  Each chain is introduced by a header
    line of the form:

        SCOM — Safaricom Plc | Underlying future MTM 36.32 | 252-day vol 21.76% | 17 DEC 26 · 69 days

    followed by 7-column ladder rows until the next header.
    """
    chains: Dict[str, OptionChain] = {}
    current: Optional[OptionChain] = None

    for raw in full_text.split("\n"):
        line = raw.strip()
        if not line:
            continue

        m = _HEADER_RE.match(line)
        if m:
            underlying, name, F, sigma = m.groups()
            days_match = re.search(r"·\s*(\d+)\s+days", line)
            days = int(days_match.group(1)) if days_match else 0
            expiry_match = re.search(r"\|\s*(\d{1,2}\s+[A-Z]{3}\s+\d{2})\s*·", line)
            expiry_label = expiry_match.group(1) if expiry_match else ""
            current = OptionChain(
                underlying=underlying,
                name=name.strip(),
                F=_clean_number(F),
                sigma_atm=float(sigma) / 100.0,
                expiry_label=expiry_label,
                days_to_expiry=days,
            )
            chains[underlying] = current
            continue

        if current is None:
            continue

        m = _LADDER_ROW_RE.match(line)
        if m:
            try:
                current.strikes.append(StrikeRow(
                    strike=float(m.group(4)),
                    call_extr=_clean_number(m.group(1)) / _CENTS,
                    call_intr=_clean_number(m.group(2)) / _CENTS,
                    call_prem=_clean_number(m.group(3)) / _CENTS,
                    put_prem=_clean_number(m.group(5)) / _CENTS,
                    put_intr=_clean_number(m.group(6)) / _CENTS,
                    put_extr=_clean_number(m.group(7)) / _CENTS,
                ))
            except ValueError:
                continue

    return chains


def _parse_as_of_date(full_text: str) -> str:
    m = re.search(r"As at (\d{2} \w+ \d{4})", full_text)
    return m.group(1) if m else ""


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def load_pricelist() -> PricelistSnapshot:
    if pdfplumber is None:
        raise RuntimeError("pdfplumber not installed")

    url, content = fetch_latest_pricelist_bytes()

    with pdfplumber.open(io.BytesIO(content)) as pdf:
        pages_text = [p.extract_text() or "" for p in pdf.pages]
    full_text = "\n".join(pages_text)

    # Options section is pages 2+.  Futures section is page 1.
    futures = _parse_futures(pages_text[:1])
    chains = _parse_chains(full_text)
    as_of = _parse_as_of_date(full_text)

    return PricelistSnapshot(
        as_of=as_of,
        pdf_url=url,
        futures=futures,
        chains=chains,
    )