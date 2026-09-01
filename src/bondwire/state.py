import json
from datetime import datetime, timezone

from . import config
from .models import YieldPoint

STATE_VERSION = 1


def load() -> dict:
    """Returns the previous snapshot: {"sent_at_utc": str|None,
    "yields": {"US|10Y": 4.758, ...}}."""
    if not config.STATE_PATH.exists():
        return {"version": STATE_VERSION, "sent_at_utc": None, "yields": {}}
    try:
        data = json.loads(config.STATE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"version": STATE_VERSION, "sent_at_utc": None, "yields": {}}
    data.setdefault("yields", {})
    return data


def save(points: list[YieldPoint]) -> None:
    snapshot = {
        "version": STATE_VERSION,
        "sent_at_utc": datetime.now(timezone.utc).isoformat(),
        "yields": {f"{p.country}|{p.tenor}": p.yield_pct for p in points},
    }
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    config.STATE_PATH.write_text(
        json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8"
    )
