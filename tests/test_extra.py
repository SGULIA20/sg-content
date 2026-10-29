from datetime import date, datetime, timezone
from pathlib import Path

from engine import extra, pieces, pipeline, publish

NOW = datetime(2026, 10, 29, 13, 30, tzinfo=timezone.utc)                      # 19:00 India


class D:
    topic = None


def test_an_extra_reel_gets_its_own_id_and_slot_and_keeps_the_chosen_story(tmp_path, monkeypatch):
    seen = {}
    def make(piece, deps, root, dry_run=False):
        seen["topic"] = pipeline._pick_topic(piece, deps, root, set())
        assert deps.topic(piece, set()) is None                                    # no other story slips in
        piece.topic = dict(seen["topic"]); piece.status = "uploaded"; pieces.save(piece, root); return piece
    monkeypatch.setattr(pipeline, "make", make)
    p = extra.make({"title": "Innodata layoffs: your rights", "link": "https://x"}, tmp_path, NOW, deps=D(), notify=lambda t: None)
    assert p.id == "2026-10-29-sglearning-x1" and p.topic["slot_ist"] == "19:15" and seen["topic"]["link"] == "https://x"
    assert extra.next_id(tmp_path, date(2026, 10, 29)) == "2026-10-29-sglearning-x2"


def test_an_extra_reel_posts_at_its_own_slot_not_the_channels(tmp_path):
    p = pieces.Piece(id="2026-10-29-sglearning-x1", channel="sglearning", kind="short", publish_day=date(2026, 10, 29), status="uploaded")
    p.topic = {"slot_ist": "22:45"}; p.ids = {"yt_id": "y", "out_sha": "a"}
    pieces.save(p, tmp_path)
    assert publish.due(tmp_path, datetime(2026, 10, 29, 15, 30, tzinfo=timezone.utc), "sglearning") == []      # 21:00 India: not yet
    assert [q.id for q in publish.due(tmp_path, datetime(2026, 10, 29, 17, 15, tzinfo=timezone.utc), "sglearning")] == [p.id]


def test_jobs_news_scores_like_the_wallet():
    from engine import topics
    item = {"title": "US AI firm Innodata lays off 550 employees in India", "summary": "", "link": "l", "rank": 0}
    assert topics.score(item) >= 4 and topics.household(item)
