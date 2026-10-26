"""Usage: python -m scanwire.main [--force] [--preview FILE] [--limit N]

Sends the 200 EMA scan once per weekday, after the US close. Does nothing if
there's no new close today (weekend, market holiday, or run before the close)
or that close was already emailed, unless --force is given. --preview
writes the HTML to a file instead of emailing; --limit scans only the N
largest companies (for quick tests)."""

import argparse
import logging
import os
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from newswire.market import universe
from techwire import config as tech_config
from techwire import prices
from techwire.http_util import new_session

from . import config, email_send, render, scan, state
from .scan import Outcome

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
logger = logging.getLogger("scanwire.main")


def load_companies() -> list[universe.Company]:
    """Fresh from Nasdaq (including watchlist stocks, which the saved list
    leaves out); falls back to the saved weekly list if Nasdaq is down."""
    try:
        companies = universe.build(universe.download_rows(), exclude=set())
    except Exception as exc:  # noqa: BLE001
        logger.warning("Nasdaq list failed (%s); using the saved list.", exc)
        companies = universe.load()
    return [c for c in companies if c.market_cap >= config.MIN_MARKET_CAP]


def _check(session, company: universe.Company) -> Outcome:
    try:
        return scan.check(company, prices.daily(session, company.ticker, history_range=config.HISTORY_RANGE))
    except Exception as exc:  # noqa: BLE001 - one bad ticker mustn't stop the rest
        logger.warning("%s failed: %s", company.ticker, exc)
        return Outcome(company.ticker, scan.FAILED, error=str(exc)[:80])


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--preview")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args(argv)
    relaxed = args.force or bool(args.preview)

    now = datetime.now(ZoneInfo(config.TIMEZONE))
    if now.weekday() >= 5 and not relaxed:
        logger.info("Weekend; nothing to do.")
        return 0
    saved = state.load()

    companies = load_companies()[: args.limit]
    logger.info("Scanning %d companies worth $%dM+", len(companies), config.MIN_MARKET_CAP // 1_000_000)
    session = new_session(tech_config.BROWSER_UA)
    with ThreadPoolExecutor(max_workers=config.DOWNLOAD_THREADS) as pool:
        outcomes = list(pool.map(lambda c: _check(session, c), companies))

    logger.info("Results: %s", dict(Counter(o.reason for o in outcomes)))
    dates = [o.as_of for o in outcomes if o.as_of]
    if not dates:
        logger.error("No price data for any stock; failing the run.")
        _write_summary(outcomes, email_sent=False)
        return 1
    as_of = max(dates)
    market_today = datetime.now(ZoneInfo(config.MARKET_TIMEZONE)).date()
    if as_of != market_today and not relaxed:
        logger.info("Latest close is %s, not today; market closed or not closed yet. No email.", as_of)
        return 0
    if saved.get("last_close") == as_of.isoformat() and not relaxed:
        logger.info("The scan for the %s close was already sent; skipping.", as_of)
        return 0

    # A stock whose last bar is older (halted, delisted) isn't current; leave it out.
    hits = [o.hit for o in outcomes if o.hit and o.as_of == as_of]
    previous = state.previous_list(saved, as_of.isoformat())
    for h in hits:
        h.new = previous is not None and h.company.ticker not in previous

    subject, text_body, html_body = render.build(hits, outcomes, as_of, first_run=previous is None)

    if args.preview:
        Path(args.preview).write_text(
            f'<meta charset="utf-8"><h4>{subject}</h4>\n{html_body}', encoding="utf-8"
        )
        logger.info("Preview written to %s (%d stocks)", args.preview, len(hits))
        return 0

    email_ok = email_send.send(subject, text_body, html_body)
    if email_ok:
        state.save(state.record(saved, as_of.isoformat(), [h.company.ticker for h in hits]))
    _write_summary(outcomes, email_sent=email_ok)

    if not email_ok:
        logger.error("Email delivery failed; failing the run so GitHub notifies.")
        return 1
    return 0


def _write_summary(outcomes: list[Outcome], email_sent: bool) -> None:
    lines = ["# EMA scan run summary", "", "| Result | Stocks |", "|---|---|"]
    lines += [f"| {reason} | {n} |" for reason, n in Counter(o.reason for o in outcomes).most_common()]
    failed = [o.ticker for o in outcomes if o.reason == scan.FAILED]
    if failed:
        lines += ["", "Failed: " + ", ".join(failed)]
    lines += ["", f"Email sent: {'yes' if email_sent else 'no'}"]
    text = "\n".join(lines) + "\n"
    print(text)
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(text)


if __name__ == "__main__":
    sys.exit(run())
