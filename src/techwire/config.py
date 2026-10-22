import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
WATCHLIST_PATH = DATA_DIR / "watchlist.txt"

# Remembers which evening/morning emails were already sent, so a late backup
# trigger never sends the same email twice. Committed back by the workflow.
STATE_PATH = DATA_DIR / "tech_state.json"

# Same sender and recipient as the watchlist news digest.
GMAIL_ADDRESS = os.environ.get("GMAIL_ADDRESS", "")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")
RECIPIENT_EMAIL = os.environ.get("RECIPIENT_EMAIL") or GMAIL_ADDRESS

HTTP_TIMEOUT_SECONDS = 25
HTTP_MAX_ATTEMPTS = 3

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

TIMEZONE = "America/Toronto"
MARKET_TIMEZONE = "America/New_York"
MARKET_CLOSE_HOUR = 16  # 4pm New York; a daily bar before this is unfinished

# Watchlist tickers left out of technicals. Anything with a "." (e.g. 2408.TT)
# is foreign and skipped automatically; this set is for the rest.
EXCLUDE_TICKERS = {"SKHY"}

# Daily price history to download (needs >200 bars for the 200-day average and
# >252 for the 52-week high/low).
HISTORY_RANGE = "2y"

# ---- Indicator settings (standard textbook values) ----
SMA_FAST = 50
SMA_SLOW = 200

RSI_PERIOD = 14
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30

MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9

BOLLINGER_PERIOD = 20
BOLLINGER_STDDEV = 2.0
# A "squeeze" = band width at its narrowest in this many days.
SQUEEZE_LOOKBACK = 120

STOCH_PERIOD = 14
STOCH_SMOOTH = 3  # %K smoothing (slow stochastic)
STOCH_SIGNAL = 3  # %D
STOCH_OVERBOUGHT = 80
STOCH_OVERSOLD = 20

VOLUME_AVG_PERIOD = 20
VOLUME_SPIKE_MULTIPLE = 2.0

YEAR_BARS = 252  # trading days in 52 weeks

# Swing highs/lows used for support/resistance: a bar whose high (low) is the
# highest (lowest) of SWING_WINDOW bars on each side, within the last
# LEVEL_LOOKBACK days.
SWING_WINDOW = 5
LEVEL_LOOKBACK = 120

# Divergences: compare the last two swing lows/highs (PIVOT_WINDOW bars each
# side) inside the last DIVERGENCE_LOOKBACK days, at least
# DIVERGENCE_MIN_GAP bars apart. Alerted on the day the second swing is
# confirmed, i.e. PIVOT_WINDOW days after it.
DIVERGENCE_LOOKBACK = 60
DIVERGENCE_PIVOT_WINDOW = 3
DIVERGENCE_MIN_GAP = 5
