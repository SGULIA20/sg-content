from datetime import date
from types import SimpleNamespace

from engine import pieces, themes, topics
from engine.config import CONTENT_DIR


def _piece(root, pid, day, topic, kind="short", status="uploaded"):
    pieces.save(pieces.Piece(id=pid, channel="sglearning", kind=kind, publish_day=day, status=status, topic=topic), root)


def test_theme_from_field_then_keywords():
    assert themes.theme_of({"theme": "gold", "title": "Sensex gira"}) == "gold"
    assert themes.theme_of({"title": "2008: Amreeka ka bank dooba, aapki SIP par kya beeta"}) == "market"
    assert themes.theme_of({"title": "PNB ka 13,000 crore fraud"}) == "scam"
    assert themes.theme_of({"title": "Kuch aur"}) == ""


def test_market_waits_a_week_and_others_three_days(tmp_path):
    (tmp_path / "pieces").mkdir()
    _piece(tmp_path, "a", date(2026, 11, 14), {"title": "500 ki SIP"}, kind="long")
    _piece(tmp_path, "b", date(2026, 11, 17), {"theme": "scam", "title": "x"})
    _piece(tmp_path, "c", date(2026, 11, 18), {"theme": "gold", "title": "y"}, status="rejected")
    new = SimpleNamespace(id="n", channel="sglearning", publish_day=date(2026, 11, 20))
    assert themes.blocked(tmp_path, new) == {"market", "scam"}          # the long counts; a rejected piece does not
    later = SimpleNamespace(id="n", channel="sglearning", publish_day=date(2026, 11, 22))
    assert themes.blocked(tmp_path, later) == set()


def test_bank_skips_blocked_themes_and_every_topic_has_a_theme():
    bank = topics.load_money_history(CONTENT_DIR)
    assert all(t.get("theme") for t in bank)
    assert sum(t["theme"] == "market" for t in bank) <= len(bank) // 4
    t = topics.next_money_history(CONTENT_DIR, set(), date(2026, 11, 20), avoid={"market", "scam"})
    assert t["theme"] not in {"market", "scam"}
    assert topics.next_money_history(CONTENT_DIR, set(), date(2026, 11, 20), avoid={x["theme"] for x in bank}) is None


def test_learning_shorts_never_take_share_market_or_rbi_topics(tmp_path):
    """Founder, 18 Nov 2026: 'Yes drop stock market and RBI headlines from Learning Shorts'. Longs and SG-MYTH are untouched."""
    from datetime import date, datetime, timezone
    from types import SimpleNamespace as NS
    from engine import themes, topics
    assert themes.theme_of({"title": "RBI releases data on ECB for September"}) == "rbi"
    assert themes.theme_of({"title": "Repo rate cut: what happens to your EMI"}) == "rbi"
    assert themes.theme_of({"title": "Bank FD ya post office"}) == "bank"
    short = NS(id="2026-11-27-sglearning-short", channel="sglearning", kind="short", publish_day=date(2026, 11, 27))
    assert {"market", "rbi"} <= themes.blocked(tmp_path, short)
    assert themes.never(NS(id="2026-11-27-sglearning-long", channel="sglearning", kind="long")) == ()
    assert themes.never(NS(id="2026-11-27-arthvan-short", channel="arthvan", kind="short")) == ()
    now = datetime(2026, 11, 26, 12, tzinfo=timezone.utc)
    only = [{"title": "Sensex falls 800 points, what happens to your SIP savings", "link": "u1", "published": now, "summary": ""}]
    got = topics.pick_finance(only, set(), now, news=True, never=themes.NEVER_SHORT)
    assert got is None or themes.theme_of(got) not in themes.NEVER_SHORT          # nothing else left: still not taken


def test_sg_myth_topics_change_theme_from_day_to_day(tmp_path):
    """Founder, 18 Nov 2026: 'every day a new topic, altogether different from the previous one' (six of nine pieces had been Ramayan)."""
    from datetime import date
    from types import SimpleNamespace as NS
    from engine import pieces, themes, topics
    from engine.pieces import Piece
    th = lambda title: themes.theme_of({"title": title}, "arthvan")
    assert th("Jatayu ne Ravan ka rath sach mein toda?") == "ramayan" and th("Prayagraj mein Hanuman ji lete hue kyun hain?") == "ramayan"
    assert th("Karna roz Surya ko arghya dene ke baad kya deta tha?") == "mahabharat" and th("Hampi, Karnataka ke khandhar") == "history"
    assert th("Jagannath mandir ka jhanda roz kaun badalta hai?") == "krishna" and th("Tulsi ka vivah Shaligram se hi kyun hota hai?") == "vishnu"
    pieces.save(Piece(id="2026-11-24-arthvan-short", channel="arthvan", kind="short", publish_day=date(2026, 11, 24), status="uploaded",
                      topic={"id": "x", "title": "Hanuman ka janm sthan, kaun sa sach?"}), tmp_path)
    nxt = NS(id="2026-11-25-arthvan-short", channel="arthvan", kind="short", publish_day=date(2026, 11, 25))
    assert themes.blocked(tmp_path, nxt) == {"ramayan"}
    assert themes.blocked(tmp_path, NS(id="2026-11-27-arthvan-short", channel="arthvan", kind="short", publish_day=date(2026, 11, 27))) == set()
    got = topics.next_myth(topics.CONTENT_DIR, set(), date(2026, 11, 25), avoid={"ramayan", "history"})
    assert themes.theme_of(got, "arthvan") not in ("ramayan", "history")
    assert not themes.allowed({"title": "Sita ki agni pariksha"}, {"ramayan"}, "arthvan")

