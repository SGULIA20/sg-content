from datetime import date, datetime, timedelta, timezone

from engine import pieces, slots, thumbtest


def _long(root, day=date(2026, 10, 24)):
    p = pieces.Piece(id=f"{day.isoformat()}-sglearning-long", channel="sglearning", kind="long", publish_day=day, status="uploaded")
    p.ids = {"yt_id": "L1"}
    pieces.save(p, root)
    out = root / "out" / p.id
    out.mkdir(parents=True)
    (out / "thumb.jpg").write_bytes(b"a"); (out / "thumb_b.jpg").write_bytes(b"b")
    return p


def test_b_goes_up_after_two_days_and_the_better_click_rate_stays(tmp_path):
    p = _long(tmp_path)
    public = slots.publish_at("sglearning", "long", p.publish_day)
    set_to = []
    st = lambda tok, vid, jpg: set_to.append(jpg.name) or True
    assert thumbtest.step(p, public + timedelta(days=1), "t", tmp_path, set_thumb=st) == ""
    assert "B is up" in thumbtest.step(p, public + timedelta(days=2, hours=1), "t", tmp_path, set_thumb=st)
    p = pieces.load(p.id, root=tmp_path)
    assert thumbtest.step(p, public + timedelta(days=4), "t", tmp_path, set_thumb=st) == ""            # numbers not in yet
    answers = iter([(900, 3.1), (800, 4.6)])                                                            # A then B
    call = lambda method, url, token: (200, {}, {"rows": [list(next(answers))]})
    msg = thumbtest.step(p, public + timedelta(days=8), "t", tmp_path, call=call, set_thumb=st)
    assert "thumbnail B stays" in msg and set_to == ["thumb_b.jpg"]
    assert pieces.load(p.id, root=tmp_path).topic["thumb_test"]["winner"] == "B"
    assert thumbtest.step(pieces.load(p.id, root=tmp_path), public + timedelta(days=9), "t", tmp_path, call=call, set_thumb=st) == ""


def test_without_click_numbers_or_enough_impressions_a_comes_back(tmp_path):
    p = _long(tmp_path)
    public = slots.publish_at("sglearning", "long", p.publish_day)
    set_to = []
    st = lambda tok, vid, jpg: set_to.append(jpg.name) or True
    thumbtest.step(p, public + timedelta(days=2, hours=1), "t", tmp_path, set_thumb=st)
    p = pieces.load(p.id, root=tmp_path)
    msg = thumbtest.step(p, public + timedelta(days=8), "t", tmp_path, call=lambda m, u, t: (400, {}, {}), set_thumb=st)
    assert "thumbnail A stays" in msg and set_to == ["thumb_b.jpg", "thumb.jpg"]


def test_videos_without_a_second_thumbnail_are_left_alone(tmp_path):
    p = _long(tmp_path)
    (tmp_path / "out" / p.id / "thumb_b.jpg").unlink()
    public = slots.publish_at("sglearning", "long", p.publish_day)
    assert thumbtest.step(p, public + timedelta(days=3), "t", tmp_path, set_thumb=lambda *a: True) == ""
