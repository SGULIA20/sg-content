import pytest

from engine import captions


def test_split_times_sum_to_scene_length():
    cues = captions.split("Crude oil sau dollar ke paar gaya, to teen cheezein badalti hain, pehli petrol ka daam.", 6.0)
    assert cues[0][0] == 0.0 and cues[-1][1] == pytest.approx(6.0)
    assert all(e > s for s, e, _t in cues)
    assert all(len(t.split()) <= 6 for _s, _e, t in cues)
    assert " ".join(t for _s, _e, t in cues).replace("  ", " ") == "Crude oil sau dollar ke paar gaya, to teen cheezein badalti hain, pehli petrol ka daam."


def test_split_devanagari_counts_syllables():
    cues = captions.split("भारत अपना अस्सी प्रतिशत तेल बाहर से खरीदता है", 4.0)
    assert cues[-1][1] == pytest.approx(4.0) and len(cues) >= 2


def test_split_short_line_is_one_cue():
    assert captions.split("Namaste.", 1.0) == [(0.0, 1.0, "Namaste.")]


def test_ass_has_devanagari_font_and_positions():
    cues = [(0.0, 1.5, "ek"), (1.5, 3.0, "do")]
    ass = captions.ass(cues, (1080, 1920))
    assert "Noto Sans Devanagari" in ass and "Dialogue: 0,0:00:00.00,0:00:01.50" in ass and "PlayResX: 1080" in ass
    assert captions.ass(cues, (1920, 1080)) != ass


def test_offset_shifts_cues():
    assert captions.offset([(0.0, 1.0, "a")], 2.5) == [(2.5, 3.5, "a")]
