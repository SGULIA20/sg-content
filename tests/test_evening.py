from datetime import date, datetime, timezone

from engine import evening, pieces


def _piece(root, pid, channel, kind, day, **ids):
    p = pieces.Piece(id=pid, channel=channel, kind=kind, publish_day=day)
    p.ids = dict(ids)
    p.status = "posted" if ids else "assembled"
    pieces.save(p, root)
    return p


APP_LOG = [
    {"date": "2026-10-22", "app": "scoremybiz", "status": "published", "kind": "set", "ids": {"post": "1", "reel": "2", "story": "3"}},
    {"date": "2026-10-22", "channel": "youtube:sglearning", "status": "published", "id": "y1"},
    {"date": "2026-10-22", "channel": "threads", "status": "published", "id": "t1"},
    {"date": "2026-10-22", "channel": "linkedin_personal", "status": "published", "id": "urn:1"},
    {"date": "2026-10-21", "channel": "linkedin", "status": "published", "id": "old"},
]


def test_apps_alternate_from_the_waypoint_epoch():
    assert evening.app_for(date(2026, 10, 11)) == "waypoint" and evening.app_for(date(2026, 10, 22)) == "scoremybiz"


def test_scorecard_marks_each_cell_posted_or_not(tmp_path):
    day = date(2026, 10, 22)                                                  # Thursday: SG-MYTH long day, both Shorts, ScoreMyBiz app day
    (tmp_path / "pieces").mkdir()
    _piece(tmp_path, "2026-10-22-sglearning-short", "sglearning", "short", day, yt_id="a", ig_reel_id="r", ig_story_id="s", threads_id="t", linkedin_id="l")
    _piece(tmp_path, "2026-10-22-arthvan-short", "arthvan", "short", day, yt_id="b", ig_reel_id="r")
    _piece(tmp_path, "2026-10-22-arthvan-long", "arthvan", "long", day, yt_id="c")
    late = datetime(2026, 10, 22, 18, 0, tzinfo=timezone.utc)                # 23:30 IST, after every slot
    text = evening.build(day, late, tmp_path, APP_LOG)
    assert text.startswith("📋 Evening status Thu 22 Oct 2026 — 4 NOT POSTED 🔴")
    assert "ScoreMyBiz Reel\n   YouTube: ✅ Posted\n   Instagram: ✅ Posted" in text
    assert "ScoreMyBiz Post\n   Instagram: ✅ Posted\n   Threads: ✅ Posted\n   LinkedIn: 🔴 NOT POSTED" in text   # yesterday's LinkedIn does not count
    assert "SG-LEARNING Short\n   YouTube: ✅ Posted\n   Instagram: ✅ Posted\n   Threads: ✅ Posted\n   LinkedIn: ✅ Posted" in text
    assert "SG-MYTH Short\n   YouTube: ✅ Posted\n   Instagram: 🔴 Reel only\n   Threads: 🔴 NOT POSTED" in text
    assert "SG-MYTH long video\n   YouTube: ✅ Posted" in text and "SG-LEARNING long video" not in text
    assert text.endswith("LinkedIn daily post\n   LinkedIn: ✅ Posted")


def test_scheduled_youtube_before_its_time_is_not_called_missing(tmp_path):
    day = date(2026, 10, 22)
    (tmp_path / "pieces").mkdir()
    _piece(tmp_path, "2026-10-22-sglearning-short", "sglearning", "short", day, yt_id="a")
    early = datetime(2026, 10, 22, 10, 0, tzinfo=timezone.utc)
    text = evening.build(day, early, tmp_path, [])
    assert "SG-LEARNING Short\n   YouTube: ⏳ scheduled" in text and "Waypoint" not in text and "ScoreMyBiz Reel\n   YouTube: 🔴 NOT POSTED" in text


def test_unreadable_app_log_gives_an_empty_list(monkeypatch):
    def boom(*a, **k):
        raise OSError("offline")
    monkeypatch.setattr(evening.urllib.request, "urlopen", boom)
    assert evening.fetch_app_log() == []
