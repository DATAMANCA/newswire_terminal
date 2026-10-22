"""Daily candles and pre-market prices from Yahoo Finance's public chart API."""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import requests

from . import config, http_util
from .models import Candles

CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
_MARKET_TZ = ZoneInfo(config.MARKET_TIMEZONE)


def daily(session: requests.Session, ticker: str, now: datetime | None = None) -> Candles:
    """Completed daily candles, oldest first. Today's bar is dropped while the
    market is still open (or hasn't opened), since it isn't final yet."""
    response = http_util.get(
        session,
        CHART_URL.format(ticker=ticker),
        params={"range": config.HISTORY_RANGE, "interval": "1d"},
    )
    candles = parse_daily(ticker, response.json())
    return drop_unfinished(candles, now or datetime.now(timezone.utc))


def parse_daily(ticker: str, payload: dict) -> Candles:
    result = payload["chart"]["result"][0]
    quote = result["indicators"]["quote"][0]
    candles = Candles(ticker, [], [], [], [], [], [])
    for i, ts in enumerate(result.get("timestamp") or []):
        o, h, l, c, v = (quote[k][i] for k in ("open", "high", "low", "close", "volume"))
        if None in (o, h, l, c):
            continue  # halted / missing bar
        candles.dates.append(datetime.fromtimestamp(ts, _MARKET_TZ).date())
        candles.opens.append(float(o))
        candles.highs.append(float(h))
        candles.lows.append(float(l))
        candles.closes.append(float(c))
        candles.volumes.append(float(v or 0))
    if not candles.closes:
        raise ValueError(f"no price data for {ticker}")
    return candles


def drop_unfinished(candles: Candles, now: datetime) -> Candles:
    market_now = now.astimezone(_MARKET_TZ)
    if candles.dates and candles.dates[-1] == market_now.date() and market_now.hour < config.MARKET_CLOSE_HOUR:
        for series in (candles.dates, candles.opens, candles.highs, candles.lows, candles.closes, candles.volumes):
            series.pop()
    return candles


def premarket(session: requests.Session, ticker: str) -> float | None:
    """Latest pre-market trade today, or None if there hasn't been one."""
    response = http_util.get(
        session,
        CHART_URL.format(ticker=ticker),
        params={"range": "1d", "interval": "5m", "includePrePost": "true"},
    )
    result = response.json()["chart"]["result"][0]
    closes = result["indicators"]["quote"][0].get("close") or []
    today = datetime.now(_MARKET_TZ).date()
    for ts, price in reversed(list(zip(result.get("timestamp") or [], closes))):
        if price is not None and datetime.fromtimestamp(ts, _MARKET_TZ).date() == today:
            return float(price)
    return None
