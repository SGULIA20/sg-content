from datetime import datetime, timezone
from pathlib import Path

from engine import topics

FIXTURE = Path(__file__).parent / "fixtures" / "et-markets.xml"
NOW = datetime(2026, 10, 19, 18, 0, tzinfo=timezone.utc)


def _items():
    return topics.parse_feed(FIXTURE.read_bytes(), source="ET Markets", rank=3)


def test_parse_rss_fixture_yields_items():
    items = _items()
    assert len(items) == 4
    first = items[0]
    assert first["title"].startswith("Crude oil crosses $100")
    assert first["link"].endswith("101.cms")
    assert first["source"] == "ET Markets"
    assert first["published"] == datetime(2026, 10, 19, 3, 45, tzinfo=timezone.utc)


def test_parse_atom_feed():
    atom = b"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><title>SEBI</title>
    <entry><title>SEBI fines broker Rs 10 lakh</title><link href="https://www.sebi.gov.in/x/1"/>
    <updated>2026-10-19T10:00:00Z</updated><summary>Order against a broker.</summary></entry></feed>"""
    items = topics.parse_feed(atom, source="SEBI", rank=5)
    assert items[0]["link"] == "https://www.sebi.gov.in/x/1" and items[0]["published"].hour == 10


def test_score_prefers_number_and_household_keyword():
    items = {i["link"][-7:]: i for i in _items()}
    crude, sensex, rally = items["101.cms"], items["102.cms"], items["103.cms"]
    assert topics.score(crude) > topics.score(sensex)
    assert topics.score(rally) < 0


def test_pick_skips_used_and_old():
    items = _items()
    best = topics.pick_finance(items, used_links=set(), now=NOW)
    assert best["link"].endswith("101.cms")
    second = topics.pick_finance(items, used_links={best["link"]}, now=NOW)
    assert second["link"].endswith("102.cms")           # the repo-rate item is 9 days old, the rally is banned
    assert topics.pick_finance(items, used_links={best["link"], second["link"]}, now=NOW) is None


def test_myth_rotation_skips_used_and_wraps(tmp_path):
    (tmp_path / "myth-topics.yaml").write_text(
        "- id: dwarka\n  title_hi: Dwarka\n  hooks: [a, b, c]\n  allowed_sources: [x]\n"
        "- id: ramsetu\n  title_hi: Ram Setu\n  hooks: [a, b, c]\n  allowed_sources: [x]\n")
    assert topics.next_myth(tmp_path, used_ids=set())["id"] == "dwarka"
    assert topics.next_myth(tmp_path, used_ids={"dwarka"})["id"] == "ramsetu"
    assert topics.next_myth(tmp_path, used_ids={"dwarka", "ramsetu"})["id"] == "dwarka"


def test_bank_has_forty_topics_with_three_hooks():
    bank = topics.load_myth_bank()
    assert len(bank) >= 40
    assert all(len(t["hooks"]) == 3 and t["allowed_sources"] for t in bank)
    assert len({t["id"] for t in bank}) == len(bank)


def test_feeds_list_names_seven_sources():
    assert len(topics.FEEDS) >= 7 and all(url.startswith("https://") for _n, url, _r in topics.FEEDS)


def test_pick_ignores_items_without_household_angle():
    items = [{"title": "RBI to conduct Overnight Variable Rate Repo auction under LAF", "link": "https://x/1", "summary": "", "published": NOW, "source": "RBI", "rank": 5},
             {"title": "Petrol price cut by Rs 2 a litre from tonight", "link": "https://x/2", "summary": "", "published": NOW, "source": "ET", "rank": 3}]
    assert topics.pick_finance(items, set(), NOW)["link"] == "https://x/2"
    assert topics.pick_finance(items[:1], set(), NOW) is None


def test_pick_pushes_rbi_plumbing_below_household_news():
    rbi = {"title": "Result of the 7-day Variable Rate Repo (VRR) auction held on October 19, 2026", "link": "https://x/1", "summary": "", "published": NOW, "source": "RBI", "rank": 5}
    mmo = {"title": "Money Market Operations as on October 16, 2026", "link": "https://x/2", "summary": "", "published": NOW, "source": "RBI", "rank": 5}
    ipo = {"title": "Jio Platforms IPO draws Rs 8,110 crore in anchor investor bids; LIC among investors", "link": "https://x/3", "summary": "", "published": NOW, "source": "Mint", "rank": 3}
    assert topics.pick_finance([rbi, mmo, ipo], set(), NOW)["link"] == "https://x/3"
    assert topics.pick_finance([rbi, mmo], set(), NOW) is None
