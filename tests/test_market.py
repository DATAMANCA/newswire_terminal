from datetime import datetime, timedelta, timezone

from newswire.email_digest import _first_sentence, _sentence_for
from newswire.market import main, sec_current, state, universe
from newswire.models import NewsItem

NOW = datetime(2026, 10, 15, 18, 0, tzinfo=timezone.utc)


def _row(symbol, name, cap=5e8, country="United States", industry="Major Banks", sector="Finance"):
    return {"symbol": symbol, "name": name, "marketCap": str(cap), "country": country,
            "industry": industry, "sector": sector}


def test_universe_keeps_common_stock_and_drops_the_rest():
    rows = [
        _row("JPM", "JPMorgan Chase & Co. Common Stock", cap=7e11),
        _row("EPD", "Enterprise Products Partners L.P. Common Units", industry="Pipelines"),
        _row("UHT", "Universal Health Realty Income Trust", industry="Real Estate Investment Trusts"),
        _row("BRK/B", "Berkshire Hathaway Inc.", cap=1e12),
        _row("TINY", "Tiny Corp", cap=5e7),
        _row("SHOP", "Shopify Inc.", country="Canada"),
        _row("CMSA", "CMS Energy Corporation 5.625% Junior Subordinated Notes due 2078"),
        _row("AGNCL", "AGNC Investment Corp. Depositary Shares"),
        _row("BULLW", "Webull Corporation Warrants"),
        _row("TACO", "Berto Acquisition Corp. Ordinary Shares", industry=""),
        _row("DSL", "DoubleLine Income Solutions Fund Common Shares"),
        _row("PBT", "Permian Basin Royalty Trust Common Stock", industry="Oil & Gas Production"),
        _row("MSFT", "Microsoft Corporation Common Stock", cap=4e12, sector="Technology"),
        _row("ODD", "Odd Co", sector=""),
    ]
    companies = universe.build(rows, exclude={"MSFT"})
    assert [c.ticker for c in companies] == ["BRK-B", "JPM", "EPD", "UHT", "ODD"]
    assert companies[0].is_large and not companies[2].is_large
    assert companies[-1].sector == universe.OTHER_SECTOR


def _entry(title, summary="", accession="0000000000-26-000001", updated=(2026, 10, 15, 17, 0, 0)):
    return {"title": title, "summary": summary, "id": f"urn:tag:sec.gov,2008:accession-number={accession}",
            "link": "https://www.sec.gov/x-index.htm", "updated_parsed": updated}


def test_sec_entry_becomes_item_with_8k_topics():
    entry = _entry(
        "8-K - Example Bank Corp (0000012345) (Filer)",
        "<b>Filed:</b> 2026-10-15 <br />Item 2.02: Results of Operations and Financial Condition"
        " <br />Item 9.01: Financial Statements and Exhibits",
    )
    item = sec_current.parse_entry(entry, {"0000012345": "EXB"})
    assert item.ticker == "EXB" and item.uid == "0000000000-26-000001"
    assert _sentence_for(item) == (
        "EXB filed a current report (8-K) with the SEC: Results of Operations and Financial Condition."
    )
    assert sec_current.parse_entry(entry, {}) is None  # not on the list


def test_13d_uses_the_subject_company_and_names_the_investor():
    filer = _entry("SCHEDULE 13D/A - Big Investor LLC (0000099999) (Filed by)")
    subject = _entry("SCHEDULE 13D/A - Target Inc. (0000012345) (Subject)")
    mapping = {"0000012345": "TGT1", "0000099999": "BIGI"}
    assert sec_current.parse_entry(filer, mapping) is None
    item = sec_current.parse_entry(subject, mapping)
    assert item.ticker == "TGT1"
    item.extra["filed_by"] = sec_current._investor(filer)[1]
    assert _sentence_for(item) == "Big Investor LLC updated its 5%+ stake in TGT1 (SCHEDULE 13D/A)."


