import html
import logging
import re
import smtplib
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from tenacity import retry, stop_after_attempt, wait_exponential

from . import config
from .models import NewsItem, SourceResult

logger = logging.getLogger("newswire.email")


# Plain-English names for the SEC forms that come up most often.
FORM_NAMES = {
    "8-K": "a current report (8-K)",
    "10-Q": "its quarterly report (10-Q)",
    "10-K": "its annual report (10-K)",
    "6-K": "a foreign issuer report (6-K)",
    "20-F": "its annual report (20-F)",
    "4": "an insider trading report (Form 4)",
    "S-1": "a registration statement (S-1)",
    "DEF 14A": "its proxy statement (DEF 14A)",
    "SC 13G": "a 5%+ ownership report (SC 13G)",
    "SC 13D": "an activist ownership report (SC 13D)",
}

SOURCE_LABELS = {"EDGAR": "SEC", "YAHOO": "Yahoo"}
# Ticker badge colour by source: blue for news, orange for SEC filings.
BADGE_COLOURS = {"EDGAR": "#b45309", "YAHOO": "#1d4ed8"}
FONT = "font-family:Segoe UI,Arial,sans-serif"
LOCAL_TZ = ZoneInfo("America/Toronto")

# Words highlighted in yellow when they appear in a story.
KEYWORDS = [
    "earnings", "revenue", "profit", "loss", "guidance", "forecast", "outlook",
    "beat", "beats", "miss", "misses", "acquisition", "acquire", "acquires", "merger",
    "takeover", "buyout", "layoffs", "job cuts", "restructuring", "downgrade",
    "downgraded", "upgrade", "upgraded", "price target", "buyback", "repurchase",
    "dividend", "lawsuit", "probe", "investigation", "antitrust", "settlement",
    "partnership", "contract", "IPO", "bankruptcy", "recall", "resigns", "steps down",
    "data center", "data centre",
]
_KEYWORD_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in sorted(KEYWORDS, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)

# "SAN SEBASTIAN, Spain, Oct. 15, 2026 (GLOBE NEWSWIRE) -- " style datelines.
_WIRE_DATELINE = re.compile(
    r"^.*?\((?:GLOBE NEWSWIRE|BUSINESS WIRE|PR NEWSWIRE|ACCESSWIRE|NEWSFILE CORP\.?)[^)]*\)\s*[-–—]+\s*",
    re.IGNORECASE,
)
# "Investing.com -- " style source prefixes.
_SOURCE_PREFIX = re.compile(r"^[A-Z][\w.&' ]{1,30}\s+[-–—]{2,}\s*")
# Words ending in a period that don't end a sentence.
_ABBREVIATIONS = {
    "inc", "corp", "co", "ltd", "llc", "plc", "u.s", "u.k", "mr", "mrs", "ms", "dr",
    "st", "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct",
    "nov", "dec", "no", "vs", "approx", "e.g", "i.e",
}
MAX_SENTENCE_CHARS = 300


def _first_sentence(text: str) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    text = re.sub(r"\s+", " ", text).strip()
    text = _WIRE_DATELINE.sub("", text, count=1)
    text = _SOURCE_PREFIX.sub("", text, count=1)
    for match in re.finditer(r"[.!?](?=\s+[A-Z\"'“])", text):
        last_word = text[: match.start()].rsplit(" ", 1)[-1].lower()
        if last_word in _ABBREVIATIONS or len(last_word) == 1:
            continue
        text = text[: match.end()]
        break
    if len(text) > MAX_SENTENCE_CHARS:
        text = text[:MAX_SENTENCE_CHARS].rsplit(" ", 1)[0] + "…"
    return text


def _sentence_for(item: NewsItem) -> str:
    if item.source == "EDGAR":
        form = item.extra.get("form", "")
        return f"{item.ticker} filed {FORM_NAMES.get(form, f'a {form} form')} with the SEC."
    sentence = _first_sentence(item.extra.get("summary", ""))
    # Fall back to the headline when the feed gave nothing useful.
    if len(sentence) < 20:
        sentence = item.title.strip()
    return sentence


def _when(item: NewsItem) -> str:
    # SEC only gives a filing date, so don't invent a time for it.
    if item.source == "EDGAR":
        return item.published_at.strftime("%a %d %b")
    return item.published_at.astimezone(LOCAL_TZ).strftime("%a %d %b %H:%M")


def _highlight(escaped_text: str) -> str:
    return _KEYWORD_PATTERN.sub(
        r"<b style='background:#fff2a8;padding:0 2px'>\1</b>", escaped_text
    )


def _merge_duplicates(items: list[NewsItem]) -> list[tuple[NewsItem, list[str]]]:
    """One entry per story; a story Yahoo lists under several tickers gets all of them."""
    merged: dict[tuple[str, str], tuple[NewsItem, list[str]]] = {}
    for item in sorted(items, key=lambda i: i.published_at, reverse=True):
        key = (item.source, item.url or item.uid)
        if key in merged:
            if item.ticker not in merged[key][1]:
                merged[key][1].append(item.ticker)
        else:
            merged[key] = (item, [item.ticker])
    return list(merged.values())


def _badge(ticker: str, source: str) -> str:
    colour = BADGE_COLOURS.get(source, "#6b7280")
    return (
        f"<span style='background:{colour};color:#fff;font-size:11px;font-weight:600;"
        f"padding:1px 6px;border-radius:3px;margin-right:4px'>{html.escape(ticker)}</span>"
    )


def _item_html(item: NewsItem, tickers: list[str]) -> str:
    source = SOURCE_LABELS.get(item.source, item.source)
    return (
        "<div style='margin:0 0 16px'>"
        + "".join(_badge(t, item.source) for t in tickers)
        + f" <a href='{html.escape(item.url, quote=True)}' style='color:#0b3d91;font-weight:600;"
        f"font-size:15px;text-decoration:none'>{_highlight(html.escape(_sentence_for(item)))}</a>"
        f"<div style='color:#6b7280;font-size:12px;margin-top:2px'>"
        f"{source} &middot; {_when(item)}</div>"
        "</div>"
    )


def _item_text(item: NewsItem, tickers: list[str]) -> str:
    source = SOURCE_LABELS.get(item.source, item.source)
    tags = " ".join(f"[{t}]" for t in tickers)
    return f"{tags} {_sentence_for(item)}\n  {source} - {_when(item)}\n  {item.url}"


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
    text_lines: list[str] = []
    html_lines: list[str] = [f"<html><body style='{FONT};color:#111827;max-width:700px'>"]

    if source_failures:
        warning = "WARNING: the following sources failed this run: " + ", ".join(
            f"{r.source} ({r.error})" for r in source_failures
        )
        text_lines.append(warning)
        text_lines.append("")
        html_lines.append(f"<p style='color:#b00'><b>{html.escape(warning)}</b></p>")

    for item, tickers in _merge_duplicates(new_items):
        text_lines.append(_item_text(item, tickers))
        text_lines.append("")
        html_lines.append(_item_html(item, tickers))

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
    message["To"] = config.RECIPIENT_EMAIL
    message.attach(MIMEText(text_body, "plain"))
    message.attach(MIMEText(html_body, "html"))

    try:
        _send(message)
        logger.info("Sent digest email: %s", subject)
        return True
    except Exception:
        logger.exception("Failed to send digest email after retries.")
        return False
