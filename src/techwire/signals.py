"""Turns a stock's daily candles into its snapshot row and the signals that
fired on the latest completed day. Every signal is an *event* (something that
changed between yesterday and today), so a stock sitting above its 200-day
average doesn't alert every day, only the day it crosses."""

from . import config, indicators as ind
from .models import BEARISH, BULLISH, NEUTRAL, Candles, Signal, Snapshot

MIN_BARS = 60


def _crossed_above(a, b, i: int) -> bool:
    vals = (a[i - 1], b[i - 1], a[i], b[i])
    return None not in vals and a[i - 1] <= b[i - 1] and a[i] > b[i]


def _crossed_below(a, b, i: int) -> bool:
    vals = (a[i - 1], b[i - 1], a[i], b[i])
    return None not in vals and a[i - 1] >= b[i - 1] and a[i] < b[i]


def _pct(a: float | None, b: float | None) -> float | None:
    if a is None or not b:
        return None
    return (a / b - 1) * 100


def _money(v: float) -> str:
    return f"${v:,.2f}"


def analyse(c: Candles) -> tuple[Snapshot, list[Signal]]:
    if len(c) < MIN_BARS:
        raise ValueError(f"only {len(c)} days of history for {c.ticker}")

    closes, highs, lows, volumes = c.closes, c.highs, c.lows, c.volumes
    i = len(closes) - 1
    t = c.ticker
    signals: list[Signal] = []

    def add(group: str, direction: str, text: str) -> None:
        signals.append(Signal(t, group, direction, text))

    # ---- Trend ----
    fast = ind.sma(closes, config.SMA_FAST)
    slow = ind.sma(closes, config.SMA_SLOW)
    nf, ns = config.SMA_FAST, config.SMA_SLOW
    if _crossed_above(fast, slow, i):
        add("Trend", BULLISH, f"Golden cross: {nf}-day average crossed above the {ns}-day")
    if _crossed_below(fast, slow, i):
        add("Trend", BEARISH, f"Death cross: {nf}-day average crossed below the {ns}-day")
    for avg, n in ((fast, nf), (slow, ns)):
        if _crossed_above(closes, avg, i):
            add("Trend", BULLISH, f"Closed above its {n}-day average ({_money(avg[i])})")
        if _crossed_below(closes, avg, i):
            add("Trend", BEARISH, f"Closed below its {n}-day average ({_money(avg[i])})")

    # ---- Momentum ----
    rsi = ind.rsi(closes, config.RSI_PERIOD)
    ob, os_ = [config.RSI_OVERBOUGHT] * len(closes), [config.RSI_OVERSOLD] * len(closes)
    if _crossed_above(rsi, ob, i):
        add("Momentum", BEARISH, f"RSI entered overbought ({rsi[i]:.0f} > {config.RSI_OVERBOUGHT}): pullback risk")
    if _crossed_below(rsi, ob, i):
        add("Momentum", BEARISH, f"RSI fell back below {config.RSI_OVERBOUGHT} ({rsi[i]:.0f}): momentum fading")
    if _crossed_below(rsi, os_, i):
        add("Momentum", BULLISH, f"RSI entered oversold ({rsi[i]:.0f} < {config.RSI_OVERSOLD}): bounce potential")
    if _crossed_above(rsi, os_, i):
        add("Momentum", BULLISH, f"RSI climbed back above {config.RSI_OVERSOLD} ({rsi[i]:.0f}): selling easing")

    macd_line, macd_sig, _ = ind.macd(closes, config.MACD_FAST, config.MACD_SLOW, config.MACD_SIGNAL)
    if _crossed_above(macd_line, macd_sig, i):
        zone = "below" if macd_line[i] < 0 else "above"
        add("Momentum", BULLISH, f"MACD crossed above its signal line ({zone} zero)")
    if _crossed_below(macd_line, macd_sig, i):
        zone = "above" if macd_line[i] > 0 else "below"
        add("Momentum", BEARISH, f"MACD crossed below its signal line ({zone} zero)")

    k, d = ind.stochastic(highs, lows, closes, config.STOCH_PERIOD, config.STOCH_SMOOTH, config.STOCH_SIGNAL)
    if _crossed_above(k, d, i) and k[i - 1] < config.STOCH_OVERSOLD:
        add("Momentum", BULLISH, f"Stochastic %K crossed above %D in oversold zone ({k[i]:.0f})")
    if _crossed_below(k, d, i) and k[i - 1] > config.STOCH_OVERBOUGHT:
        add("Momentum", BEARISH, f"Stochastic %K crossed below %D in overbought zone ({k[i]:.0f})")

    # ---- Breakouts ----
    yb = config.YEAR_BARS
    if i >= yb:
        prior_high = max(highs[i - yb + 1 : i])
        prior_low = min(lows[i - yb + 1 : i])
        if highs[i] > prior_high:
            add("Breakout", BULLISH, f"New 52-week high ({_money(highs[i])})")
        if lows[i] < prior_low:
            add("Breakout", BEARISH, f"New 52-week low ({_money(lows[i])})")

    upper, mid, lower = ind.bollinger(closes, config.BOLLINGER_PERIOD, config.BOLLINGER_STDDEV)
    if _crossed_above(closes, upper, i):
        add("Breakout", BULLISH, f"Closed above the upper Bollinger band ({_money(upper[i])}): strong, may be stretched")
    if _crossed_below(closes, lower, i):
        add("Breakout", BEARISH, f"Closed below the lower Bollinger band ({_money(lower[i])}): weak, may be stretched")

    width = [
        (u - l) / m if None not in (u, l, m) and m else None for u, l, m in zip(upper, lower, mid)
    ]

    def _is_squeeze(j: int) -> bool:
        window = width[j - config.SQUEEZE_LOOKBACK + 1 : j + 1]
        return j >= config.SQUEEZE_LOOKBACK and None not in window and width[j] <= min(window)

    if _is_squeeze(i) and not _is_squeeze(i - 1):
        add(
            "Breakout",
            NEUTRAL,
            f"Bollinger squeeze: bands at their narrowest in {config.SQUEEZE_LOOKBACK} days, a big move often follows",
        )

    start = max(0, i - config.LEVEL_LOOKBACK)
    win = config.SWING_WINDOW
    resistance = [highs[j] for j in ind.pivots(highs, win, "high") if j >= start]
    support = [lows[j] for j in ind.pivots(lows, win, "low") if j >= start]
    broken_up = [lv for lv in resistance if closes[i - 1] <= lv < closes[i]]
    broken_down = [lv for lv in support if closes[i - 1] >= lv > closes[i]]
    if broken_up:
        add("Breakout", BULLISH, f"Broke above resistance at {_money(max(broken_up))} (a recent swing high)")
    if broken_down:
        add("Breakout", BEARISH, f"Broke below support at {_money(min(broken_down))} (a recent swing low)")

    # ---- Volume ----
    vp = config.VOLUME_AVG_PERIOD
    if i >= vp:
        avg_vol = sum(volumes[i - vp : i]) / vp
        if avg_vol and volumes[i] >= config.VOLUME_SPIKE_MULTIPLE * avg_vol:
            move = _pct(closes[i], closes[i - 1]) or 0.0
            direction = BULLISH if move > 0 else BEARISH if move < 0 else NEUTRAL
            add("Volume", direction, f"Volume {volumes[i] / avg_vol:.1f}x its {vp}-day average on a {move:+.1f}% day")

    # ---- Divergences ----
    obv = ind.obv(closes, volumes)
    for name, series in (("RSI", rsi), ("MACD", macd_line), ("OBV", obv)):
        found = _divergence(lows, highs, series, i)
        if found:
            direction, text = found
            add("Divergence", direction, text.format(name=name))

    snap = Snapshot(
        ticker=t,
        as_of=c.dates[i],
        close=closes[i],
        change_pct=_pct(closes[i], closes[i - 1]),
        rsi=rsi[i],
        macd_above_signal=None if None in (macd_line[i], macd_sig[i]) else macd_line[i] > macd_sig[i],
        vs_sma_fast_pct=_pct(closes[i], fast[i]),
        vs_sma_slow_pct=_pct(closes[i], slow[i]),
        bollinger_pct_b=(
            (closes[i] - lower[i]) / (upper[i] - lower[i])
            if None not in (upper[i], lower[i]) and upper[i] != lower[i]
            else None
        ),
        stoch_k=k[i],
        from_year_high_pct=_pct(closes[i], max(highs[-yb:])),
        trend=_trend(closes[i], fast[i], slow[i]),
    )
    return snap, signals


