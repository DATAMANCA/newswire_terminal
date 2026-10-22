import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest  # noqa: E402

from techwire import config, indicators as ind, prices, render, signals  # noqa: E402
from techwire.main import pick_mode, us_tickers  # noqa: E402
from techwire.models import BEARISH, BULLISH, Candles, Signal, StockResult  # noqa: E402


def _candles(closes, volumes=None, ticker="TEST"):
    start = date(2024, 1, 1)
    n = len(closes)
    return Candles(
        ticker,
        [start + timedelta(days=i) for i in range(n)],
        list(closes),
        [c * 1.01 for c in closes],
        [c * 0.99 for c in closes],
        list(closes),
        list(volumes or [1_000_000.0] * n),
    )


def _texts(sigs):
    return [s.text for s in sigs]


def _first_event(closes, predicate, start=60):
    """Analyse growing prefixes of `closes` and return the signals on the first
    day `predicate(signals)` is true."""
    for n in range(start, len(closes) + 1):
        _, sigs = signals.analyse(_candles(closes[:n]))
        if predicate(sigs):
            return sigs
    raise AssertionError("event never fired")


# ---- indicators ----

def test_sma_and_ema():
    assert ind.sma([1, 2, 3, 4], 2) == [None, 1.5, 2.5, 3.5]
    # seed = mean(1,2,3) = 2; next = 4*0.5 + 2*0.5 = 3
    assert ind.ema([1, 2, 3, 4], 3) == [None, None, 2.0, 3.0]


def test_rsi_extremes():
    assert ind.rsi(list(range(1, 30)), 14)[-1] == 100.0
    assert ind.rsi(list(range(30, 1, -1)), 14)[-1] == 0.0
    assert ind.rsi([5.0] * 30, 14)[-1] == 50.0


def test_rsi_wilder_smoothing_by_hand():
    # changes +1 -1 +1 +1, period 2: avg gain/loss 0.5/0.5 -> 50,
    # then 0.75/0.25 -> 75, then 0.875/0.125 -> 87.5
    assert ind.rsi([1, 2, 1, 2, 3], 2) == [None, None, 50.0, 75.0, 87.5]


def test_macd_flat_is_zero_and_bollinger_collapses():
    line, sig, hist = ind.macd([10.0] * 60, 12, 26, 9)
    assert line[-1] == pytest.approx(0) and sig[-1] == pytest.approx(0) and hist[-1] == pytest.approx(0)
    upper, mid, lower = ind.bollinger([10.0] * 30, 20, 2)
    assert upper[-1] == mid[-1] == lower[-1] == 10.0


def test_obv_and_pivots():
    assert ind.obv([1, 2, 2, 1], [10, 20, 30, 40]) == [0, 20, 20, -20]
    values = [5, 4, 3, 1, 3, 4, 5, 6, 7]
    assert ind.pivots(values, 3, "low") == [3]
    assert ind.pivots(values, 3, "high") == []


def test_stochastic_top_of_range():
    closes = [float(i) for i in range(1, 40)]
    k, d = ind.stochastic(closes, closes, closes, 14, 3, 3)
    assert k[-1] == pytest.approx(100) and d[-1] == pytest.approx(100)


# ---- signals ----

def _v_shape():
    down = [200 - i * 0.5 for i in range(220)]
    up = [down[-1] + i * 1.5 for i in range(1, 150)]
    return down + up


def test_golden_cross_fires_once():
    closes = _v_shape()
    sigs = _first_event(closes, lambda s: any("Golden cross" in t for t in _texts(s)), start=210)
    assert any(s.direction == BULLISH and "Golden cross" in s.text for s in sigs)


def test_price_crosses_50_day_average():
    sigs = _first_event(_v_shape(), lambda s: any("above its 50-day" in t for t in _texts(s)), start=210)
    assert any(s.group == "Trend" for s in sigs)


def test_rsi_oversold_entry():
    closes = [100.0 + (i % 2) for i in range(80)] + [100 - i * 2 for i in range(1, 20)]
    sigs = _first_event(closes, lambda s: any("RSI entered oversold" in t for t in _texts(s)), start=80)
    assert any(s.direction == BULLISH for s in sigs)


def test_new_52_week_high_and_volume_spike():
    closes = [100.0 + (i % 5) for i in range(300)] + [120.0]
    closes[250] = 110.0  # a clear swing high for resistance
    volumes = [1_000_000.0] * 300 + [3_500_000.0]
    _, sigs = signals.analyse(_candles(closes, volumes))
    texts = _texts(sigs)
    assert any("New 52-week high" in t for t in texts)
    assert any(t.startswith("Volume 3.5x") for t in texts)
    assert any("Broke above resistance" in t for t in texts)


