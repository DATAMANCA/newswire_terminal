import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"

# Last snapshot, so each digest can also show the move since the previous email
# (not just the move since the market's prior close). Committed back by the
# workflow, since GitHub Actions runners persist nothing themselves.
STATE_PATH = DATA_DIR / "bond_state.json"

# Reuses the newswire_terminal Gmail sender secrets. The recipient is fixed for
# bond digests and deliberately independent of newswire's RECIPIENT_EMAIL.
GMAIL_ADDRESS = os.environ.get("GMAIL_ADDRESS", "")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")
RECIPIENT_EMAIL = os.environ.get("BOND_RECIPIENT_EMAIL") or "malithdisala@gmail.com"

HTTP_TIMEOUT_SECONDS = 25
HTTP_MAX_ATTEMPTS = 3

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Report order. (code, display name, flag emoji)
COUNTRIES: list[tuple[str, str, str]] = [
    ("US", "United States", "\U0001F1FA\U0001F1F8"),
    ("CA", "Canada", "\U0001F1E8\U0001F1E6"),
    ("DE", "Germany", "\U0001F1E9\U0001F1EA"),
    ("GB", "United Kingdom", "\U0001F1EC\U0001F1E7"),
    ("FR", "France", "\U0001F1EB\U0001F1F7"),
    ("IT", "Italy", "\U0001F1EE\U0001F1F9"),
    ("JP", "Japan", "\U0001F1EF\U0001F1F5"),
]
COUNTRY_NAMES = {code: name for code, name, _ in COUNTRIES}

TENORS: list[str] = ["2Y", "10Y", "30Y"]

# Euro-area AAA yield curve (ECB) — shown as a reference row, not a country.
EURO_AREA_CODE = "EA"
EURO_AREA_NAME = "Euro area (AAA)"

# Key benchmark spreads, in basis points: (label, minuend country, subtrahend
# country, tenor).
SPREADS: list[tuple[str, str, str, str]] = [
    ("BTP–Bund (IT–DE 10Y)", "IT", "DE", "10Y"),
    ("OAT–Bund (FR–DE 10Y)", "FR", "DE", "10Y"),
    ("Gilt–Bund (GB–DE 10Y)", "GB", "DE", "10Y"),
    ("UST–Bund (US–DE 10Y)", "US", "DE", "10Y"),
    ("UST–JGB (US–JP 10Y)", "US", "JP", "10Y"),
    ("UST–GoC (US–CA 10Y)", "US", "CA", "10Y"),
]

# 2s10s curve slope (10Y minus 2Y), in basis points, per country.
CURVE_COUNTRIES: list[str] = ["US", "CA", "DE", "GB", "JP"]
