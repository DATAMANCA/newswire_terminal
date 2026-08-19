import json
import logging
from datetime import datetime, timezone

from . import config, http_util

logger = logging.getLogger("newswire.cik_cache")

COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"


def _cache_is_fresh(cache: dict) -> bool:
    fetched_at = cache.get("fetched_at")
    if not fetched_at:
        return False
    age = datetime.now(timezone.utc) - datetime.fromisoformat(fetched_at)
    return age.total_seconds() < config.CIK_CACHE_MAX_AGE_HOURS * 3600


def _load_cache() -> dict:
    if not config.CIK_CACHE_PATH.exists():
        return {}
    try:
        return json.loads(config.CIK_CACHE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_cache(cache: dict) -> None:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    config.CIK_CACHE_PATH.write_text(
        json.dumps(cache, indent=2, sort_keys=True), encoding="utf-8"
    )


def _fetch_ticker_map() -> dict:
    session = http_util.new_session(config.EDGAR_USER_AGENT)
    response = http_util.get(session, COMPANY_TICKERS_URL)
    raw = response.json()
    # raw is {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}, ...}
    return {
        entry["ticker"].upper(): str(entry["cik_str"]).zfill(10)
        for entry in raw.values()
    }


def get_cik_map() -> dict:
    cache = _load_cache()
    if _cache_is_fresh(cache) and cache.get("tickers"):
        return cache["tickers"]

    try:
        tickers = _fetch_ticker_map()
    except Exception:
        if cache.get("tickers"):
            logger.warning(
                "Refreshing ticker->CIK map failed; falling back to stale cache."
            )
            return cache["tickers"]
        raise

    _save_cache(
        {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "tickers": tickers,
        }
    )
    return tickers
