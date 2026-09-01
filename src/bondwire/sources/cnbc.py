"""Primary source: CNBC's public quote endpoint.

One request returns near-real-time 2/10/30-year government-bond yields for every
country we track, with the prior close alongside. No API key. This is the
"scrape" layer the design accepts as best-effort — the official sources back it
up when it is unavailable or blocked.
"""

import logging

from .. import config, http_util
from ..models import YieldPoint

logger = logging.getLogger("bondwire.sources.cnbc")

QUOTE_URL = "https://quote.cnbc.com/quote-html-webservice/quote.htm"


def cnbc_symbol(country: str, tenor: str) -> str:
    # US Treasuries use bare symbols; every other market uses "<CC><T>Y-<CC>".
    if country == "US":
        return f"US{tenor}"
    return f"{country}{tenor}-{country}"


def _to_pct(raw) -> float | None:
    if raw is None:
        return None
    text = str(raw).strip().rstrip("%").strip()
    if not text or text.upper() in {"UNCH", "N/A", "NA", "--"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _change_bp(last: float, quote: dict) -> float | None:
    """Prefer computing the move from last minus prior close; fall back to
    CNBC's own `change` field (percentage points -> basis points)."""
    prev = _to_pct(quote.get("previous_day_closing"))
    if prev is not None:
        return round((last - prev) * 100, 1)

    raw = str(quote.get("change", "")).strip()
    if raw.upper() in {"", "UNCH"}:
        return 0.0 if raw.upper() == "UNCH" else None
    try:
        return round(float(raw.replace("+", "")) * 100, 1)
    except ValueError:
        return None


def parse(payload: dict, wanted: dict[str, tuple[str, str]]) -> list[YieldPoint]:
    quotes = (payload.get("ITVQuoteResult") or {}).get("ITVQuote") or []
    if isinstance(quotes, dict):  # single-symbol responses aren't wrapped in a list
        quotes = [quotes]

    points: list[YieldPoint] = []
    for quote in quotes:
        symbol = quote.get("symbol")
        if symbol not in wanted:
            continue
        last = _to_pct(quote.get("last"))
        if last is None:
            logger.warning("CNBC %s has no usable last value; skipping.", symbol)
            continue
        country, tenor = wanted[symbol]
        points.append(
            YieldPoint(
                country=country,
                tenor=tenor,
                yield_pct=last,
                change_bp=_change_bp(last, quote),
                as_of=str(quote.get("last_timedate") or "").strip(),
                source="CNBC",
            )
        )
    return points


def fetch(
    countries: list[tuple[str, str, str]], tenors: list[str]
) -> list[YieldPoint]:
    wanted: dict[str, tuple[str, str]] = {}
    for code, _, _ in countries:
        for tenor in tenors:
            wanted[cnbc_symbol(code, tenor)] = (code, tenor)

    session = http_util.new_session(config.BROWSER_UA)
    session.headers.update({"Accept": "application/json", "Referer": "https://www.cnbc.com/bonds/"})
    response = http_util.get(
        session,
        QUOTE_URL,
        params={
            "symbols": "|".join(wanted),
            "requestMethod": "itv",
            "noform": "1",
            "fund": "1",
            "exthrs": "1",
            "output": "json",
        },
    )
    return parse(response.json(), wanted)
