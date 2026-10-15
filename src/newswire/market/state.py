"""What the sector emails have already covered.

Kept compact (a short hash per story) and outside git, in the GitHub Actions
cache. If the cache is ever lost, the next run quietly re-learns what's there
instead of emailing a backlog.
"""

import hashlib
import json
from datetime import datetime, timedelta, timezone

from .. import config
from ..models import NewsItem

VERSION = 1


def empty() -> dict:
    return {"version": VERSION, "last_run_utc": None, "seen": {}, "yahoo_seeded": [],
            "sec_seeded": False, "rotation": 0}


def load() -> dict:
    try:
        data = json.loads(config.MARKET_STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return empty()
    if data.get("version") != VERSION:
        return empty()
    return {**empty(), **data}


def save(data: dict) -> None:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    config.MARKET_STATE_PATH.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")


def _key(item: NewsItem) -> str:
    raw = f"{item.source}|{item.ticker}|{item.uid}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def find_new(
    data: dict,
    sec_items: list[NewsItem] | None,
    yahoo_items: list[NewsItem],
    yahoo_checked: list[str],
    now: datetime | None = None,
) -> list[NewsItem]:
    """Records every item as seen and returns the ones that are new.

    Nothing is reported for a source (SEC) or ticker (Yahoo) the first time it
    is checked, and stories older than MARKET_MAX_ITEM_AGE_DAYS never are.
    `sec_items` is None when the SEC fetch failed.
    """
    now = now or datetime.now(timezone.utc)
    today = now.date().isoformat()
    oldest = now - timedelta(days=config.MARKET_MAX_ITEM_AGE_DAYS)
    seen = data["seen"]
    seeded = set(data["yahoo_seeded"])
    new: list[NewsItem] = []

    def record(item: NewsItem, can_report: bool) -> None:
        key = _key(item)
        if key not in seen and can_report and item.published_at >= oldest:
            new.append(item)
        seen[key] = today

    if sec_items is not None:
        for item in sec_items:
            record(item, data["sec_seeded"])
        data["sec_seeded"] = True

    for item in yahoo_items:
        record(item, item.ticker in seeded)
    data["yahoo_seeded"] = sorted(seeded | set(yahoo_checked))

    data["last_run_utc"] = now.isoformat()
    return new


def prune(data: dict, tickers: set[str], now: datetime | None = None) -> None:
    now = now or datetime.now(timezone.utc)
    cutoff = (now - timedelta(days=config.MARKET_STATE_RETENTION_DAYS)).date().isoformat()
    data["seen"] = {k: d for k, d in data["seen"].items() if d >= cutoff}
    data["yahoo_seeded"] = [t for t in data["yahoo_seeded"] if t in tickers]
