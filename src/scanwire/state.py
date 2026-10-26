import json

from . import config


def load() -> dict:
    """{"last_close": "2026-10-26", "lists": {"2026-10-26": ["AAPL", ...]}}:
    the closing date of the last email (so a backup trigger never sends the
    same close twice), and the tickers flagged on each of the last few trading
    days."""
    if not config.STATE_PATH.exists():
        return {}
    try:
        return json.loads(config.STATE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def previous_list(data: dict, as_of: str) -> set[str] | None:
    """Tickers flagged on the last trading day before `as_of`, or None on the
    first run."""
    earlier = [d for d in data.get("lists", {}) if d < as_of]
    return set(data["lists"][max(earlier)]) if earlier else None


def record(data: dict, as_of: str, tickers: list[str]) -> dict:
    lists = dict(data.get("lists", {}))
    lists[as_of] = sorted(tickers)
    keep = sorted(lists)[-config.STATE_DAYS_KEPT :]
    return {"last_close": as_of, "lists": {d: lists[d] for d in keep}}


def save(data: dict) -> None:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    config.STATE_PATH.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
