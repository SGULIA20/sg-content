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
