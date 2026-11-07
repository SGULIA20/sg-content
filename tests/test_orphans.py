from datetime import datetime, timezone

from engine import orphans, youtube

MOVES = [{"video": "v1", "channel": "sglearning", "kind": "short", "date": "2026-12-03"},
         {"video": "v2", "channel": "arthvan", "kind": "long", "date": "2026-12-03"}]


def test_target_is_the_channel_slot_in_utc():
    assert orphans.target(MOVES[0]) == datetime(2026, 12, 3, 14, 30, tzinfo=timezone.utc)
    assert orphans.target(MOVES[1]) == datetime(2026, 12, 3, 13, 30, tzinfo=timezone.utc)


def test_check_moves_nothing_and_apply_moves_free_slots_only():
    moved = []
    kw = dict(token_for=lambda ch: ch, reschedule=lambda t, v, w: moved.append(v) or True, out=lambda *_: None)
    r = orphans.run(MOVES, apply=False, scheduled_at=lambda t, w: [], **kw)
    assert moved == [] and r["moved"] == []
    r = orphans.run(MOVES, apply=True, scheduled_at=lambda t, w: ["other"] if t == "arthvan" else [], **kw)
    assert moved == ["v1"] and r["blocked"] == ["v2"]


def test_a_video_already_on_its_new_day_is_left_alone_and_a_failure_is_reported():
    moved = []
    kw = dict(token_for=lambda ch: ch, out=lambda *_: None)
    r = orphans.run(MOVES, apply=True, scheduled_at=lambda t, w: ["v1", "v2"], reschedule=lambda *a: moved.append(a), **kw)
    assert moved == [] and r["already"] == ["v1", "v2"]
    r = orphans.run(MOVES[:1], apply=True, scheduled_at=lambda t, w: [], reschedule=lambda *a: False, **kw)
    assert r["failed"] == ["v1"]


def test_the_real_plan_has_sixteen_videos_and_never_two_in_one_slot():
    plan = orphans.load_plan()
    assert len(plan) == 16
    slots_used = [orphans.target(m) + __import__("datetime").timedelta(0) for m in plan]
    keys = [(m["channel"], t) for m, t in zip(plan, slots_used)]
    assert len(set(keys)) == 16 and len({m["video"] for m in plan}) == 16
    assert all(m["date"] >= "2026-12-02" and m["date"] <= "2027-03-04" for m in plan)
    unakoti = sorted(m["date"] for m in plan if m["video"] in {"aqlBCko_79E", "jcRNBbYeBpE", "alnSQTKBWpg", "lzhCLhq0qbA", "DZXTbCfU__0", "eA822xFSovc", "FJdS2ZliCF0"})
    from datetime import date
    gaps = [(date.fromisoformat(b) - date.fromisoformat(a)).days for a, b in zip(unakoti, unakoti[1:])]
    assert len(unakoti) == 7 and min(gaps) >= 14                                   # the same story never twice within two weeks


def test_scheduled_at_lists_private_videos_at_that_minute_and_never_raises():
    when = datetime(2026, 12, 3, 14, 30, tzinfo=timezone.utc)

    def call(method, url, token, **kw):
        if "channels" in url:
            return 200, {}, {"items": [{"contentDetails": {"relatedPlaylists": {"uploads": "UP"}}}]}
        if "playlistItems" in url:
            return 200, {}, {"items": [{"contentDetails": {"videoId": "a"}}, {"contentDetails": {"videoId": "b"}}, {"contentDetails": {"videoId": "c"}}]}
        return 200, {}, {"items": [{"id": "a", "status": {"privacyStatus": "private", "publishAt": "2026-12-03T14:30:00Z"}},
                                   {"id": "b", "status": {"privacyStatus": "private", "publishAt": "2026-12-04T14:30:00Z"}},
                                   {"id": "c", "status": {"privacyStatus": "public"}}]}
    assert youtube.scheduled_at("t", when, call=call) == ["a"]
    assert youtube.scheduled_at("t", when, call=lambda *a, **k: (500, {}, {})) == []
    def boom(*a, **k): raise OSError("x")
    assert youtube.scheduled_at("t", when, call=boom) == []
