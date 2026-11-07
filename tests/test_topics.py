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
    # the rest: "Sensex ends flat" is the day's index move (30 Oct 2026), the repo-rate item is 9 days old, the rally is banned
    assert topics.pick_finance(items, used_links={best["link"]}, now=NOW) is None


def test_myth_rotation_skips_used_and_wraps(tmp_path):
    (tmp_path / "myth-topics.yaml").write_text(
        "- id: dwarka\n  title_hi: Dwarka\n  hooks: [a, b, c]\n  allowed_sources: [x]\n"
        "- id: ramsetu\n  title_hi: Ram Setu\n  hooks: [a, b, c]\n  allowed_sources: [x]\n")
    from datetime import date
    quiet = date(2027, 3, 1)                                               # no festival window: ties keep the bank's order
    assert topics.next_myth(tmp_path, used_ids=set(), today=quiet)["id"] == "dwarka"
    assert topics.next_myth(tmp_path, used_ids={"dwarka"}, today=quiet)["id"] == "ramsetu"
    assert topics.next_myth(tmp_path, used_ids={"dwarka", "ramsetu"}, today=quiet)["id"] == "dwarka"


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
    ipo = {"title": "Home loan EMI to fall as banks cut rates by 0.25%", "link": "https://x/3", "summary": "", "published": NOW, "source": "Mint", "rank": 3}
    assert topics.pick_finance([rbi, mmo, ipo], set(), NOW)["link"] == "https://x/3"
    assert topics.pick_finance([rbi, mmo], set(), NOW) is None


def test_long_bank_rotates_in_order(tmp_path):
    (tmp_path / "long-topics.yaml").write_text("- id: a\n  title: A\n  summary: s\n  hooks: [h]\n- id: b\n  title: B\n  summary: s\n  hooks: [h]\n")
    assert topics.next_long_finance(tmp_path, set())["id"] == "a"
    assert topics.next_long_finance(tmp_path, {"a"})["id"] == "b"
    assert topics.next_long_finance(tmp_path, {"a", "b"})["id"] == "a"


def test_real_long_bank_has_ten_sourced_topics():
    bank = topics.load_long_bank()
    assert len(bank) >= 10 and all(t["id"] and t["title"] and t["summary"] and len(t["hooks"]) == 3 for t in bank)


def test_stock_tip_headlines_are_never_topics():
    for title in ("Stocks in news: Reliance, Eternal, Alkem Labs", "5 stocks to buy today", "Top picks for Diwali"):
        assert topics.score({"title": title, "summary": "market", "published": None}) < 0


def test_wallet_news_beats_market_news_of_the_same_rank():
    from engine import topics
    wallet = {"title": "Petrol price cut by 2 rupees from today", "summary": "", "rank": 3}
    market = {"title": "Meta profit results beat estimates by 10%", "summary": "", "rank": 3}
    assert topics.score(wallet) > 0 >= topics.score(market)                 # 4 Nov 2026: company results are never a Reel


def test_famous_myth_topics_go_first_then_bank_order(tmp_path):
    from engine import topics
    (tmp_path / "myth-topics.yaml").write_text("- id: a\n- id: b\n  priority: 1\n- id: c\n  priority: 1\n")
    assert topics.next_myth(tmp_path, set())["id"] == "b"
    assert topics.next_myth(tmp_path, {"b"})["id"] == "c"
    assert topics.next_myth(tmp_path, {"b", "c"})["id"] == "a"
    assert topics.next_myth(tmp_path, {"a", "b", "c"})["id"] == "a"


def test_the_days_index_move_is_never_a_topic():
    from engine import topics
    assert topics.score({"title": "Sensex 829 upar, phir bhi loss kyun?", "summary": "salary EMI", "rank": 5}) < 0
    assert topics.score({"title": "Petrol price cut by Rs 2", "summary": "", "rank": 1}) > 0


def test_routine_notices_are_not_topics():
    from engine import topics
    assert topics.score({"title": "Premature redemption under Sovereign Gold Bond (SGB) Scheme - Redemption Price for premature redemption of SGB 2021-22 Series", "summary": "gold", "rank": 5}) < 0


