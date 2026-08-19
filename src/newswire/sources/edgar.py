import logging
from datetime import datetime, timezone

from .. import cik_cache, config, http_util
from ..models import NewsItem

logger = logging.getLogger("newswire.sources.edgar")

SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"


def _filing_url(cik: str, accession_number: str, primary_document: str) -> str:
    accession_no_dashes = accession_number.replace("-", "")
    cik_no_zeros = str(int(cik))
    return (
        f"https://www.sec.gov/Archives/edgar/data/{cik_no_zeros}/"
        f"{accession_no_dashes}/{primary_document}"
    )


def _parse_filings(ticker: str, cik: str, payload: dict) -> list[NewsItem]:
    recent = payload.get("filings", {}).get("recent", {})
    accession_numbers = recent.get("accessionNumber", [])
    forms = recent.get("form", [])
    filing_dates = recent.get("filingDate", [])
    primary_documents = recent.get("primaryDocument", [])

    items: list[NewsItem] = []
    for i, accession_number in enumerate(accession_numbers):
        form = forms[i] if i < len(forms) else ""
        if config.EDGAR_FORM_ALLOWLIST is not None and form not in config.EDGAR_FORM_ALLOWLIST:
            continue

        filing_date = filing_dates[i] if i < len(filing_dates) else None
        published_at = (
            datetime.fromisoformat(filing_date).replace(tzinfo=timezone.utc)
            if filing_date
            else datetime.now(timezone.utc)
        )
        primary_document = primary_documents[i] if i < len(primary_documents) else ""

        items.append(
            NewsItem(
                source="EDGAR",
                ticker=ticker,
                uid=accession_number,
                title=f"{ticker} filed {form}",
                url=_filing_url(cik, accession_number, primary_document),
                published_at=published_at,
                extra={"form": form},
            )
        )
    return items


def fetch(tickers: list[str]) -> list[NewsItem]:
    cik_map = cik_cache.get_cik_map()
    session = http_util.new_session(config.EDGAR_USER_AGENT)

    all_items: list[NewsItem] = []
    for ticker in tickers:
        cik = cik_map.get(ticker.upper())
        if not cik:
            logger.warning("No CIK found for ticker %s; skipping EDGAR for it.", ticker)
            continue
        try:
            response = http_util.get(session, SUBMISSIONS_URL.format(cik=cik))
            all_items.extend(_parse_filings(ticker, cik, response.json()))
        except Exception:
            logger.exception("EDGAR fetch failed for ticker %s; skipping it.", ticker)
            continue

    return all_items
