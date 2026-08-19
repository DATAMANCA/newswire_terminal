import logging
import time
from datetime import datetime, timezone

import feedparser

from .. import config, http_util
from ..models import NewsItem

logger = logging.getLogger("newswire.sources.yahoo_rss")

FEED_URL = "https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US"


def _parse_entries(ticker: str, feed) -> list[NewsItem]:
    items: list[NewsItem] = []
    for entry in feed.entries:
        uid = entry.get("guid") or entry.get("id") or entry.get("link")
        if not uid:
            continue

        if getattr(entry, "published_parsed", None):
            published_at = datetime.fromtimestamp(
                time.mktime(entry.published_parsed), tz=timezone.utc
            )
        else:
            published_at = datetime.now(timezone.utc)

        items.append(
            NewsItem(
                source="YAHOO",
                ticker=ticker,
                uid=uid,
                title=entry.get("title", "(untitled)"),
                url=entry.get("link", ""),
                published_at=published_at,
            )
        )
    return items


def fetch(tickers: list[str]) -> list[NewsItem]:
    session = http_util.new_session(config.YAHOO_USER_AGENT)

    all_items: list[NewsItem] = []
    for i, ticker in enumerate(tickers):
        if i > 0:
            time.sleep(config.YAHOO_MIN_INTERVAL_SECONDS)
        try:
            response = http_util.get(session, FEED_URL.format(ticker=ticker))
            feed = feedparser.parse(response.content)
            all_items.extend(_parse_entries(ticker, feed))
        except Exception:
            logger.exception("Yahoo RSS fetch failed for ticker %s; skipping it.", ticker)
            continue

    return all_items
