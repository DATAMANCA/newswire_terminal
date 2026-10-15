import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"

WATCHLIST_PATH = DATA_DIR / "watchlist.txt"
STATE_PATH = DATA_DIR / "state.json"
CIK_CACHE_PATH = DATA_DIR / "cik_cache.json"

# SEC requires a descriptive, contactable User-Agent on every request. This is
# not a secret -- SEC wants it identifiable, so it ships as a plain constant.
EDGAR_USER_AGENT = "NewswireTerminal/1.0 (contact: malithdisala@gmail.com)"
YAHOO_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

GMAIL_ADDRESS = os.environ.get("GMAIL_ADDRESS", "")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")
RECIPIENT_EMAIL = os.environ.get("RECIPIENT_EMAIL") or GMAIL_ADDRESS

EDGAR_FORM_ALLOWLIST: set[str] | None = None  # None = include every form type

CIK_CACHE_MAX_AGE_HOURS = 24
YAHOO_MIN_INTERVAL_SECONDS = 0.75

STATE_RETENTION_DAYS = 180
# EDGAR's "recent filings" bucket alone can hold up to ~1000 entries for an
# active large-cap (mostly Form 4s), so this must comfortably exceed that or
# pruning will discard dedupe records for filings the source still returns,
# causing false "new" re-alerts. This is a pathological-growth safety valve,
# not the primary retention control -- STATE_RETENTION_DAYS is.
STATE_MAX_ITEMS_PER_TICKER_SOURCE = 3000

WATCHDOG_STALE_THRESHOLD_HOURS = 3

HTTP_TIMEOUT_SECONDS = 20
HTTP_MAX_ATTEMPTS = 3

# --- Whole-market sector emails (newswire.market) ---
MARKET_UNIVERSE_PATH = DATA_DIR / "market_universe.csv"
# Kept in the GitHub Actions cache, not committed, so the repo doesn't grow.
MARKET_STATE_PATH = DATA_DIR / "market_state.json"
MARKET_MIN_CAP = 100_000_000
MARKET_LARGE_CAP = 10_000_000_000  # these get Yahoo news every run and are listed first
MARKET_STATE_RETENTION_DAYS = 14
MARKET_MAX_ITEM_AGE_DAYS = 3  # older stories that resurface in a feed are skipped
MARKET_YAHOO_WORKERS = 6
# How many companies under $10B get their Yahoo feed checked per run (rotating).
# None checks all of them every run; lower it if Yahoo starts blocking.
MARKET_YAHOO_SMALL_PER_RUN: int | None = None
MARKET_SEC_FORMS = ["8-K", "10-Q", "10-K", "S-1", "SCHEDULE 13D", "SC 13D"]
MARKET_SEC_MAX_PAGES = 10  # 100 filings per page, per form
MARKET_MAX_ITEMS_PER_EMAIL = 120  # bigger sector emails are split into parts
