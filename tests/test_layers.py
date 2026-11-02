from datetime import date
from types import SimpleNamespace

from engine import layers


def _piece(kind="short", channel="sglearning", topic=None, day=date(2026, 11, 5)):
    return SimpleNamespace(kind=kind, channel=channel, topic=topic if topic is not None else {"title": "x"}, publish_day=day)


def test_layers_alternate_days_from_the_test_start_and_none_before():
    assert layers.on_for(date(2026, 11, 4)) is False            # before the test
    assert [layers.on_for(date(2026, 11, d)) for d in range(5, 11)] == [True, False, True, False, True, False]


def test_apply_records_the_arm_only_for_painted_daily_shorts():
    p = _piece()
    assert layers.apply(p) is True and p.topic["layers"] is True
    q = _piece(day=date(2026, 11, 6))
    assert layers.apply(q) is False and q.topic["layers"] is False
    news = _piece(topic={"news": True})                         # the code-drawn news Reels keep their own cards
    assert layers.apply(news) is False and "layers" not in news.topic
    assert layers.apply(_piece(kind="long")) is False and layers.apply(_piece(channel="other")) is False


def test_badge_shows_the_spoken_figure_and_skips_years():
    assert layers.badge_text("Gold January se 21.43 percent gir chuka hai") == "21.43%"
    assert layers.badge_text("2029 mein maturity hai") is None
    assert layers.badge_text("Kuch bhi nahi") is None


def test_sound_cues_match_the_badge():
    with_badge = layers.sfx_events(10.0, "21.43%")
    assert [n for _t, n in with_badge] == ["whoosh", "pop", "tick"]
    no_badge = layers.sfx_events(10.0, None)
    assert [n for _t, n in no_badge] == ["whoosh"]


def test_scene_overlays_have_a_bar_and_a_timed_badge(tmp_path):
    ov = layers.scene_overlays("21.43%", 2, 9, (1080, 1920), tmp_path, top=326, side=120, badge_y=556, dur=6.0)
    assert len(ov) == 2
    bar, badge = ov
    assert bar[3:] == (0.0, 6.0)
    assert badge[1:3] == (120, 556) and badge[3] == layers.POP_AT and badge[4] <= 6.0 - 0.1
    assert all(p.exists() for p, *_ in ov)