def test_no_signals_on_a_quiet_flat_stock():
    closes = [100.0] * 300
    snap, sigs = signals.analyse(_candles(closes))
    assert [s for s in sigs if s.group != "Breakout"] == []
    assert snap.trend == "Mixed" and snap.change_pct == 0


def test_bullish_divergence_on_confirmed_lower_low():
    w = config.DIVERGENCE_PIVOT_WINDOW
    lows = [10, 9, 8, 7, 5, 7, 8, 9, 8, 7, 6, 4.5, 6, 7, 8]  # lows at 4 and 11
    highs = [v + 1 for v in lows]
    indicator = [50, 45, 40, 35, 20, 35, 40, 45, 42, 38, 34, 30, 40, 45, 50]  # higher low
    i = 11 + w
    found = signals._divergence(lows[: i + 1], highs[: i + 1], indicator[: i + 1], i)
    assert found and found[0] == BULLISH
    # One day later it's no longer "new", so it doesn't alert again.
    assert signals._divergence(lows, highs, indicator, i + 1) is None


def test_bearish_divergence_on_higher_high():
    highs = [1, 2, 3, 4, 6, 4, 3, 2, 3, 4, 5, 6.5, 5, 4, 3]
    lows = [v - 1 for v in highs]
    indicator = [50, 55, 60, 65, 80, 65, 60, 55, 58, 62, 66, 70, 60, 55, 50]  # lower high
    found = signals._divergence(lows, highs, indicator, 14)
    assert found and found[0] == BEARISH


def test_too_little_history_raises():
    with pytest.raises(ValueError):
        signals.analyse(_candles([1.0] * 10))


# ---- prices / main ----

def test_drop_unfinished_bar_during_market_hours():
    c = _candles([1.0, 2.0])
    c.dates[-1] = date(2026, 10, 22)
    open_now = datetime(2026, 10, 22, 17, 0, tzinfo=timezone.utc)  # 1pm New York
    assert len(prices.drop_unfinished(c, open_now)) == 1

    c = _candles([1.0, 2.0])
    c.dates[-1] = date(2026, 10, 22)
    after_close = datetime(2026, 10, 22, 21, 0, tzinfo=timezone.utc)  # 5pm New York
    assert len(prices.drop_unfinished(c, after_close)) == 2


def test_parse_daily_skips_missing_bars():
    payload = {"chart": {"result": [{
        "timestamp": [1792675800, 1792762200],
        "indicators": {"quote": [{
            "open": [1, None], "high": [2, None], "low": [0.5, None], "close": [1.5, None], "volume": [100, None],
        }]},
    }]}}
    c = prices.parse_daily("X", payload)
    assert c.closes == [1.5] and c.dates == [date(2026, 10, 22)]


def test_us_tickers_and_mode():
    assert us_tickers(["MSFT", "2408.TT", "SKHY", "285A.JP", "MU"]) == ["MSFT", "MU"]
    toronto = timezone(timedelta(hours=-4))
    assert pick_mode("auto", datetime(2026, 10, 22, 8, tzinfo=toronto)) == "morning"
    assert pick_mode("auto", datetime(2026, 10, 22, 17, tzinfo=toronto)) == "evening"
    assert pick_mode("auto", datetime(2026, 10, 22, 13, tzinfo=toronto)) is None
    assert pick_mode("morning", datetime(2026, 10, 22, 17, tzinfo=toronto)) == "morning"


# ---- render ----

def _results():
    snap, _ = signals.analyse(_candles([100.0 + i * 0.1 for i in range(300)]))
    flagged = StockResult("MSFT", ok=True, snapshot=snap, premarket_price=snap.close * 1.02, signals=[
        Signal("MSFT", "Trend", BULLISH, "Golden cross"),
        Signal("MSFT", "Momentum", BEARISH, "RSI entered overbought"),
    ])
    quiet = StockResult("MU", ok=True, snapshot=snap)
    broken = StockResult("EA", ok=False, error="only 1 days of history")
    return [flagged, quiet, broken]


def test_render_evening_and_morning():
    now = datetime(2026, 10, 22, 17, 5, tzinfo=timezone(timedelta(hours=-4)))
    subject, text, html = render.build("evening", _results(), now)
    assert subject.startswith("Technicals close 22 Oct: 2 signals on 1 stocks")
    assert "Golden cross" in html and "MU" in html and "Could not load: EA" in html
    assert "Pre-mkt" not in html

    subject, text, html = render.build("morning", _results(), now)
    assert subject.startswith("Technicals pre-market")
    assert "Pre-mkt" in html and "+2.0%" in html
    assert "pre-market +2.0%" in text


def test_render_quiet_day_still_has_table():
    snap, _ = signals.analyse(_candles([100.0] * 300))
    subject, _, html = render.build("evening", [StockResult("MU", ok=True, snapshot=snap)], datetime.now())
    assert subject.endswith("no new signals")
    assert "All stocks" in html and "MU" in html