def _trend(close: float, fast: float | None, slow: float | None) -> str:
    if fast is None or slow is None:
        return "Mixed"
    if close > fast > slow:
        return "Uptrend"
    if close < fast < slow:
        return "Downtrend"
    return "Mixed"


def _divergence(lows: list[float], highs: list[float], series, i: int) -> tuple[str, str] | None:
    """A divergence whose second swing point was confirmed today (so it alerts
    once). Bullish: price makes a lower low but the indicator a higher low.
    Bearish: price makes a higher high but the indicator a lower high."""
    w = config.DIVERGENCE_PIVOT_WINDOW
    start = i - config.DIVERGENCE_LOOKBACK
    newest = i - w

    for kind, prices in (("low", lows), ("high", highs)):
        points = [j for j in ind.pivots(prices, w, kind) if j >= start]
        if not points or points[-1] != newest:
            continue
        earlier = [j for j in points[:-1] if newest - j >= config.DIVERGENCE_MIN_GAP]
        if not earlier:
            continue
        a, b = earlier[-1], newest
        if series[a] is None or series[b] is None:
            continue
        if kind == "low" and prices[b] < prices[a] and series[b] > series[a]:
            return BULLISH, "Bullish {name} divergence: price made a lower low, {name} a higher low"
        if kind == "high" and prices[b] > prices[a] and series[b] < series[a]:
            return BEARISH, "Bearish {name} divergence: price made a higher high, {name} a lower high"
    return None