def test_company_deal_and_crypto_news_is_never_a_learning_reel():
    """4 Nov 2026 (founder: "B"): Vodafone's new owner got 4 Instagram views, Binance hack 5, charity rules 3; gold on Dhanteras 1,923."""
    from engine import topics
    for title in ("Vodafone Idea: French billionaire buys 16.2% stake", "Binance hack: record theft, 90% recovered",
                  "Charity trust rules change after merger", "Jio Platforms IPO draws Rs 8,110 crore anchor bids", "Nvidia chip sales hit record"):
        assert topics.score({"title": title, "summary": "", "rank": 5}) <= 0, title
    for title in ("Gold price falls 21% from January: buy on Dhanteras?", "US stocks from $1 on Zerodha: the real cost",
                  "Dividend of Rs 6.50: why the share fell the next day", "Petrol price cut by Rs 2", "Infosys lays off 2,000 employees"):
        assert topics.score({"title": title, "summary": "", "rank": 1}) > 0, title


def _proven_root(tmp_path):
    import json
    from engine import pieces
    (tmp_path / "logs").mkdir(); (tmp_path / "content").mkdir()
    (tmp_path / "logs" / "whatworks.json").write_text(json.dumps({"week": [
        {"id": "2026-10-30-sglearning-short", "channel": "sglearning", "title": "Gold price gira, Dhanteras par khareedna sahi?", "ig_views": 1923, "yt_views": 32},
        {"id": "2026-10-26-arthvan-short", "channel": "arthvan", "title": "Mahabharat kab hua?", "ig_views": 1396, "yt_views": 344},
        {"id": "2026-10-27-sglearning-short", "channel": "sglearning", "title": "Sensex gira", "ig_views": 55, "yt_views": 11}]}))
    (tmp_path / "logs" / "diagnosis.json").write_text(json.dumps({"rows": [
        {"id": "2026-10-21-arthvan-short", "channel": "arthvan", "title": "Ram Setu: 103 reefs?", "ig_views": 1585, "yt_views": 42},
        {"id": "2026-10-30-sglearning-short", "channel": "sglearning", "title": "Gold price gira, Dhanteras par khareedna sahi?", "ig_views": 1500, "yt_views": 30}]}))
    for pid, ch, topic, hook in (("2026-10-30-sglearning-short", "sglearning", {"link": "https://m/gold", "summary": "Gold fell 21% since January.", "source": "Mint"}, "Gold 21% gira, pata tha?"),
                                 ("2026-10-26-arthvan-short", "arthvan", {"id": "mahabharata-date"}, "Kya tareekh taaron mein likhi hai?"),
                                 ("2026-10-21-arthvan-short", "arthvan", {"id": "ram-setu"}, "Pul aaj bhi dikhta hai?")):
        p = pieces.Piece(id=pid, channel=ch, kind="short", publish_day=__import__("datetime").date.fromisoformat(pid[:10]), status="posted")
        p.topic = topic; p.script = {"hook": hook}; pieces.save(p, tmp_path)
    (tmp_path / "content" / "long-topics.yaml").write_text("- id: bank-a\n  title: A\n- id: bank-b\n  title: B\n")
    (tmp_path / "content" / "myth-topics.yaml").write_text("- id: ram-setu\n  title_hi: Ram Setu\n  priority: 1\n- id: mahabharata-date\n  title_hi: Mahabharat\n- id: other\n  title_hi: Other\n  priority: 1\n")
    return tmp_path


def test_proven_shorts_are_the_ones_that_reached_a_thousand_on_instagram(tmp_path):
    """4 Nov 2026 (founder: "D"): the next longs are made on the questions the Shorts proved."""
    from engine import topics
    root = _proven_root(tmp_path)
    gold = topics.proven_shorts(root, "sglearning")
    assert [s["id"] for s in gold] == ["2026-10-30-sglearning-short"] and gold[0]["ig_views"] == 1923 and gold[0]["hook"].startswith("Gold")
    assert [s["id"] for s in topics.proven_shorts(root, "arthvan")] == ["2026-10-21-arthvan-short", "2026-10-26-arthvan-short"]


def test_the_finance_long_takes_the_proven_question_first_then_the_bank(tmp_path):
    from engine import topics
    root = _proven_root(tmp_path); content = root / "content"
    proven = topics.proven_shorts(root, "sglearning")
    t = topics.next_long_finance(content, set(), proven)
    assert t["id"] == "proven-2026-10-30-sglearning-short" and t["link"] == "https://m/gold" and t["hooks"] == ["Gold 21% gira, pata tha?"]
    assert "1,923" in t["summary"] and "Gold fell 21%" in t["summary"] and t["proven_views"] == 1923
    assert topics.next_long_finance(content, {t["id"]}, proven)["id"] == "bank-a"            # once made, the bank as before
    crypto = [{"id": "x", "title": "Google aur Bitcoin ek saath kyun gire?", "ig_views": 1221, "topic": {}, "hook": ""}]
    assert topics.next_long_finance(content, set(), crypto)["id"] == "bank-a"                # rule B holds for longs too
    assert topics.next_long_finance(content, set(), [])["id"] == "bank-a"


