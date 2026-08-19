import logging
import traceback
from typing import Callable

from ..models import Source, SourceResult

logger = logging.getLogger("newswire.sources")


def fetch_source_safe(
    source: Source, fetch_fn: Callable[[list[str]], list], tickers: list[str]
) -> SourceResult:
    """Run a source's fetch function, isolating any failure so it can never
    take down the other sources or block email delivery of what did work."""
    try:
        items = fetch_fn(tickers)
        return SourceResult(source=source, ok=True, items=items)
    except Exception as exc:  # noqa: BLE001 - intentional catch-all boundary
        logger.error("Source %s failed: %s\n%s", source, exc, traceback.format_exc())
        return SourceResult(source=source, ok=False, items=[], error=str(exc))
