import logging
import smtplib
from collections import defaultdict
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from tenacity import retry, stop_after_attempt, wait_exponential

from . import config
from .models import NewsItem, SourceResult

logger = logging.getLogger("newswire.email")


def _group_by_ticker_then_source(
    items: list[NewsItem],
) -> dict[str, dict[str, list[NewsItem]]]:
    grouped: dict[str, dict[str, list[NewsItem]]] = defaultdict(lambda: defaultdict(list))
    for item in items:
        grouped[item.ticker][item.source].append(item)
    return grouped


def _build_subject(new_items: list[NewsItem]) -> str:
    tickers = {item.ticker for item in new_items}
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    return (
        f"Newswire Terminal: {len(new_items)} new item(s) across "
        f"{len(tickers)} ticker(s) — {timestamp} UTC"
    )


def _build_body(
    new_items: list[NewsItem], source_failures: list[SourceResult]
) -> tuple[str, str]:
    grouped = _group_by_ticker_then_source(new_items)
    text_lines: list[str] = []
    html_lines: list[str] = ["<html><body>"]

    if source_failures:
        warning = "WARNING: the following sources failed this run: " + ", ".join(
            f"{r.source} ({r.error})" for r in source_failures
        )
        text_lines.append(warning)
        text_lines.append("")
        html_lines.append(f"<p style='color:#b00'><b>{warning}</b></p>")

    for ticker in sorted(grouped):
        text_lines.append(f"=== {ticker} ===")
        html_lines.append(f"<h2>{ticker}</h2>")
        for source in sorted(grouped[ticker]):
            text_lines.append(f"-- {source} --")
            html_lines.append(f"<h3>{source}</h3><ul>")
            items = sorted(grouped[ticker][source], key=lambda i: i.published_at)
            for item in items:
                when = item.published_at.strftime("%Y-%m-%d %H:%M UTC")
                form = item.extra.get("form")
                label = f"[{form}] " if form else ""
                text_lines.append(f"  {label}{item.title} ({when})\n  {item.url}")
                html_lines.append(
                    f"<li>{label}<a href='{item.url}'>{item.title}</a> "
                    f"<span style='color:#666'>({when})</span></li>"
                )
            html_lines.append("</ul>")
        text_lines.append("")

    html_lines.append("</body></html>")
    return "\n".join(text_lines), "\n".join(html_lines)


@retry(reraise=True, stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=2, max=30))
def _send(message: MIMEMultipart) -> None:
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=config.HTTP_TIMEOUT_SECONDS) as smtp:
        smtp.login(config.GMAIL_ADDRESS, config.GMAIL_APP_PASSWORD)
        smtp.send_message(message)


def send(new_items: list[NewsItem], source_failures: list[SourceResult]) -> bool:
    if not new_items:
        return True

    subject = _build_subject(new_items)
    text_body, html_body = _build_body(new_items, source_failures)

    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = config.GMAIL_ADDRESS
    message["To"] = config.GMAIL_ADDRESS
    message.attach(MIMEText(text_body, "plain"))
    message.attach(MIMEText(html_body, "html"))

    try:
        _send(message)
        logger.info("Sent digest email: %s", subject)
        return True
    except Exception:
        logger.exception("Failed to send digest email after retries.")
        return False
