"""Sector emails for every US-listed US company above the market-cap floor.

Runs after the watchlist digest (newswire.main). Your own watchlist tickers
are left out here because they already get the full digest.
"""

import logging
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone

from .. import config, email_digest, watchlist
from ..models import NewsItem
from . import sec_current, state, universe, yahoo_many

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("newswire.market.main")

# Share of Yahoo checks that may fail before the emails carry a warning.
YAHOO_FAILURE_WARNING = 0.2


def _load_companies(exclude: set[str]) -> list[universe.Company]:
    if config.MARKET_UNIVERSE_PATH.exists():
        companies = universe.load()
    else:
        logger.info("No stock list yet; downloading it.")
        companies = universe.refresh(exclude)
    return [c for c in companies if c.ticker not in exclude]


def _yahoo_tickers(companies: list[universe.Company], data: dict) -> list[str]:
    large = [c.ticker for c in companies if c.is_large]
    small = [c.ticker for c in companies if not c.is_large]
    per_run = config.MARKET_YAHOO_SMALL_PER_RUN
    if per_run is None or per_run >= len(small) or not small:
        return large + small
    start = data["rotation"] % len(small)
    data["rotation"] = (start + per_run) % len(small)
    return large + (small + small)[start : start + per_run]


def _split(entries: list, size: int) -> list[list]:
    return [entries[i : i + size] for i in range(0, len(entries), size)]


def send_sector_emails(
    new_items: list[NewsItem], companies: list[universe.Company], failures: list[str]
) -> tuple[int, bool]:
    """Returns (emails sent, all succeeded)."""
    by_ticker = {c.ticker: c for c in companies}
    large = frozenset(c.ticker for c in companies if c.is_large)
    by_sector: dict[str, list[NewsItem]] = defaultdict(list)
    for item in new_items:
        company = by_ticker.get(item.ticker)
        by_sector[company.sector if company else universe.OTHER_SECTOR].append(item)

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    sent, all_ok = 0, True
    for sector in sorted(by_sector):
        entries = email_digest.merge_duplicates(by_sector[sector], first=large)
        parts = _split(entries, config.MARKET_MAX_ITEMS_PER_EMAIL)
        for number, part in enumerate(parts, start=1):
            label = f" ({number}/{len(parts)})" if len(parts) > 1 else ""
            subject = f"Newswire {sector}{label}: {len(part)} new item(s) — {timestamp} UTC"
            text_body, html_body = email_digest.render(part, failures)
            if email_digest.deliver(subject, text_body, html_body):
                sent += 1
            else:
                all_ok = False
            time.sleep(2)  # be gentle with Gmail
    return sent, all_ok


def _write_summary(lines: list[str]) -> None:
    text = "\n".join(["# Sector emails", "", *(line for line in lines if line)]) + "\n"
    print(text)
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(text)


def run() -> int:
    exclude = set(watchlist.load_watchlist(config.WATCHLIST_PATH))
    companies = _load_companies(exclude)
    data = state.load()
    failures: list[str] = []

    tickers = {c.ticker for c in companies}
    try:
        sec_items: list[NewsItem] | None = sec_current.fetch(
            tickers, sec_current.default_since(data["last_run_utc"])
        )
    except Exception as exc:  # noqa: BLE001 - Yahoo should still go out
        logger.exception("SEC latest-filings fetch failed.")
        failures.append(f"SEC ({exc})")
        sec_items = None

    yahoo_list = _yahoo_tickers(companies, data)
    yahoo_items, yahoo_ok, yahoo_failed = yahoo_many.fetch(yahoo_list)
    if yahoo_list and len(yahoo_failed) / len(yahoo_list) > YAHOO_FAILURE_WARNING:
        failures.append(f"YAHOO ({len(yahoo_failed)} of {len(yahoo_list)} tickers failed)")

    first_run = not data["sec_seeded"] and not data["yahoo_seeded"]
    new_items = state.find_new(data, sec_items, yahoo_items, yahoo_ok)
    state.prune(data, tickers)
    state.save(data)

    sent, emails_ok = 0, True
    if new_items:
        sent, emails_ok = send_sector_emails(new_items, companies, failures)

    _write_summary([
        f"- Companies on the list: {len(companies)}",
        f"- SEC filings fetched: {'FAILED' if sec_items is None else len(sec_items)}",
        f"- Yahoo tickers checked: {len(yahoo_ok)} OK, {len(yahoo_failed)} failed",
        "- First run: learned what's already out there, no emails." if first_run else "",
        f"- New stories: {len(new_items)}",
        f"- Emails sent: {sent}",
        f"- Remembered stories: {len(data['seen'])}",
    ])

    if not emails_ok:
        logger.error("Some sector emails failed to send.")
        return 1
    if sec_items is None and not yahoo_ok:
        logger.error("Both SEC and Yahoo failed.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(run())
