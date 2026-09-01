"""Official / primary-issuer sources.

These refresh only at each market's daily close (Bundesbank updates through the
day), but they never silently change shape and need no key. They fill any gap
CNBC leaves and are cross-checked against it in the digest footer.

Each ``fetch_*`` returns a list[YieldPoint]; the caller isolates failures.
Each has a matching pure ``parse_*`` for offline testing.
"""

import csv
import io
import logging
import re

from .. import config, http_util
from ..models import YieldPoint

logger = logging.getLogger("bondwire.sources.official")

_DATE_RE = re.compile(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}")


def _bp(newer: float, older: float | None) -> float | None:
    return None if older is None else round((newer - older) * 100, 1)


# --------------------------------------------------------------------------- US
TREASURY_URL = (
    "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
    "daily-treasury-rates.csv/2026/all"
    "?type=daily_treasury_yield_curve&field_tdr_date_value=2026&page&_format=csv"
)
_TREASURY_COLS = {"2Y": "2 Yr", "10Y": "10 Yr", "30Y": "30 Yr"}


def parse_treasury(text: str) -> list[YieldPoint]:
    rows = list(csv.DictReader(io.StringIO(text)))
    if not rows:
        return []
    latest, prev = rows[0], (rows[1] if len(rows) > 1 else None)
    out: list[YieldPoint] = []
    for tenor, col in _TREASURY_COLS.items():
        try:
            value = float(latest[col])
        except (KeyError, TypeError, ValueError):
            continue
        prior = None
        if prev is not None:
            try:
                prior = float(prev[col])
            except (KeyError, TypeError, ValueError):
                prior = None
        out.append(YieldPoint("US", tenor, value, _bp(value, prior), latest["Date"], "Treasury"))
    return out


def fetch_treasury() -> list[YieldPoint]:
    session = http_util.new_session(config.BROWSER_UA)
    return parse_treasury(http_util.get(session, TREASURY_URL).text)


# --------------------------------------------------------------------------- CA
BOC_SERIES = {
    "BD.CDN.2YR.DQ.YLD": "2Y",
    "BD.CDN.10YR.DQ.YLD": "10Y",
    "BD.CDN.LONG.DQ.YLD": "30Y",  # long-term benchmark, ~30Y proxy
}
BOC_URL = (
    "https://www.bankofcanada.ca/valet/observations/"
    + ",".join(BOC_SERIES)
    + "/json?recent=2"
)


def parse_boc(payload: dict) -> list[YieldPoint]:
    obs = payload.get("observations") or []
    if not obs:
        return []
    latest = obs[0]
    prev = obs[1] if len(obs) > 1 else {}

    def val(row: dict, series: str) -> float | None:
        cell = row.get(series)
        try:
            return float(cell["v"]) if cell and cell.get("v") not in (None, "") else None
        except (TypeError, ValueError):
            return None

    out: list[YieldPoint] = []
    for series, tenor in BOC_SERIES.items():
        value = val(latest, series)
        if value is None:
            continue
        out.append(
            YieldPoint("CA", tenor, value, _bp(value, val(prev, series)), latest.get("d", ""), "BoC")
        )
    return out


def fetch_boc() -> list[YieldPoint]:
    session = http_util.new_session(config.BROWSER_UA)
    return parse_boc(http_util.get(session, BOC_URL).json())


# --------------------------------------------------------------------------- JP
MOF_URL = (
    "https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/jgbcme.csv"
)


def parse_mof(text: str) -> list[YieldPoint]:
    reader = csv.reader(io.StringIO(text))
    header: list[str] | None = None
    data: list[list[str]] = []
    for row in reader:
        if not row:
            continue
        if row[0].strip() == "Date":
            header = [c.strip() for c in row]
            continue
        if header and _DATE_RE.match(row[0].strip()):
            data.append(row)
    if not header or not data:
        return []

    idx = {name: i for i, name in enumerate(header)}
    latest = data[-1]
    prev = data[-2] if len(data) > 1 else None

    def cell(row: list[str], tenor: str) -> float | None:
        i = idx.get(tenor)
        if i is None or i >= len(row):
            return None
        try:
            return float(row[i])
        except ValueError:
            return None

    out: list[YieldPoint] = []
    for tenor in ("2Y", "10Y", "30Y"):
        value = cell(latest, tenor)
        if value is None:
            continue
        out.append(
            YieldPoint("JP", tenor, value, _bp(value, cell(prev or [], tenor)), latest[0].strip(), "MOF")
        )
    return out


