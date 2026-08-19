import logging
import sys

from . import config, email_digest, state, summary, watchlist
from .models import SourceResult
from .sources import base as source_base
from .sources import edgar, finnhub, yahoo_rss

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("newswire.main")

SOURCE_FETCHERS = {
    "EDGAR": edgar.fetch,
    "YAHOO": yahoo_rss.fetch,
    "FINNHUB": finnhub.fetch,
}


def run() -> int:
    tickers = watchlist.load_watchlist(config.WATCHLIST_PATH)
    if not tickers:
        logger.info("Watchlist is empty; nothing to do.")
        return 0

    logger.info("Watching %d ticker(s): %s", len(tickers), ", ".join(tickers))

    current_state, is_first_run = state.load_state()

    results: dict[str, SourceResult] = {}
    for source, fetch_fn in SOURCE_FETCHERS.items():
        results[source] = source_base.fetch_source_safe(source, fetch_fn, tickers)
        if results[source].ok:
            logger.info("%s: %d item(s)", source, len(results[source].items))
        else:
            logger.warning("%s: FAILED (%s)", source, results[source].error)

    new_items = state.diff_against_state(results, current_state, is_first_run)
    state.prune_state(current_state)
    state.save_state(current_state)

    source_failures = [r for r in results.values() if not r.ok]

    email_ok = True
    if new_items:
        email_ok = email_digest.send(new_items, source_failures)
    elif is_first_run:
        seeded_count = sum(len(r.items) for r in results.values() if r.ok)
        logger.info("Seeded %d item(s) across all sources; no email sent.", seeded_count)

    summary.write_step_summary(results, new_items, is_first_run, email_sent=bool(new_items and email_ok))

    all_sources_failed = all(not r.ok for r in results.values())

    if not email_ok:
        logger.error("Email delivery failed; failing the run so GitHub's failure notification fires.")
        return 1
    if all_sources_failed:
        logger.error("All sources failed this run; failing the run so GitHub's failure notification fires.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(run())
