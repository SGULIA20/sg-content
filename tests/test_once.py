from datetime import datetime, timedelta, timezone

from engine import once, pieces, produce, publish, watch

NOW = datetime(2026, 12, 2, 8, 0, tzinfo=timezone.utc)


def test_the_same_thing_is_told_once_and_a_change_is_told_at_once(tmp_path):
    """Founder, 24 Nov 2026: 'I am getting n number of duplicate messages on my both bots'."""
    assert once.fresh("thumb-refused:x", "sha1", root=tmp_path, now=NOW) is True
    assert once.fresh("thumb-refused:x", "sha1", root=tmp_path, now=NOW + timedelta(minutes=5)) is False       # the Studio sweep five minutes later
    assert once.fresh("thumb-refused:x", "sha2", root=tmp_path, now=NOW + timedelta(minutes=10)) is True        # a new file: told
    assert once.fresh("thumb-refused:x", "sha2", root=tmp_path, now=NOW + timedelta(hours=21)) is True          # still broken a day later: once more
    assert once.fresh("other", "sha2", root=tmp_path, now=NOW) is True
    assert once.fresh("old", 1, root=tmp_path, now=NOW - timedelta(days=9)) is True
    once.fresh("new", 1, root=tmp_path, now=NOW)
    assert "old" not in (tmp_path / "logs" / "told.json").read_text()                                             # old records are dropped


def test_a_video_is_reviewed_and_reported_once_however_often_it_is_built(tmp_path, monkeypatch):
    from datetime import date
    p = pieces.Piece(id="2026-12-05-arthvan-short", channel="arthvan", kind="short", publish_day=date(2026, 12, 5))
    p.ids["watch"] = {"opening": 5, "verdict": "fix", "issues": 1, "best_change": "x"}
    told = []
    assert watch.look(p, tmp_path / "v.mp4", tmp_path, notify=told.append, ask=lambda c: "{}", grab=lambda *a: None) is None and told == []
