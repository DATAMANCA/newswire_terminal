import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bondwire.sources import cnbc  # noqa: E402
from bondwire.sources import official  # noqa: E402


# --------------------------------------------------------------------------- CNBC
CNBC_PAYLOAD = {
    "ITVQuoteResult": {
        "ITVQuote": [
            {
                "symbol": "US10Y",
                "last": "4.758%",
                "previous_day_closing": "4.738%",
                "change": "+0.020",
                "last_timedate": "10:27 AM EDT",
            },
            {
                "symbol": "US2Y",
                "last": "4.362%",
                "previous_day_closing": "4.350%",
                "last_timedate": "10:27 AM EDT",
            },
            {
                "symbol": "DE30Y-DE",
                "last": "3.8114%",
                "previous_day_closing": "3.8149%",
                "last_timedate": "4:27 PM CEST",
            },
            {"symbol": "JP10Y-JP", "last": "UNCH", "last_timedate": "x"},  # unusable
        ]
    }
}


def test_cnbc_symbol_scheme():
    assert cnbc.cnbc_symbol("US", "10Y") == "US10Y"
    assert cnbc.cnbc_symbol("DE", "2Y") == "DE2Y-DE"


def test_cnbc_parse_values_and_change_bp():
    wanted = {"US10Y": ("US", "10Y"), "US2Y": ("US", "2Y"), "DE30Y-DE": ("DE", "30Y"),
              "JP10Y-JP": ("JP", "10Y")}
    points = {p.key: p for p in cnbc.parse(CNBC_PAYLOAD, wanted)}

    assert points[("US", "10Y")].yield_pct == 4.758
    assert points[("US", "10Y")].change_bp == 2.0          # (4.758 - 4.738) * 100
    assert points[("US", "2Y")].change_bp == 1.2
    assert points[("DE", "30Y")].change_bp == -0.4         # (3.8114 - 3.8149) * 100
    assert ("JP", "10Y") not in points                     # UNCH last dropped
    assert points[("US", "10Y")].source == "CNBC"


# ----------------------------------------------------------------------- Treasury
TREASURY_CSV = (
    'Date,"1 Mo","2 Yr","10 Yr","20 Yr","30 Yr"\n'
    "08/31/2026,3.85,4.34,4.75,5.24,5.25\n"
    "08/28/2026,3.84,4.34,4.73,5.21,5.22\n"
)


def test_parse_treasury():
    points = {p.tenor: p for p in official.parse_treasury(TREASURY_CSV)}
    assert set(points) == {"2Y", "10Y", "30Y"}
    assert points["10Y"].yield_pct == 4.75
    assert points["10Y"].change_bp == 2.0        # 4.75 - 4.73
    assert points["2Y"].change_bp == 0.0
    assert points["30Y"].country == "US"
    assert points["30Y"].as_of == "08/31/2026"


# ---------------------------------------------------------------------------- BoC
BOC_PAYLOAD = {
    "observations": [
        {
            "d": "2026-08-31",
            "BD.CDN.2YR.DQ.YLD": {"v": "3.01"},
            "BD.CDN.10YR.DQ.YLD": {"v": "3.73"},
            "BD.CDN.LONG.DQ.YLD": {"v": "4.14"},
        },
        {
            "d": "2026-08-28",
            "BD.CDN.2YR.DQ.YLD": {"v": "2.96"},
            "BD.CDN.10YR.DQ.YLD": {"v": "3.70"},
            "BD.CDN.LONG.DQ.YLD": {"v": "4.10"},
        },
    ]
}


def test_parse_boc():
    points = {p.tenor: p for p in official.parse_boc(BOC_PAYLOAD)}
    assert points["2Y"].yield_pct == 3.01
    assert points["2Y"].change_bp == 5.0          # 3.01 - 2.96
    assert points["30Y"].yield_pct == 4.14        # LONG mapped to 30Y
    assert points["10Y"].source == "BoC"


# ---------------------------------------------------------------------------- MOF
MOF_CSV = (
    "Interest Rate (August 2026),,,,,,,,,,,,,,,(Unit : %)\n"
    "Date,1Y,2Y,3Y,4Y,5Y,6Y,7Y,8Y,9Y,10Y,15Y,20Y,25Y,30Y,40Y\n"
    "2026/8/28,1.30,1.70,1.9,2.0,2.1,2.2,2.3,2.4,2.5,2.90,3.4,3.7,3.9,4.05,4.0\n"
    "2026/8/31,1.31,1.743,1.9,2.0,2.1,2.2,2.3,2.4,2.5,2.943,3.5,3.8,3.9,4.092,4.0\n"
    ",,,,,,,,,,,,,,,\n"
)


def test_parse_mof():
    points = {p.tenor: p for p in official.parse_mof(MOF_CSV)}
    assert points["2Y"].yield_pct == 1.743
    assert points["10Y"].yield_pct == 2.943
    assert points["30Y"].yield_pct == 4.092
    assert points["10Y"].change_bp == 4.3         # 2.943 - 2.90
    assert points["2Y"].as_of == "2026/8/31"


# --------------------------------------------------------------------- Bundesbank
BUNDESBANK_CSV = (
    '"";BBSIS.D.I.ZAR...;FLAGS\n'
    "Dezimalstellen;2;\n"
    "Stand vom;01.09.2026 13:13:42 Uhr;\n"
    "2026-08-31;3,33;\n"
    "2026-09-01;3,28;\n"
)


def test_parse_bundesbank():
    p = official.parse_bundesbank(BUNDESBANK_CSV, "10Y")
    assert p is not None
    assert p.country == "DE"
    assert p.yield_pct == 3.28
    assert p.change_bp == -5.0                     # 3.28 - 3.33
    assert p.as_of == "2026-09-01"


# ---------------------------------------------------------------------------- ECB
ECB_CSV = (
    "KEY,FREQ,DATA_TYPE_FM,TIME_PERIOD,OBS_VALUE,OBS_STATUS\n"
    "YC...SR_10Y,B,SR_10Y,2026-08-28,3.2789202996,A\n"
    "YC...SR_10Y,B,SR_10Y,2026-08-31,3.3395935506,A\n"
)


def test_parse_ecb():
    p = official.parse_ecb(ECB_CSV, "10Y")
    assert p is not None
    assert p.country == "EA"
    assert p.yield_pct == 3.34                     # rounded to 3 dp
    assert p.change_bp == 6.1                      # (3.340 - 3.279) * 100
    assert p.source == "ECB"
