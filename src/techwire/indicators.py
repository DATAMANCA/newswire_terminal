"""Indicator maths on plain lists. Each function returns a list the same length
as its input, with None where there isn't enough history yet."""

from statistics import pstdev

Series = list[float | None]


def sma(values: Series, period: int) -> Series:
    out: Series = [None] * len(values)
    for i in range(period - 1, len(values)):
        window = values[i - period + 1 : i + 1]
        if None not in window:
            out[i] = sum(window) / period
    return out


def ema(values: Series, period: int) -> Series:
    """Seeded with the simple average of the first `period` values."""
    out: Series = [None] * len(values)
    start = next((i for i, v in enumerate(values) if v is not None), None)
    if start is None or len(values) - start < period:
        return out
    seed = start + period - 1
    out[seed] = sum(values[start : seed + 1]) / period
    k = 2 / (period + 1)
    for i in range(seed + 1, len(values)):
        out[i] = values[i] * k + out[i - 1] * (1 - k)
    return out


def rsi(closes: list[float], period: int) -> Series:
    """Wilder's RSI."""
    out: Series = [None] * len(closes)
    if len(closes) <= period:
        return out
    gains = [max(closes[i] - closes[i - 1], 0) for i in range(1, len(closes))]
    losses = [max(closes[i - 1] - closes[i], 0) for i in range(1, len(closes))]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    def _value(g: float, l: float) -> float:
        if l == 0:
            return 100.0 if g > 0 else 50.0
        return 100 - 100 / (1 + g / l)

    out[period] = _value(avg_gain, avg_loss)
    for i in range(period + 1, len(closes)):
        avg_gain = (avg_gain * (period - 1) + gains[i - 1]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i - 1]) / period
        out[i] = _value(avg_gain, avg_loss)
    return out


def macd(closes: list[float], fast: int, slow: int, signal: int) -> tuple[Series, Series, Series]:
    """(MACD line, signal line, histogram)."""
    fast_ema, slow_ema = ema(closes, fast), ema(closes, slow)
    line: Series = [
        f - s if f is not None and s is not None else None for f, s in zip(fast_ema, slow_ema)
    ]
    sig = ema(line, signal)
    hist: Series = [
        m - s if m is not None and s is not None else None for m, s in zip(line, sig)
    ]
    return line, sig, hist


def bollinger(closes: list[float], period: int, stddev: float) -> tuple[Series, Series, Series]:
    """(upper, middle, lower)."""
    mid = sma(closes, period)
    upper: Series = [None] * len(closes)
    lower: Series = [None] * len(closes)
    for i in range(period - 1, len(closes)):
        sd = pstdev(closes[i - period + 1 : i + 1])
        upper[i] = mid[i] + stddev * sd
        lower[i] = mid[i] - stddev * sd
    return upper, mid, lower


def stochastic(
    highs: list[float], lows: list[float], closes: list[float], period: int, smooth: int, signal: int
) -> tuple[Series, Series]:
    """Slow stochastic: (%K, %D)."""
    raw: Series = [None] * len(closes)
    for i in range(period - 1, len(closes)):
        hh = max(highs[i - period + 1 : i + 1])
        ll = min(lows[i - period + 1 : i + 1])
        raw[i] = 50.0 if hh == ll else (closes[i] - ll) / (hh - ll) * 100
    k = sma(raw, smooth)
    d = sma(k, signal)
    return k, d


def obv(closes: list[float], volumes: list[float]) -> list[float]:
    out = [0.0] * len(closes)
    for i in range(1, len(closes)):
        if closes[i] > closes[i - 1]:
            out[i] = out[i - 1] + volumes[i]
        elif closes[i] < closes[i - 1]:
            out[i] = out[i - 1] - volumes[i]
        else:
            out[i] = out[i - 1]
    return out


def pivots(values: list[float], window: int, kind: str) -> list[int]:
    """Indexes of swing highs (kind="high") or lows (kind="low"): bars that are
    the strict extreme of `window` bars on each side. The last `window` bars
    can't be confirmed yet and are never returned."""
    found: list[int] = []
    for i in range(window, len(values) - window):
        left = values[i - window : i]
        right = values[i + 1 : i + window + 1]
        v = values[i]
        if kind == "high" and v > max(left) and v >= max(right):
            found.append(i)
        elif kind == "low" and v < min(left) and v <= min(right):
            found.append(i)
    return found