def _news(ticker, uid, hours_ago=1, source="YAHOO"):
    return NewsItem(source, ticker, uid, "Headline", f"https://example.com/{uid}",
                    NOW - timedelta(hours=hours_ago), {"summary": "Something happened at the company today."})


def test_first_check_is_silent_then_only_new_fresh_stories_are_reported():
    data = state.empty()
    first = state.find_new(data, [_news("A", "s1", source="EDGAR")], [_news("A", "y1")], ["A"], now=NOW)
    assert first == []

    sec = [_news("A", "s1", source="EDGAR"), _news("A", "s2", source="EDGAR")]
    yahoo = [_news("A", "y1"), _news("A", "y2"), _news("A", "old", hours_ago=24 * 5), _news("B", "b1")]
    second = state.find_new(data, sec, yahoo, ["A", "B"], now=NOW)
    assert sorted(i.uid for i in second) == ["s2", "y2"]  # B is new to the list, so only learned

    third = state.find_new(data, [], [_news("B", "b1"), _news("B", "b2")], ["B"], now=NOW)
    assert [i.uid for i in third] == ["b2"]


def test_failed_sec_fetch_does_not_mark_sec_as_learned():
    data = state.empty()
    state.find_new(data, None, [], [], now=NOW)
    assert data["sec_seeded"] is False


def test_prune_forgets_old_stories_and_dropped_tickers():
    data = state.empty()
    data["seen"] = {"old": "2026-09-01", "new": "2026-10-14"}
    data["yahoo_seeded"] = ["A", "GONE"]
    state.prune(data, {"A"}, now=NOW)
    assert data["seen"] == {"new": "2026-10-14"}
    assert data["yahoo_seeded"] == ["A"]


def test_big_sector_is_split_into_parts_and_large_caps_come_first(monkeypatch):
    companies = [universe.Company("BIG", "Big", "Technology", 5e11),
                 universe.Company("SML", "Small", "Technology", 5e8),
                 universe.Company("BNK", "Bank", "Finance", 5e8)]
    items = [_news("SML", f"s{i}", hours_ago=0.1) for i in range(5)]
    items += [_news("BIG", "b1", hours_ago=2), _news("BNK", "f1")]
    sent = []
    monkeypatch.setattr(main.config, "MARKET_MAX_ITEMS_PER_EMAIL", 4)
    monkeypatch.setattr(main.time, "sleep", lambda s: None)
    monkeypatch.setattr(main.email_digest, "deliver", lambda subject, text, html: sent.append((subject, text)) or True)

    count, ok = main.send_sector_emails(items, companies, [])
    assert ok and count == 3
    subjects = [s for s, _ in sent]
    assert subjects[0].startswith("Newswire Finance: 1 new item(s)")
    assert subjects[1].startswith("Newswire Technology (1/2): 4 new item(s)")
    assert subjects[2].startswith("Newswire Technology (2/2): 2 new item(s)")
    assert sent[1][1].startswith("[BIG]")  # the large company leads despite being older


def test_rotation_checks_a_slice_of_small_companies_each_run(monkeypatch):
    companies = [universe.Company("L", "L", "Technology", 5e11)] + [
        universe.Company(f"S{i}", "S", "Technology", 5e8) for i in range(5)
    ]
    data = state.empty()
    monkeypatch.setattr(main.config, "MARKET_YAHOO_SMALL_PER_RUN", 2)
    assert main._yahoo_tickers(companies, data) == ["L", "S0", "S1"]
    assert main._yahoo_tickers(companies, data) == ["L", "S2", "S3"]
    assert main._yahoo_tickers(companies, data) == ["L", "S4", "S0"]


def test_plain_dateline_is_removed():
    text = ("ETOBICOKE, Ontario, October 15, 2026--CDW Canada, a leading provider, announced today "
            "that it won an award. More text.")
    assert _first_sentence(text) == "CDW Canada, a leading provider, announced today that it won an award."
