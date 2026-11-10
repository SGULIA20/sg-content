import json
from types import SimpleNamespace as NS

from engine import lint, opening


def _cfg(tmp_path, body='{"channel": "arthvan", "from": "2026-11-16", "to": "2026-11-18", "scenes": 2}'):
    (tmp_path / "hero-test.json").write_text(body)
    return tmp_path


def _piece(day="2026-11-16", kind="short", ch="arthvan"):
    return NS(id=f"{day}-{ch}-{kind}", kind=kind, channel=ch, topic={"place": "Dwarka, Gujarat"},
              facts=[{"source_name": "National Institute of Oceanography survey report", "source_date": "1990"}, {"source_name": "Mahabharata, Mausala Parva"}],
              script={"scenes": [{"label": "legend", "facts_used": []}, {"label": "scripture", "facts_used": [1]}, {"label": "archaeology", "facts_used": [0]},
                                 {"label": "legend", "facts_used": []}]})


def test_the_test_window_only_covers_the_configured_shorts(tmp_path):
    root = _cfg(tmp_path)
    assert opening.is_trial(_piece(), root) and opening.is_trial(_piece("2026-11-18"), root)
    assert not opening.is_trial(_piece("2026-11-19"), root) and not opening.is_trial(_piece("2026-11-15"), root)
    assert not opening.is_trial(_piece(ch="sglearning"), root) and not opening.is_trial(_piece(kind="long"), root)
    assert not opening.is_trial(_piece(), tmp_path / "nowhere")
    assert opening.is_hero_scene(_piece(), 1, root) and not opening.is_hero_scene(_piece(), 2, root)


def test_pills_name_the_place_then_the_kind_of_evidence_and_the_source():
    p = _piece()
    assert opening.pill_for(p, 0) == ("Dwarka, Gujarat", "")
    assert opening.pill_for(p, 1) == ("Parampara • Mahabharata, M…", "legend")
    text, kind = opening.pill_for(p, 2)
    assert text.startswith("Khoj • National Insti") and text.endswith("…") and kind == "science"
    assert opening.pill_for(p, 3) is None and opening.pill_for(p, 9) is None


def test_the_full_screen_frame_tags_a_realistic_picture_and_puts_the_pill_under_the_tag(tmp_path, monkeypatch):
    monkeypatch.setattr(opening, "CONTENT_DIR", _cfg(tmp_path))
    p = _piece()
    pills = {1: "pill.png", "tag": "tag.png"}
    ov = opening.frame_overlays(p, 1, 6.0, (1080, 1920), pills, 170, 120, 150)
    assert ov == [("tag.png", 120, 170, 0.0, 6.0), ("pill.png", 120, 250, 0.0, 6.0)]
    assert opening.frame_overlays(p, 3, 6.0, (1080, 1920), pills, 170, 120, 150) == []      # scene 4 is not realistic here and has no pill


def test_trial_shorts_use_the_35_to_45_second_length_and_the_writer_gets_the_new_rules():
    assert opening.WORDS == (70, 100)
    assert "NEW OPENING STYLE" in opening.addendum() and "PAYOFF" in opening.addendum() and "PIVOT" in opening.addendum()
