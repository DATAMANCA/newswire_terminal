"""The list of US-listed, US-based common stocks above the market-cap floor."""

import csv
import logging
import re
from dataclasses import dataclass

from .. import config, http_util

logger = logging.getLogger("newswire.market.universe")

SCREENER_URL = "https://api.nasdaq.com/api/screener/stocks?tableonly=true&limit=10000&download=true"

# Securities that aren't ordinary shares: bonds, preferreds, warrants, rights, units.
_NOT_COMMON = re.compile(
    r"\bnotes?\b|\bbonds?\b|debentures?|\bstrats\b|preferred|\bpref\b|depositary|warrants?|\brights?\b"
    r"|tangible equity|\bunits?\b(?! representing)|trust preferred|capital trust|perpetual",
    re.IGNORECASE,
)
_COMMON_UNITS = re.compile(r"common units|units representing", re.IGNORECASE)
# Blank-cheque companies (SPACs).
_SPAC = re.compile(r"acquisition corp|acquisition co\b|acquisition inc|acquisition ltd", re.IGNORECASE)
# Closed-end funds, interval funds and royalty/grantor trusts.
_FUND = re.compile(
    r"\bfund\b|\bfunds\b|income trust|term trust|municipal|royalty trust|opportunities trust"
    r"|strategic trust|dividend trust|equity trust|credit trust|bond trust|\betf\b",
    re.IGNORECASE,
)
_FUND_INDUSTRIES = {"Trusts Except Educational Religious and Charitable", "Blank Checks"}

# Nasdaq's sector names, tidied for email subjects.
SECTOR_NAMES = {
    "Finance": "Finance",
    "Consumer Discretionary": "Consumer Discretionary",
    "Health Care": "Health Care",
    "Industrials": "Industrials",
    "Technology": "Technology",
    "Real Estate": "Real Estate",
    "Utilities": "Utilities",
    "Energy": "Energy",
    "Consumer Staples": "Consumer Staples",
    "Telecommunications": "Telecommunications",
    "Basic Materials": "Basic Materials",
}
OTHER_SECTOR = "Other"


@dataclass
class Company:
    ticker: str
    name: str
    sector: str
    market_cap: float

    @property
    def is_large(self) -> bool:
        return self.market_cap >= config.MARKET_LARGE_CAP


def _market_cap(row: dict) -> float:
    try:
        return float(row.get("marketCap") or 0)
    except ValueError:
        return 0.0


def exclusion_reason(row: dict) -> str | None:
    """Why a screener row is left out of the list, or None to keep it."""
    name = (row.get("name") or "").strip()
    industry = (row.get("industry") or "").strip()
    if (row.get("country") or "") != "United States":
        return "not US-based"
    if _market_cap(row) < config.MARKET_MIN_CAP:
        return "below market-cap floor"
    if "^" in row.get("symbol", ""):
        return "not common stock"
    if _NOT_COMMON.search(name) and not _COMMON_UNITS.search(name):
        return "not common stock"
    if _SPAC.search(name) or industry == "Blank Checks":
        return "SPAC"
    if industry == "Real Estate Investment Trusts":
        return None
    if _FUND.search(name) or industry in _FUND_INDUSTRIES:
        return "fund or trust"
    return None


def build(rows: list[dict], exclude: set[str]) -> list[Company]:
    companies: list[Company] = []
    for row in rows:
        if exclusion_reason(row):
            continue
        # Nasdaq writes class shares as BRK/B; SEC and Yahoo use BRK-B.
        ticker = row["symbol"].strip().upper().replace("/", "-")
        if ticker in exclude:
            continue
        sector = SECTOR_NAMES.get((row.get("sector") or "").strip(), OTHER_SECTOR)
        companies.append(Company(ticker, (row.get("name") or "").strip(), sector, _market_cap(row)))
    companies.sort(key=lambda c: c.market_cap, reverse=True)
    return companies


def download_rows() -> list[dict]:
    session = http_util.new_session(config.YAHOO_USER_AGENT)
    session.headers["Accept"] = "application/json"
    response = http_util.get(session, SCREENER_URL, timeout=60)
    return response.json()["data"]["rows"]


def save(companies: list[Company]) -> None:
    with config.MARKET_UNIVERSE_PATH.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["ticker", "name", "sector", "market_cap"])
        for c in companies:
            writer.writerow([c.ticker, c.name, c.sector, f"{c.market_cap:.0f}"])


def load() -> list[Company]:
    with config.MARKET_UNIVERSE_PATH.open(encoding="utf-8", newline="") as f:
        return [
            Company(r["ticker"], r["name"], r["sector"], float(r["market_cap"]))
            for r in csv.DictReader(f)
        ]


def refresh(exclude: set[str]) -> list[Company]:
    companies = build(download_rows(), exclude)
    if len(companies) < 1000:
        raise RuntimeError(f"Stock list looks wrong ({len(companies)} companies); keeping the old one.")
    save(companies)
    logger.info("Saved %d companies to %s", len(companies), config.MARKET_UNIVERSE_PATH.name)
    return companies


if __name__ == "__main__":
    from .. import watchlist

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    refresh(set(watchlist.load_watchlist(config.WATCHLIST_PATH)))
