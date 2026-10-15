"""Important SEC filings for the whole list, from EDGAR's "latest filings" feed.

One feed covers every company, so a run needs a few requests per form type
instead of one per company.
"""

import logging
import re
from datetime import datetime, timedelta, timezone

import feedparser

from .. import cik_cache, config, http_util
from ..models import NewsItem

logger = logging.getLogger("newswire.market.sec_current")

FEED_URL = "https://www.sec.gov/cgi-bin/browse-edgar"
PAGE_SIZE = 100

# "8-K - Empery Digital Inc. (0001829794) (Filer)"
_TITLE = re.compile(r"^(?P<form>.+?) - (?P<name>.+) \((?P<cik>\d{10})\) \((?P<role>[^)]+)\)$")
# "Item 2.02: Results of Operations and Financial Condition"
_ITEM = re.compile(r"Item (\d+\.\d+):\s*([^<]+)")
_FILED = re.compile(r"Filed:</b>\s*(\d{4}-\d{2}-\d{2})")

# 8-K items that are paperwork rather than news.
_SKIP_ITEMS = {"9.01"}


def _cik_to_ticker(tickers: set[str]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for ticker, cik in cik_cache.get_cik_map().items():
        if ticker in tickers and cik not in mapping:
            mapping[cik] = ticker
    return mapping


def _wanted_role(form: str) -> str:
    # For ownership reports the company the stake is in is the "Subject";
    # the "Filed by" entry is the investor.
    return "Subject" if "13D" in form.upper() else "Filer"


def _investor(entry) -> tuple[str, str] | None:
    """(accession, investor name) for the "Filed by" side of a 13D."""
    match = _TITLE.match(entry.get("title", ""))
    if not match or match["role"] != "Filed by":
        return None
    return entry.get("id", "").rsplit("=", 1)[-1], match["name"].strip()


def parse_entry(entry, cik_to_ticker: dict[str, str]) -> NewsItem | None:
    match = _TITLE.match(entry.get("title", ""))
    if not match:
        return None
    form = match["form"].strip()
    if match["role"] != _wanted_role(form):
        return None
    ticker = cik_to_ticker.get(match["cik"])
    if not ticker:
        return None

    summary = entry.get("summary", "")
    items = [
        (number, text.strip())
        for number, text in _ITEM.findall(summary)
        if number not in _SKIP_ITEMS
    ]
    accession = entry.get("id", "").rsplit("=", 1)[-1] or entry.get("link", "")

    updated = entry.get("updated_parsed")
    if updated:
        published_at = datetime(*updated[:6], tzinfo=timezone.utc)
    else:
        filed = _FILED.search(summary)
        published_at = (
            datetime.fromisoformat(filed[1]).replace(tzinfo=timezone.utc)
            if filed
            else datetime.now(timezone.utc)
        )

    return NewsItem(
        source="EDGAR",
        ticker=ticker,
        uid=accession,
        title=f"{ticker} filed {form}",
        url=entry.get("link", ""),
        published_at=published_at,
        extra={"form": form, "items": [text for _, text in items], "company": match["name"]},
    )


def fetch(tickers: set[str], since: datetime) -> list[NewsItem]:
    """Filings by companies in `tickers` for the configured forms, newest
    first, paging back until filings are older than `since`."""
    cik_to_ticker = _cik_to_ticker(tickers)
    session = http_util.new_session(config.EDGAR_USER_AGENT)

    found: dict[str, NewsItem] = {}
    filed_by: dict[str, str] = {}  # accession -> investor name, for 13D stake reports
    for form in config.MARKET_SEC_FORMS:
        for page in range(config.MARKET_SEC_MAX_PAGES):
            params = {
                "action": "getcurrent", "type": form, "owner": "include",
                "count": PAGE_SIZE, "start": page * PAGE_SIZE, "output": "atom",
            }
            response = http_util.get(session, FEED_URL, params=params)
            feed = feedparser.parse(response.content)
            if not feed.entries:
                break
            for entry in feed.entries:
                investor = _investor(entry)
                if investor:
                    filed_by[investor[0]] = investor[1]
                item = parse_entry(entry, cik_to_ticker)
                if item and item.uid not in found:
                    found[item.uid] = item
            oldest = feed.entries[-1].get("updated_parsed")
            if oldest and datetime(*oldest[:6], tzinfo=timezone.utc) < since:
                break
            if len(feed.entries) < PAGE_SIZE:
                break

    for uid, item in found.items():
        if uid in filed_by:
            item.extra["filed_by"] = filed_by[uid]

    logger.info("SEC latest filings: %d for companies on the list", len(found))
    return list(found.values())


def default_since(last_run_utc: str | None) -> datetime:
    """Page back to a little before the previous run (or 2 days on a first run)."""
    if last_run_utc:
        return datetime.fromisoformat(last_run_utc) - timedelta(hours=2)
    return datetime.now(timezone.utc) - timedelta(days=2)
