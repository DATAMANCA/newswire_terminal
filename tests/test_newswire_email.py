from datetime import datetime, timezone

from newswire.email_digest import _build_body, _first_sentence
from newswire.models import NewsItem


def _item(source, ticker, published, summary="", form=None, title="Some headline here"):
    extra = {"form": form} if form else {"summary": summary}
    return NewsItem(source, ticker, f"{ticker}-{published}", title, f"https://example.com/{ticker}?b=1&c=2",
                    datetime(2026, 10, 15, published, tzinfo=timezone.utc), extra)


def test_first_sentence_strips_wire_dateline():
    text = ("Subtitle textSAN SEBASTIAN, Spain, Oct. 15, 2026 (GLOBE NEWSWIRE) -- Acme Inc. "
            "today announced a new chip. It is fast.")
    assert _first_sentence(text) == "Acme Inc. today announced a new chip."


def test_first_sentence_strips_source_prefix_and_html():
    text = "Investing.com -- <b>The U.S. government</b> is preparing a deal. More follows."
    assert _first_sentence(text) == "The U.S. government is preparing a deal."


def test_body_is_flat_newest_first_with_badges_and_dates():
    items = [
        _item("YAHOO", "NVDA", 9, summary="Nvidia raised guidance on strong demand. Extra."),
        _item("EDGAR", "VRT", 12, form="8-K"),
        _item("YAHOO", "EQIX", 10, summary="Short."),
    ]
    text, html = _build_body(items, [])
    lines = [line for line in text.splitlines() if line.startswith("[")]
    assert lines == [
        "[VRT] VRT filed a current report (8-K) with the SEC.",
        "[EQIX] Some headline here",
        "[NVDA] Nvidia raised guidance on strong demand.",
    ]
    assert "  SEC - Thu 15 Oct\n" in text  # SEC gives a date only
    assert "  Yahoo - Thu 15 Oct 06:00" in text  # 10:00 UTC shown in Toronto time
    assert "background:#b45309;color:#fff" in html  # SEC badge is orange
    assert "background:#1d4ed8;color:#fff" in html  # Yahoo badge is blue
    assert "padding:0 2px'>guidance</b>" in html
    assert "href='https://example.com/NVDA?b=1&amp;c=2'" in html


def test_same_story_under_two_tickers_is_shown_once_with_both_badges():
    a = _item("YAHOO", "MSFT", 9, summary="Palantir posted strong revenue growth this quarter.")
    b = _item("YAHOO", "PLTR", 9, summary="Palantir posted strong revenue growth this quarter.")
    b.url = a.url
    text, html = _build_body([a, b], [])
    assert text.count("Palantir posted") == 1
    assert "[MSFT] [PLTR] Palantir posted" in text
    assert html.count("Palantir posted") == 1
