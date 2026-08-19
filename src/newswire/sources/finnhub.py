import logging
import time
from datetime import datetime, timedelta, timezone

from .. import config, http_util
from ..models import NewsItem

logger = logging.getLogger("newswire.sources.finnhub")

NEWS_URL = "https://finnhub.io/api/v2/company-news"


def _parse_articles(ticker: str, articles: list[dict]) -> list[NewsItem]:
    items: list[NewsItem] = []
    for article in articles:
        uid = article.get("id")
        uid = str(uid) if uid is not None else article.get("url")
        if not uid:
            continue

        timestamp = article.get("datetime")
        published_at = (
            datetime.fromtimestamp(timestamp, tz=timezone.utc)
            if timestamp
            else datetime.now(timezone.utc)
        )

        items.append(
            NewsItem(
                source="FINNHUB",
                ticker=ticker,
                uid=uid,
                title=article.get("headline", "(untitled)"),
                url=article.get("url", ""),
                published_at=published_at,
                extra={"source_name": article.get("source", "")},
            )
        )
    return items


def fetch(tickers: list[str]) -> list[NewsItem]:
    if not config.FINNHUB_API_KEY:
        raise RuntimeError("FINNHUB_API_KEY is not set")

    session = http_util.new_session(config.EDGAR_USER_AGENT)
    today = datetime.now(timezone.utc).date()
    from_date = today - timedelta(days=config.FINNHUB_LOOKBACK_DAYS)

    all_items: list[NewsItem] = []
    for i, ticker in enumerate(tickers):
        if i > 0:
            time.sleep(config.FINNHUB_MIN_INTERVAL_SECONDS)
        try:
            response = http_util.get(
                session,
                NEWS_URL,
                params={
                    "symbol": ticker,
                    "from": from_date.isoformat(),
                    "to": today.isoformat(),
                    "token": config.FINNHUB_API_KEY,
                },
            )
            all_items.extend(_parse_articles(ticker, response.json()))
        except Exception:
            logger.exception("Finnhub fetch failed for ticker %s; skipping it.", ticker)
            continue

    return all_items
