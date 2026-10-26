"""Checks one stock's daily candles against the 200 EMA band."""

from dataclasses import dataclass
from datetime import date

from newswire.market.universe import Company
from techwire.indicators import ema
from techwire.models import Candles

from . import config

# Why a stock didn't make the list (keys of Outcome.reason).
HIT = "hit"
OUTSIDE = "outside band"
LOW_PRICE = "under $5"
LOW_VOLUME = "low volume"
SHORT_HISTORY = "under 200 days of history"
FAILED = "failed"


@dataclass
class Hit:
    company: Company
    as_of: date
    close: float
    ema: float
    distance_pct: float  # + above the EMA, - below
    came_from: str  # "above" / "below" / "" (not enough history)
    slope_pct: float | None
    days_in_band: int
    new: bool = False


@dataclass
class Outcome:
    ticker: str
    reason: str  # HIT / OUTSIDE / LOW_PRICE / LOW_VOLUME / SHORT_HISTORY / FAILED
    as_of: date | None = None
    hit: Hit | None = None
    error: str | None = None


def _pct(a: float, b: float) -> float:
    return (a / b - 1) * 100


def check(company: Company, c: Candles) -> Outcome:
    as_of = c.dates[-1] if c.dates else None
    if len(c) < config.EMA_PERIOD:
        return Outcome(company.ticker, SHORT_HISTORY, as_of)
    close = c.closes[-1]
    if close < config.MIN_PRICE:
        return Outcome(company.ticker, LOW_PRICE, as_of)
    recent_volume = c.volumes[-config.VOLUME_AVG_PERIOD :]
    if sum(recent_volume) / len(recent_volume) < config.MIN_AVG_VOLUME:
        return Outcome(company.ticker, LOW_VOLUME, as_of)

    line = ema(c.closes, config.EMA_PERIOD)
    distance = _pct(close, line[-1])
    if abs(distance) > config.BAND_PCT:
        return Outcome(company.ticker, OUTSIDE, as_of)

    days = 0
    for price, avg in zip(reversed(c.closes), reversed(line)):
        if avg is None or abs(_pct(price, avg)) > config.BAND_PCT:
            break
        days += 1

    back = -1 - config.DIRECTION_LOOKBACK
    came_from = ""
    if len(line) >= -back and line[back] is not None:
        came_from = "above" if c.closes[back] > line[back] else "below"

    slope_back = -1 - config.SLOPE_LOOKBACK
    slope = None
    if len(line) >= -slope_back and line[slope_back] is not None:
        slope = _pct(line[-1], line[slope_back])

    hit = Hit(company, as_of, close, line[-1], distance, came_from, slope, days)
    return Outcome(company.ticker, HIT, as_of, hit)
