import json
from datetime import datetime, timedelta, timezone

from . import config
from .models import NewsItem, SourceResult

STATE_VERSION = 1


def _empty_state() -> dict:
    return {"version": STATE_VERSION, "last_run_utc": None, "seen": {}}


def load_state() -> tuple[dict, bool]:
    """Returns (state, is_first_run)."""
    if not config.STATE_PATH.exists():
        return _empty_state(), True
    try:
        state = json.loads(config.STATE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return _empty_state(), True
    state.setdefault("seen", {})
    return state, False


def save_state(state: dict) -> None:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    config.STATE_PATH.write_text(
        json.dumps(state, indent=2, sort_keys=True), encoding="utf-8"
    )


def diff_against_state(
    results: dict[str, SourceResult], state: dict, is_first_run: bool
) -> list[NewsItem]:
    """Determines which items are new, and records every item (new or not)
    into state['seen'] so subsequent runs won't re-alert on them.

    On the very first run for the app overall, or the first time a given
    ticker is seen for a given source, items are recorded but never treated
    as "new" -- this prevents dumping a historical backlog into one email.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    seen = state.setdefault("seen", {})
    new_items: list[NewsItem] = []

    for source, result in results.items():
        if not result.ok:
            continue

        source_seen = seen.setdefault(source, {})
        for item in result.items:
            ticker_is_new = item.ticker not in source_seen
            ticker_seen = source_seen.setdefault(item.ticker, {})
            item_is_new = item.uid not in ticker_seen

            if item_is_new and not is_first_run and not ticker_is_new:
                new_items.append(item)

            ticker_seen[item.uid] = now_iso

    state["last_run_utc"] = now_iso
    return new_items


def prune_state(state: dict) -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(days=config.STATE_RETENTION_DAYS)
    seen = state.get("seen", {})

    for source, tickers in seen.items():
        for ticker, uid_map in tickers.items():
            fresh_items = []
            for uid, ts in uid_map.items():
                try:
                    is_fresh = datetime.fromisoformat(ts) >= cutoff
                except ValueError:
                    is_fresh = True
                if is_fresh:
                    fresh_items.append((uid, ts))

            fresh_items.sort(key=lambda pair: pair[1], reverse=True)
            capped = fresh_items[: config.STATE_MAX_ITEMS_PER_TICKER_SOURCE]
            tickers[ticker] = dict(capped)
