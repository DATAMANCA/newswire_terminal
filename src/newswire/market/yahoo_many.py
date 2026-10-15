"""Yahoo Finance news for many tickers at once, a few requests in parallel."""

import logging
from concurrent.futures import ThreadPoolExecutor

import feedparser

from .. import config, http_util
from ..models import NewsItem
from ..sources import yahoo_rss

logger = logging.getLogger("newswire.market.yahoo_many")


def fetch(tickers: list[str]) -> tuple[list[NewsItem], list[str], list[str]]:
    """Returns (items, tickers checked OK, tickers that failed)."""
    session = http_util.new_session(config.YAHOO_USER_AGENT)

    def one(ticker: str) -> tuple[str, list[NewsItem] | None]:
        try:
            response = http_util.get(session, yahoo_rss.FEED_URL.format(ticker=ticker))
            return ticker, yahoo_rss._parse_entries(ticker, feedparser.parse(response.content))
        except Exception as exc:  # noqa: BLE001 - one bad ticker mustn't stop the rest
            logger.warning("Yahoo fetch failed for %s: %s", ticker, exc)
            return ticker, None

    items: list[NewsItem] = []
    ok: list[str] = []
    failed: list[str] = []
    with ThreadPoolExecutor(config.MARKET_YAHOO_WORKERS) as pool:
        for ticker, result in pool.map(one, tickers):
            if result is None:
                failed.append(ticker)
            else:
                ok.append(ticker)
                items.extend(result)

    logger.info("Yahoo: %d tickers OK, %d failed, %d stories", len(ok), len(failed), len(items))
    return items, ok, failed
