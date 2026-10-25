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
    assert text.startswith("📋 Evening status Thu 22 Oct 2026 — 2 NOT POSTED 🔴")
    assert "ScoreMyBiz Reel\n   YouTube: ✅ Posted\n   Instagram: ✅ Posted" in text
    assert "ScoreMyBiz Post\n   Instagram: ✅ Posted\n   Threads: ✅ Posted\n   LinkedIn" not in text                   # nothing from the apps goes to LinkedIn
    assert "SG-LEARNING Short\n   YouTube: ✅ Posted\n   Instagram: ✅ Posted\n   Threads: ✅ Posted\n   LinkedIn" not in text      # no videos on LinkedIn (founder, 22 Oct 2026)
    assert "SG-MYTH Short\n   YouTube: ✅ Posted\n   Instagram: 🔴 Reel only\n   Threads: 🔴 NOT POSTED" in text
    assert "SG-MYTH long video\n   YouTube: ✅ Posted" in text and "SG-LEARNING long video" not in text
    assert "LinkedIn daily post\n   LinkedIn: ✅ Posted" in text and "📅 Tomorrow Fri 23 Oct (Lagos time)" in text


def test_scheduled_youtube_before_its_time_is_not_called_missing(tmp_path):
    day = date(2026, 10, 22)
    (tmp_path / "pieces").mkdir()
    _piece(tmp_path, "2026-10-22-sglearning-short", "sglearning", "short", day, yt_id="a")
    early = datetime(2026, 10, 22, 10, 0, tzinfo=timezone.utc)
    text = evening.build(day, early, tmp_path, [])
    status = text.split("📅 Tomorrow")[0]
    assert "SG-LEARNING Short\n   YouTube: ⏳ scheduled" in status and "Waypoint" not in status and "ScoreMyBiz" not in status     # Thursday: no app post due (Mon/Wed/Fri)


def test_unreadable_app_log_gives_an_empty_list(monkeypatch):
    def boom(*a, **k):
        raise OSError("offline")
    monkeypatch.setattr(evening.urllib.request, "urlopen", boom)
    assert evening.fetch_app_log() == []


def test_tomorrow_plan_lists_times_in_lagos_time():
    plan = evening.tomorrow_plan(date(2026, 10, 23))                               # tomorrow = Saturday 24 Oct: Learning with SG long day
    assert plan.startswith("📅 Tomorrow Sat 24 Oct (Lagos time)")
    assert "08:10  your daily post, reply in the first hour: LinkedIn" in plan and "09:30  Learning with SG Reel and Story" in plan
    assert "14:30  Learning with SG long video: YouTube" in plan and "15:30  Shorts on both channels: YouTube" in plan
    assert "17:00  SG-MYTH-WORLD Reel and Story" in plan and " set (Reel" not in plan     # Saturday: no app post
    assert "SG-MYTH-WORLD long video" not in plan
    monday = evening.tomorrow_plan(date(2026, 10, 25))
    assert "08:10  your daily post (document), reply in the first hour: LinkedIn" in monday
    assert "15:40  Waypoint set" in monday or "15:40  ScoreMyBiz set" in monday


def test_a_skipped_story_with_no_reel_yet_is_simply_not_posted(tmp_path):
    day = date(2026, 10, 22)
    (tmp_path / "pieces").mkdir()
    _piece(tmp_path, "2026-10-22-arthvan-short", "arthvan", "short", day, yt_id="b", ig_story_id="skipped: Reel over 60 s")
    text = evening.build(day, datetime(2026, 10, 22, 18, 0, tzinfo=timezone.utc), tmp_path, [])
    assert "SG-MYTH Short\n   YouTube: ✅ Posted\n   Instagram: 🔴 NOT POSTED" in text


def test_the_9pm_card_reports_the_founders_lagos_day_not_indias_next_day():
    from datetime import datetime, timezone
    sent = datetime(2026, 10, 22, 20, 3, tzinfo=timezone.utc)          # 21:03 WAT, already 01:33 on 23 Oct in India
    assert evening.card_day(sent).isoformat() == "2026-10-22"


def test_a_card_run_after_midnight_in_lagos_still_reports_the_day_that_ended():
    from datetime import datetime, timezone
    late = datetime(2026, 10, 24, 23, 30, tzinfo=timezone.utc)         # 00:30 WAT on 25 Oct: a late run, the day that ended is still the 24th
    assert evening.card_day(late).isoformat() == "2026-10-24"
    assert evening.card_day(datetime(2026, 10, 25, 3, 59, tzinfo=timezone.utc)).isoformat() == "2026-10-24"   # 04:59 WAT
    assert evening.card_day(datetime(2026, 10, 25, 4, 0, tzinfo=timezone.utc)).isoformat() == "2026-10-25"    # 05:00 WAT: a new day


def test_no_app_rows_on_a_day_without_app_posts():
    from engine import evening
    assert evening._app_rows(date(2026, 10, 25), []) == []                                            # Sunday: no app post due
    rows = evening._app_rows(date(2026, 10, 26), [])                                                   # Monday: due, not out yet
    assert rows and all("NOT POSTED" in v for _n, cells in rows for v in cells.values())
    fest = [{"date": "2026-10-25", "status": "published", "app": "waypoint", "ids": {"reel": "r"}}]
    assert evening._app_rows(date(2026, 10, 25), fest)[0][0] == "Waypoint Reel"                        # a festival post still shows