def test_the_myth_long_takes_the_proven_shorts_bank_topic_first_then_the_rotation(tmp_path):
    from engine import topics
    root = _proven_root(tmp_path); content = root / "content"
    proven = topics.proven_shorts(root, "arthvan")
    t = topics.next_myth_long(content, {"ram-setu", "mahabharata-date"}, proven)      # the Shorts used the bank ids; the long still comes
    assert t["id"] == "ram-setu#long" and t["title_hi"] == "Ram Setu" and t["proven_short"] == "2026-10-21-arthvan-short"
    assert topics.next_myth_long(content, {"ram-setu#long"}, proven)["id"] == "mahabharata-date#long"
    assert topics.next_myth_long(content, {"ram-setu", "mahabharata-date", "ram-setu#long", "mahabharata-date#long"}, proven)["id"] == "other"
    assert topics.next_myth_long(content, set(), [])["id"] in ("ram-setu", "other")


def test_every_other_learning_short_comes_from_the_money_history_bank():
    """Founder, 6 Nov 2026: wars, attacks, scams and price history of the last 45 years; no more SIP, gold, oil on repeat."""
    from datetime import date
    from engine.config import CONTENT_DIR
    bank = topics.load_money_history(CONTENT_DIR)
    assert len(bank) >= 30 and len({t["id"] for t in bank}) == len(bank)
    assert all(t.get("title") and t.get("summary") and t.get("hooks") and t.get("category") for t in bank)
    assert len({t["category"] for t in bank}) >= 6                                   # war, attack, crash, scam, policy, sensation, price-history
    assert topics.history_day(date(2026, 11, 14)) != topics.history_day(date(2026, 11, 15))
    from engine import topicscore
    ranked = topicscore.rank(bank, "sglearning")                                        # 7 Nov 2026: the YouTube-based rule orders the bank
    first = topics.next_money_history(CONTENT_DIR, set())
    assert first["id"] == ranked[0][2]["id"] and first["history"] is True and first["topic_score"] == ranked[0][0] and first["topic_score_why"]
    assert topics.next_money_history(CONTENT_DIR, {t["id"] for t in bank}) is None     # every topic used: the news feed takes over
    assert topics.next_money_history(CONTENT_DIR, {ranked[0][2]["id"]})["id"] == ranked[1][2]["id"]


def test_topic_scoring_rule_prefers_scares_with_money_and_famous_shock_questions():
    from datetime import date
    from engine import topicscore
    quiet = date(2027, 3, 1)
    crash, _ = topicscore.score("Gold silver crash: ₹33,710 sasta, abhi khareedein ya rukein?", "sglearning", quiet)
    results, _ = topicscore.score("Reliance net profit rises 7% in Q2 results", "sglearning", quiet)
    roundup, _ = topicscore.score("Top 10 badi khabrein aaj ki", "sglearning", quiet)
    assert crash >= 9 and results < 0 and roundup < 0
    vishnu, _ = topicscore.score("Bhagwan Vishnu ka sir kaise kata? Hayagriva ka rahasya", "arthvan", quiet)
    obscure, _ = topicscore.score("Ek chhote gaon ki purani baoli", "arthvan", quiet)
    assert vishnu >= 8 and obscure < 2
    assert topicscore.score("Modi ke election ki baat", "sglearning", quiet)[0] == -10


def test_a_festival_boosts_only_matching_stories_inside_its_window():
    from datetime import date
    from engine import topicscore
    cal = [{"date": "2026-11-08", "name": "Diwali", "lead_days": 5, "after_days": 2, "terms": ["lakshmi", "ganesh"]}]
    inside, why = topicscore.score("Lakshmi ji ki kahani: kaise aayi?", "arthvan", date(2026, 11, 6), cal)
    outside, _ = topicscore.score("Lakshmi ji ki kahani: kaise aayi?", "arthvan", date(2026, 12, 6), cal)
    other, _ = topicscore.score("Kedarnath ki deewar kaise bachi?", "arthvan", date(2026, 11, 6), cal)
    assert inside == outside + 3 and any("Diwali" in w for w in why) and not any("timely" in w for w in topicscore.score("Kedarnath ki deewar kaise bachi?", "arthvan", date(2026, 11, 6), cal)[1])
