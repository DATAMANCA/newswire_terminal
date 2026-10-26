import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"

# Remembers the last send date (so a backup trigger never sends twice) and the
# last few days' lists (for the NEW tags). Committed back by the workflow.
STATE_PATH = DATA_DIR / "scan_state.json"
STATE_DAYS_KEPT = 5

GMAIL_ADDRESS = os.environ.get("GMAIL_ADDRESS", "")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")
RECIPIENT_EMAIL = os.environ.get("SCAN_RECIPIENT_EMAIL") or "mmautom_258@outlook.com"

HTTP_TIMEOUT_SECONDS = 25
DOWNLOAD_THREADS = 8

TIMEZONE = "America/Toronto"
MARKET_TIMEZONE = "America/New_York"

# ---- Which stocks are scanned ----
MIN_MARKET_CAP = 300_000_000  # no upper limit
MIN_PRICE = 5.0
MIN_AVG_VOLUME = 500_000  # shares/day
VOLUME_AVG_PERIOD = 50

# ---- The scan ----
EMA_PERIOD = 200
# Daily history to download. An EMA is seeded from a simple average and takes
# several hundred bars to settle; with 2 years it can still be ~0.2% off, which
# matters on a 1% band. 5 years matches the charting sites.
HISTORY_RANGE = "5y"
BAND_PCT = 1.0  # flag closes within +/- this % of the EMA
DIRECTION_LOOKBACK = 10  # "came from above/below" = where the close was this many days ago
SLOPE_LOOKBACK = 20  # EMA slope = % change of the EMA over this many days
FLAT_SLOPE_PCT = 0.25  # slopes smaller than this (either way) are shown as "Flat"
