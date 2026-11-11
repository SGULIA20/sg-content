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
    assert opening.pill_for(p, 1) == ("Parampara • Mahabharata…", "legend")
    text, kind = opening.pill_for(p, 2)
    assert text.startswith("Khoj • National In") and text.endswith("…") and kind == "science"
    assert opening.pill_for(p, 3) is None and opening.pill_for(p, 9) is None


def test_the_full_screen_frame_tags_a_realistic_picture_and_puts_the_pill_under_the_tag(tmp_path, monkeypatch):
    monkeypatch.setattr(opening, "CONTENT_DIR", _cfg(tmp_path))
    p = _piece()
    pills = {1: "pill.png", "tag": "tag.png"}
    ov = opening.frame_overlays(p, 1, 6.0, (1080, 1920), pills, 170, 120, 150)
    assert ov[0] == ("tag.png", 120, 170, 0.0, 6.0) and ov[1][0] == "pill.png" and ov[1][2:] == (338, 0.15, 6.0) and "min(120," in ov[1][1]
    assert opening.frame_overlays(p, 3, 6.0, (1080, 1920), pills, 170, 120, 150) == []      # scene 4 is not realistic here and has no pill


def test_trial_shorts_use_the_35_to_45_second_length_and_the_writer_gets_the_new_rules():
    assert opening.WORDS == (70, 100) and opening.words('arthvan') == (70, 100) and opening.words('sglearning') == (75, 110)
    # founder, 11 Nov 2026: "do not compromise with scripts": the writer is told about the pictures only
    for ch in ("arthvan", "sglearning"):
        text = opening.addendum(ch)
        assert "REALISTIC PICTURES" in text and "stay as the rules above say" in text
        assert "PAYOFF" not in text and "PIVOT" not in text and "LENGTH:" not in text
    assert "PAYOFF" not in opening.addendum("arthvan", kind="long")


def test_the_tools_are_installed_only_while_the_test_window_is_being_produced(tmp_path):
    from datetime import date
    root = _cfg(tmp_path)
    assert opening.active(date(2026, 11, 10), root) and opening.active(date(2026, 11, 18), root)
    assert not opening.active(date(2026, 11, 1), root) and not opening.active(date(2026, 11, 25), root)
    assert not opening.active(date(2026, 11, 10), tmp_path / "nowhere")


def test_both_channels_can_run_the_new_style_each_from_its_own_day_with_no_end_date(tmp_path):
    from datetime import date
    root = _cfg(tmp_path, '{"channels": {"arthvan": "2026-11-16", "sglearning": "2026-11-17"}, "scenes": 99}')
    assert opening.is_trial(_piece("2026-11-16"), root) and opening.is_trial(_piece("2027-03-01"), root)
    assert not opening.is_trial(_piece("2026-11-16", ch="sglearning"), root) and opening.is_trial(_piece("2026-11-17", ch="sglearning"), root)
    assert not opening.is_trial(_piece("2026-11-18", kind="long", ch="sglearning"), root)
    assert opening.is_hero_scene(_piece("2026-11-17", ch="sglearning"), 7, root) and opening.active(date(2027, 1, 5), root)
    assert "REALISTIC PICTURES" in opening.addendum("sglearning") and "disclaimer" in opening.addendum("sglearning")


def test_a_money_fact_gets_a_pill_from_the_facts_own_label():
    p = _piece(ch="sglearning")
    p.topic = {}
    p.facts = [{"source_name": "Reserve Bank of India", "label": "official"}, {"source_name": "Mint", "label": "reported"}]
    p.script = {"scenes": [{"label": "hook", "facts_used": []}, {"label": "twist", "facts_used": [0]}, {"label": None, "facts_used": [1]}]}   # 10 Nov 2026: beat labels hid every pill
    assert opening.pill_for(p, 0) is None                                    # no place, no fact
    assert opening.pill_for(p, 1) == ("Sarkari • Reserve Bank…", "science")
    assert opening.pill_for(p, 2) == ("Report • Mint", "")


def test_long_videos_join_the_new_style_from_their_own_day(tmp_path):
    root = _cfg(tmp_path, '{"channels": {"arthvan": "2026-11-16"}, "longs": {"arthvan": "2026-11-22", "sglearning": "2026-11-22"}, "scenes": 99}')
    assert opening.is_trial(_piece("2026-11-22", kind="long"), root) and opening.is_trial(_piece("2026-11-25", kind="long", ch="sglearning"), root)
    assert not opening.is_trial(_piece("2026-11-19", kind="long"), root)                      # made before: keeps the banded frame
    assert opening.is_hero_scene(_piece("2026-11-22", kind="long"), 60, root)
    assert "FULL SCREEN, 16:9" in opening.addendum("arthvan", kind="long")
