import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest  # noqa: E402

from newswire.market.universe import Company  # noqa: E402
from scanwire import config, render, scan, state  # noqa: E402
from techwire.models import Candles  # noqa: E402

ACME = Company("ACME", "Acme Corp Common Stock", "Industrials", 4_200_000_000)


def _candles(closes, volume=1_000_000.0):
    start = date(2024, 1, 1)
    n = len(closes)
    return Candles(
        "ACME", [start + timedelta(days=i) for i in range(n)],
        list(closes), list(closes), list(closes), list(closes), [volume] * n,
    )


# ---- scan.check ----

def test_flat_price_sits_on_the_ema():
    out = scan.check(ACME, _candles([50.0] * 300))
    assert out.reason == scan.HIT
    assert out.hit.distance_pct == pytest.approx(0, abs=1e-9)
    assert out.hit.days_in_band == 101  # EMA exists from bar 200 onwards
    assert out.hit.slope_pct == pytest.approx(0, abs=1e-9)


def test_band_edges():
    assert scan.check(ACME, _candles([50.0] * 299 + [50.49])).reason == scan.HIT
    assert scan.check(ACME, _candles([50.0] * 299 + [49.51])).reason == scan.HIT
    assert scan.check(ACME, _candles([50.0] * 299 + [51.0])).reason == scan.OUTSIDE
    assert scan.check(ACME, _candles([50.0] * 299 + [49.0])).reason == scan.OUTSIDE


def test_filters():
    assert scan.check(ACME, _candles([4.0] * 300)).reason == scan.LOW_PRICE
    assert scan.check(ACME, _candles([50.0] * 300, volume=400_000)).reason == scan.LOW_VOLUME
    assert scan.check(ACME, _candles([50.0] * 150)).reason == scan.SHORT_HISTORY


def test_came_from_above_and_days_in_band():
    # Well above the EMA, then drops back onto it for the last 3 days.
    closes = [50.0] * 280 + [56.0] * 17 + [51.0] * 3
    hit = scan.check(ACME, _candles(closes)).hit
    assert hit.came_from == "above"
    assert hit.days_in_band == 3
    assert hit.slope_pct > 0


def test_came_from_below():
    closes = [50.0] * 280 + [45.0] * 17 + [49.6] * 3
    hit = scan.check(ACME, _candles(closes)).hit
    assert hit.came_from == "below"
    assert hit.slope_pct < 0


# ---- state ----

def test_previous_list_and_record(monkeypatch):
    monkeypatch.setattr(config, "STATE_DAYS_KEPT", 2)
    assert state.previous_list({}, "2026-10-26") is None
    data = state.record({}, "2026-10-22", ["B", "A"])
    data = state.record(data, "2026-10-23", ["C"])
    data = state.record(data, "2026-10-26", ["D"])
    assert data["last_close"] == "2026-10-26"
    assert list(data["lists"]) == ["2026-10-23", "2026-10-26"]
    assert state.previous_list(data, "2026-10-26") == {"C"}
    # Re-running for the same close compares against the day before, not itself.
    assert state.previous_list(data, "2026-10-26") != {"D"}


# ---- render ----

def _hit(ticker, sector, distance, new=False):
    company = Company(ticker, f"{ticker} Inc. Common Stock", sector, 1_500_000_000)
    return scan.Hit(company, date(2026, 10, 23), 100.0, 100.0, distance, "above", 1.2, 2, new)


def test_by_sector_orders_sectors_and_rows():
    hits = [_hit("A", "Tech", 0.9), _hit("B", "Tech", -0.1), _hit("C", "Energy", 0.5)]
    groups = render.by_sector(hits)
    assert [s for s, _ in groups] == ["Tech", "Energy"]
    assert [h.company.ticker for h in groups[0][1]] == ["B", "A"]


def test_build_email():
    hits = [_hit("A", "Tech", 0.9, new=True), _hit("B", "Tech", -0.1)]
    outcomes = [scan.Outcome("A", scan.HIT), scan.Outcome("B", scan.HIT), scan.Outcome("X", scan.FAILED)]
    subject, text, html = render.build(hits, outcomes, date(2026, 10, 23), first_run=False)
    assert subject == "200 EMA scan Fri 23 Oct: 2 stocks within ±1% (1 new)"
    assert "NEW A" in text and "Could not load: X" in text
    assert "1 just above, 1 just below" in text
    assert ">NEW<" in html and "A Inc." in html and "Common Stock" not in html


def test_labels():
    assert render.money(4.2e9) == "$4.2B"
    assert render.money(350e6) == "$350M"
    assert render.slope_label(1.23) == "Rising +1.2%"
    assert render.slope_label(-0.1) == "Flat -0.1%"
    assert render.slope_label(None) == "n/a"
    assert render.came_from_label("below") == "↑ from below"
