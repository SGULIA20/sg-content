import json
import subprocess
from datetime import date
from pathlib import Path

import pytest

from engine import pieces, storyframe, cast

pytestmark = pytest.mark.slow


def _png(path, w, h, colour):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c={colour}:s={w}x{h}", "-frames:v", "1", str(path)], check=True)
    return path


def _tone(path, seconds, rate=24000):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"sine=frequency=440:sample_rate={rate}", "-t", str(seconds), "-ac", "1", "-sample_fmt", "s16", str(path)], check=True)
    return path


def _probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height:format=duration", "-of", "json", str(path)], capture_output=True, text=True, check=True).stdout
    d = json.loads(out)
    return d["streams"][0]["width"], d["streams"][0]["height"], float(d["format"]["duration"])


def test_story_build_frames_panels_with_title_and_captions(tmp_path):
    p = pieces.Piece(id="2026-10-21-sglearning-short", channel="sglearning", kind="short", publish_day=date(2026, 10, 21))
    p.script = {"title": "Papa ne 20 saal *FD* mein rakha… 💔", "hook": "h",
                "scenes": [{"vo": "Mummy boli, beta bank hi safe hai.", "visual": {"type": "art", "prompt": "x", "card": None}, "facts_used": [], "label": "reported"},
                           {"vo": "7 percent mila, mehngai 6.", "visual": {"type": "art", "prompt": "y", "card": None}, "facts_used": [0], "label": "reported"}],
                "end_question": "q", "cards": [], "captions": {"youtube": {"title": "t", "description": "d", "tags": [], "chapters": []}}, "carousel": False}
    p.facts = [{"source_name": "RBI", "source_date": "2026-10-19"}]
    lines = [(_tone(tmp_path / "v0.wav", 1.6), 1.6), (_tone(tmp_path / "v1.wav", 1.4), 1.4)]
    panels = [_png(tmp_path / "p0.png", 1080, 1350, "orange"), _png(tmp_path / "p1.png", 1080, 1350, "teal")]
    out = storyframe.build(p, lines, panels, (1080, 1920), tmp_path / "out")
    w, h, dur = _probe(out)
    assert (w, h) == (1080, 1920) and out.name == "reel.mp4" and 6.5 < dur < 7.5          # two lines + the 3 s branded end card
    assert (tmp_path / "out" / "title.png").exists() and (tmp_path / "out" / "end.png").exists() and p.timings[0] == 0.0
    from engine import qa
    assert qa.narration_intact(out, speech_end=p.timings[-1] + 1.4)                    # the last line is still audible to its end


def test_brand_names_the_channel_on_every_piece():
    assert storyframe.brand("sglearning") == {"channel": "Learning with SG", "tagline": "Paise ki khabar, seedhi baat", "handle": "@sanjeev_gulia"}
    assert storyframe.brand("arthvan")["channel"] == "SG-MYTH-WORLD"


def test_title_markup_turns_stars_into_keyword_span():
    assert storyframe.title_html("Papa ne 20 saal *FD* mein rakha") == 'Papa ne 20 saal <span class="k">FD</span> mein rakha'
    assert storyframe.title_html("no stars & <b>") == "no stars &amp; &lt;b&gt;"


def test_cast_sheet_lists_sg_and_family():
    members = cast.load()
    assert {"sg", "wife", "beta", "beti", "papa", "mummy", "bhai", "behen"} <= set(members)
    assert members["sg"]["refs"] and all((cast.ASSETS_DIR / "reference" / r).exists() for r in members["sg"]["refs"])


def test_story_build_overlays_label_chip_for_mythology(tmp_path):
    p = pieces.Piece(id="2026-10-21-arthvan-short", channel="arthvan", kind="short", publish_day=date(2026, 10, 21))
    p.script = {"title": "Samundar ke neeche *Dwarka*? 😱", "hook": "h",
                "scenes": [{"vo": "NIO ke goton ne deewarein dekhi.", "visual": {"type": "art", "prompt": "x", "card": None}, "facts_used": [], "label": "archaeology"}],
                "end_question": "q", "cards": [], "captions": {"youtube": {"title": "t", "description": "d", "tags": [], "chapters": []}}, "carousel": False}
    lines = [(_tone(tmp_path / "v0.wav", 1.5), 1.5)]
    panels = [_png(tmp_path / "p0.png", 1080, 1350, "orange")]
    out = storyframe.build(p, lines, panels, (1080, 1920), tmp_path / "out")
    assert out.exists() and (tmp_path / "out" / "label-archaeology.png").exists()


def test_story_build_landscape_long(tmp_path):
    p = pieces.Piece(id="2026-10-21-sglearning-long", channel="sglearning", kind="long", publish_day=date(2026, 10, 21))
    p.script = {"title": "FD ka *sach* 💔", "hook": "h",
                "scenes": [{"vo": "Pehla adhyay.", "visual": {"type": "art", "prompt": "x", "card": None}, "facts_used": [], "label": "reported"},
                           {"vo": "Doosra adhyay.", "visual": {"type": "art", "prompt": "y", "card": None}, "facts_used": [], "label": "reported"}],
                "end_question": "q", "cards": [], "captions": {"youtube": {"title": "t", "description": "d", "tags": [], "chapters": ["00:00 Ek", "00:00 Do"]}}, "carousel": False}
    lines = [(_tone(tmp_path / "v0.wav", 1.5), 1.5), (_tone(tmp_path / "v1.wav", 1.5), 1.5)]
    panels = [_png(tmp_path / "p0.png", 1920, 1080, "orange"), _png(tmp_path / "p1.png", 1920, 1080, "teal")]
    out = storyframe.build(p, lines, panels, (1920, 1080), tmp_path / "out")
    w, h, dur = _probe(out)
    assert (w, h) == (1920, 1080) and out.name == "long.mp4" and 6.4 < dur < 7.4


def test_logo_badge_is_drawn_once_per_channel_and_transparent(tmp_path):
    a = storyframe.logo("sglearning", 150, tmp_path)
    b = storyframe.logo("sglearning", 150, tmp_path)
    assert a == b == tmp_path / "sglearning-150.png" and a.stat().st_size > 1000
    import zlib, struct
    data = a.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n" and struct.unpack(">B", data[25:26])[0] in (6,)      # colour type 6 = RGBA, so corners stay see-through
    assert storyframe.logo("arthvan", 150, tmp_path).exists()


def test_first_scene_opens_on_a_moving_close_up_then_cuts():
    from engine import storyframe
    assert "if(lt(on,39),1.35" in storyframe.zoom_expr(4.0, True)
    assert storyframe.zoom_expr(4.0, False).startswith("min(zoom+")
    assert storyframe.zoom_expr(1.5, True).startswith("min(zoom+")          # too short to cut twice
