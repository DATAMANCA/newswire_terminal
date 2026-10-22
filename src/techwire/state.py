import json

from . import config


def load() -> dict:
    """{"evening": "2026-10-22", "morning": "2026-10-22"}: the Toronto date each
    email was last sent."""
    if not config.STATE_PATH.exists():
        return {}
    try:
        return json.loads(config.STATE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save(data: dict) -> None:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    config.STATE_PATH.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
