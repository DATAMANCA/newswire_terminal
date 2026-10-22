"""Usage: python -m techwire.main [--mode auto|evening|morning] [--force] [--preview FILE]

auto picks "morning" before noon Toronto time and "evening" after 4pm, and
does nothing in between. Each email goes out at most once per day unless
--force is given; --preview writes the HTML to a file instead of emailing."""

import argparse
import logging
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from . import config, email_send, prices, render, signals, state
from .http_util import new_session
from .models import StockResult
from newswire.watchlist import load_watchlist

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
logger = logging.getLogger("techwire.main")


def us_tickers(tickers: list[str]) -> list[str]:
    return [t for t in tickers if "." not in t and t not in config.EXCLUDE_TICKERS]


def pick_mode(requested: str, now: datetime) -> str | None:
    if requested != "auto":
        return requested
    if now.hour < 12:
        return "morning"
    if now.hour >= 16:
        return "evening"
    return None


def _analyse(session, ticker: str, with_premarket: bool) -> StockResult:
    try:
        snap, sigs = signals.analyse(prices.daily(session, ticker))
        result = StockResult(ticker, ok=True, snapshot=snap, signals=sigs)
    except Exception as exc:  # noqa: BLE001 - one bad ticker mustn't stop the rest
        logger.error("%s failed: %s", ticker, exc)
        return StockResult(ticker, ok=False, error=str(exc)[:80])
    if with_premarket:
        try:
            result.premarket_price = prices.premarket(session, ticker)
        except Exception as exc:  # noqa: BLE001
            logger.warning("%s pre-market price failed: %s", ticker, exc)
    return result


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["auto", "evening", "morning"], default="auto")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--preview")
    args = parser.parse_args(argv)

    now = datetime.now(ZoneInfo(config.TIMEZONE))
    mode = pick_mode(args.mode, now)
    if mode is None:
        logger.info("Auto mode at %s Toronto: not morning or evening; nothing to do.", now.strftime("%H:%M"))
        return 0
    if now.weekday() >= 5 and not args.force:
        logger.info("Weekend; nothing to do.")
        return 0

    sent = state.load()
    today = now.date().isoformat()
    if sent.get(mode) == today and not args.force and not args.preview:
        logger.info("The %s email was already sent today; skipping.", mode)
        return 0

    tickers = us_tickers(load_watchlist(config.WATCHLIST_PATH))
    session = new_session(config.BROWSER_UA)
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda t: _analyse(session, t, mode == "morning"), tickers))

    ok_count = sum(r.ok for r in results)
    signal_count = sum(len(r.signals) for r in results)
    logger.info("%s mode: %d/%d stocks loaded, %d signal(s)", mode, ok_count, len(results), signal_count)
    if ok_count == 0:
        logger.error("No price data for any stock; failing the run.")
        _write_summary(mode, results, email_sent=False)
        return 1

    subject, text_body, html_body = render.build(mode, results, now)

    if args.preview:
        Path(args.preview).write_text(f"<h4>{subject}</h4>\n{html_body}", encoding="utf-8")
        logger.info("Preview written to %s", args.preview)
        return 0

    email_ok = email_send.send(subject, text_body, html_body)
    if email_ok:
        sent[mode] = today
        state.save(sent)
    _write_summary(mode, results, email_sent=email_ok)

    if not email_ok:
        logger.error("Email delivery failed; failing the run so GitHub notifies.")
        return 1
    return 0


def _write_summary(mode: str, results: list[StockResult], email_sent: bool) -> None:
    lines = [f"# Techwire run summary ({mode})", "", "| Ticker | Status | Signals |", "|---|---|---|"]
    for r in results:
        status = "OK" if r.ok else f"FAILED: {r.error}"
        lines.append(f"| {r.ticker} | {status} | {len(r.signals)} |")
    lines += ["", f"Email sent: {'yes' if email_sent else 'no'}"]
    text = "\n".join(lines) + "\n"
    print(text)
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(text)


if __name__ == "__main__":
    sys.exit(run())