def fetch_mof() -> list[YieldPoint]:
    session = http_util.new_session(config.BROWSER_UA)
    return parse_mof(http_util.get(session, MOF_URL).text)


# --------------------------------------------------------------------------- DE
_BUNDESBANK_KEYS = {"2Y": "R02XX", "10Y": "R10XX", "30Y": "R30XX"}


def _bundesbank_url(tenor_key: str) -> str:
    return (
        "https://api.statistiken.bundesbank.de/rest/data/BBSIS/"
        f"D.I.ZAR.ZI.EUR.S1311.B.A604.{tenor_key}.R.A.A._Z._Z.A"
        "?lastNObservations=2&format=csv"
    )


def parse_bundesbank(text: str, tenor: str) -> YieldPoint | None:
    points: list[tuple[str, float]] = []
    for line in text.splitlines():
        parts = line.split(";")
        if len(parts) < 2 or not _DATE_RE.match(parts[0].strip()):
            continue
        try:
            points.append((parts[0].strip(), float(parts[1].strip().replace(",", "."))))
        except ValueError:
            continue
    if not points:
        return None
    date, value = points[-1]
    prior = points[-2][1] if len(points) > 1 else None
    return YieldPoint("DE", tenor, value, _bp(value, prior), date, "Bundesbank")


def fetch_bundesbank() -> list[YieldPoint]:
    session = http_util.new_session(config.BROWSER_UA)
    session.headers.update({"Accept": "text/csv"})
    out: list[YieldPoint] = []
    for tenor, key in _BUNDESBANK_KEYS.items():
        try:
            point = parse_bundesbank(http_util.get(session, _bundesbank_url(key)).text, tenor)
        except Exception:
            logger.exception("Bundesbank %s fetch failed; skipping that tenor.", tenor)
            continue
        if point is not None:
            out.append(point)
    return out


# ------------------------------------------------------------------ Euro area (ECB)
_ECB_KEYS = {"2Y": "SR_2Y", "10Y": "SR_10Y", "30Y": "SR_30Y"}


def _ecb_url(data_type: str) -> str:
    return (
        "https://data-api.ecb.europa.eu/service/data/YC/"
        f"B.U2.EUR.4F.G_N_A.SV_C_YM.{data_type}?lastNObservations=2"
    )


def parse_ecb(text: str, tenor: str) -> YieldPoint | None:
    rows = list(csv.DictReader(io.StringIO(text)))
    obs = [r for r in rows if r.get("OBS_VALUE") not in (None, "")]
    if not obs:
        return None
    obs.sort(key=lambda r: r.get("TIME_PERIOD", ""))
    try:
        value = round(float(obs[-1]["OBS_VALUE"]), 3)
    except (TypeError, ValueError):
        return None
    prior = None
    if len(obs) > 1:
        try:
            prior = round(float(obs[-2]["OBS_VALUE"]), 3)
        except (TypeError, ValueError):
            prior = None
    return YieldPoint(
        config.EURO_AREA_CODE, tenor, value, _bp(value, prior), obs[-1].get("TIME_PERIOD", ""), "ECB"
    )


def fetch_ecb() -> list[YieldPoint]:
    session = http_util.new_session(config.BROWSER_UA)
    session.headers.update({"Accept": "text/csv"})
    out: list[YieldPoint] = []
    for tenor, data_type in _ECB_KEYS.items():
        try:
            point = parse_ecb(http_util.get(session, _ecb_url(data_type)).text, tenor)
        except Exception:
            logger.exception("ECB %s fetch failed; skipping that tenor.", tenor)
            continue
        if point is not None:
            out.append(point)
    return out


FETCHERS = {
    "Treasury": fetch_treasury,
    "BoC": fetch_boc,
    "MOF": fetch_mof,
    "Bundesbank": fetch_bundesbank,
    "ECB": fetch_ecb,
}
