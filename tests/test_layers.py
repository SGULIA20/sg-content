from datetime import date
from pathlib import Path
from types import SimpleNamespace

from engine import layers


def _piece(kind="short", channel="sglearning", topic=None, day=date(2026, 11, 5)):
    return SimpleNamespace(kind=kind, channel=channel, topic=topic if topic is not None else {"title": "x"}, publish_day=day)


def test_layers_alternate_days_from_the_test_start_and_none_before():
    assert layers.on_for(date(2026, 11, 4)) is False
    assert [layers.on_for(date(2026, 11, d)) for d in range(5, 11)] == [True, False, True, False, True, False]


def test_apply_records_the_arm_only_for_painted_daily_shorts():
    p = _piece()
    assert layers.apply(p) is True and p.topic["layers"] is True
    q = _piece(day=date(2026, 11, 6))
    assert layers.apply(q) is False and q.topic["layers"] is False
    news = _piece(topic={"news": True})
    assert layers.apply(news) is False and "layers" not in news.topic
    assert layers.apply(_piece(kind="long")) is False and layers.apply(_piece(channel="other")) is False


def test_figures_skip_years_and_bare_numbers():
    assert [f[2] for f in layers.figures("Gold 21.43 percent gira")] == ["%"]
    assert layers.figures("2029 mein maturity") == []
    assert layers.figures("Ek 5 log aaye") == []


def test_chart_only_when_a_scene_compares_two_or_more_figures_in_one_unit():
    assert layers.comparison("Gold January se 21.43 percent gir chuka hai") is None        # one figure: the caption carries it
    two = layers.comparison("Gold Bond 2021 mein ₹14,167 par tha, aaj ₹4,715 ka byaaj")
    assert two == [("₹14,167", 14167.0), ("₹4,715", 4715.0)]
    assert layers.comparison("Byaaj 2.5 percent, 14,167 par") is None                       # mixed units: no chart


def test_scene_overlays_have_a_bar_and_a_chart_only_when_comparing(tmp_path):
    plain = layers.scene_overlays("Gold 21.43 percent gira", 2, 9, (1080, 1920), tmp_path / "a", top=326, side=120, chart_y=496, dur=6.0)
    assert len(plain) == 1 and plain[0][3:] == (0.0, 6.0)
    compare = layers.scene_overlays("Jio 8,387 crore aur 40,475 crore", 3, 9, (1080, 1920), tmp_path / "b", top=326, side=120, chart_y=496, dur=6.0)
    assert len(compare) == 2
    chart = compare[1]
    assert chart[3] == layers.CHART_AT and chart[4] <= 6.0 - 0.1
    assert all(Path(p).exists() for p, *_ in compare)


def test_no_sound_cue_module_is_left():
    import importlib.util
    assert importlib.util.find_spec("engine.sfx") is None
