import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bondwire import render  # noqa: E402
from bondwire.models import FetchResult, YieldPoint  # noqa: E402


def _pt(country, tenor, y, chg):
    return YieldPoint(country, tenor, y, chg, "12:00", "CNBC")


POINTS = [
    _pt("US", "2Y", 4.36, 1.2),
    _pt("US", "10Y", 4.76, 6.0),
    _pt("US", "30Y", 5.24, 4.0),
    _pt("DE", "2Y", 2.93, 1.0),
    _pt("DE", "10Y", 3.33, -2.0),
    _pt("DE", "30Y", 3.81, -0.4),
    _pt("IT", "10Y", 4.17, 0.2),
    _pt("FR", "10Y", 4.19, 1.2),
    _pt("JP", "10Y", 2.99, -3.0),
    _pt("EA", "10Y", 3.34, 6.1),
]
RESULTS = {
    "CNBC": FetchResult("CNBC", ok=True, points=POINTS),
    "Treasury": FetchResult("Treasury", ok=False, points=[], error="timeout"),
}


def test_build_has_table_spreads_and_context():
    subject, text, html = render.build(POINTS, [], RESULTS, {"yields": {}, "sent_at_utc": None})

    assert "US10Y 4.76%" in subject
    # BTP-Bund = IT10Y - DE10Y = (4.17 - 3.33) * 100 = 84.0 bp
    assert "84.0 bp" in html
    # UST-Bund = (4.76 - 3.33) * 100 = 143.0 bp
    assert "143.0 bp" in html
    # US 2s10s = (4.76 - 4.36) * 100 = 40 bp
    assert "+40 bp" in html
    # biggest 10Y mover is US +6.0 bp
    assert "Biggest 10Y move" in html and "United States" in html
    # failed source surfaced
    assert "Source failures this run" in html and "Treasury" in html
    assert "Euro area (AAA)" in html


def test_since_last_email_section():
    prev = {
        "sent_at_utc": "2000-01-01T00:00:00+00:00",
        "yields": {"US|10Y": 4.70, "DE|10Y": 3.33},
    }
    _, text, html = render.build(POINTS, [], RESULTS, prev)
    assert "Since last email" in html
    assert "4.700 → 4.760" in html          # US 10Y moved, shown
    assert "DE" not in html.split("Since last email")[1][:400] or "3.330 → 3.330" not in html


def test_inverted_curve_flagged():
    pts = [_pt("US", "2Y", 4.90, 0.0), _pt("US", "10Y", 4.60, 0.0)]
    _, text, html = render.build(pts, [], {"CNBC": FetchResult("CNBC", True, pts)}, {})
    assert "Inverted 2s10s" in html and "United States" in html
