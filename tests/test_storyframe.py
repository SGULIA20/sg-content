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
    assert storyframe.brand("sglearning") == {"channel": "Learning with SG", "tagline": "Paise ki khabar, seedhi baat", "handle": "@sanjeev_gulia",
                                              "cta_html": "<b>SUBSCRIBE</b> aur share karo"}
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


def test_a_full_screen_long_puts_captions_on_a_shade_and_moves_the_camera_a_different_way_each_scene():
    """Founder, 10 Nov 2026: "same should be for long videos also"."""
    from engine import storyframe as sf
    size = (1920, 1080)
    old, new = sf.geometry(size, False, False), sf.geometry(size, False, True)
    assert old["shade"] is None and old["cap_y"] == 1080 - int(1080 * sf.TOP)          # the banded long is unchanged
    assert new["shade"] == (1920, sf.LONG_SHADE_H) and new["shade_y"] == 1080 - sf.LONG_SHADE_H
    assert new["cap_y"] + new["cap"][1] <= 1080 and new["top"] == sf.LONG_TOP
    short = sf.geometry((1080, 1920), True, True)
    assert short["cap"] == (1080, sf.CAP_H) and short["top"] == sf.FULL_TOP
    seen = {sf.camera_expr(p, 300) for p in sf.CAMERA_PATHS}
    assert len(seen) == len(sf.CAMERA_PATHS)
    z, x, y = sf.camera_expr("push", 300)
    assert "1.40" in z and "on" in z
    assert sf.camera_expr("glide", 300, 1)[1] != sf.camera_expr("glide", 300, -1)[1]


def test_a_scene_is_cut_into_several_framings_and_short_scenes_are_left_whole(tmp_path):
    """Founder, 27 Nov 2026: 'Do all 3'. The watched viral videos changed the picture at least 3 times in 10 seconds; ours 1 to 2."""
    import json, subprocess
    from types import SimpleNamespace as P
    from engine import opening, storyframe as sf
    assert sf.cut_filter(3.0, 0, 108, 192) == "" and sf.cut_filter(1.2, 3, 108, 192) == ""            # too short to cut
    seven = sf.cut_filter(7.4, 0, 108, 192)
    assert seven.count("if(lt(on,") == 6 and "1.0+" in seven and seven.endswith(",")                    # three framings: two cuts in zoom, x and y
    assert sf.cut_filter(7.4, 0, 108, 192) != sf.cut_filter(7.4, 1, 108, 192)                           # the next scene frames differently
    (tmp_path / "hero-test.json").write_text(json.dumps({"cuts_from": "2026-11-28"}))
    assert opening.cuts_on(P(id="2026-11-28-arthvan-short"), tmp_path) and not opening.cuts_on(P(id="2026-11-27-arthvan-short"), tmp_path)
    pic = tmp_path / "pic.png"                                                                           # left half red, right half blue
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=red:s=200x400", "-f", "lavfi", "-i", "color=blue:s=200x400",
                    "-filter_complex", "hstack", "-frames:v", "1", str(pic)], check=True)
    blank = tmp_path / "blank.png"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=black@0.0:s=108x10,format=rgba", "-frames:v", "1", str(blank)], check=True)
    out = sf.scene(pic, 5.0, (108, 192), tmp_path / "s.mp4", blank, [], full=True, cuts=0)
    def red_share(t):
        raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(t), "-i", str(out), "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                             capture_output=True, check=True).stdout
        px = [raw[i:i + 3] for i in range(0, len(raw), 3)]
        return sum(1 for p in px if p[0] > p[2]) / len(px)
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(out)], capture_output=True, text=True).stdout)
    assert abs(dur - 5.0) < 0.1 and abs(red_share(1.0) - 0.5) < 0.06 and red_share(3.5) - red_share(1.0) > 0.05          # the whole picture, then a close-up of its left side


def test_the_founders_moving_clip_takes_the_place_of_a_scenes_painting(tmp_path):
    """Founder, 27 Nov 2026: 'Moving clips I can provide ... let us make try now'."""
    from types import SimpleNamespace as P
    from engine import storyframe as sf
    piece = P(id="2026-12-03-arthvan-short", ids={})
    panels = [tmp_path / "a.png", tmp_path / "b.png", tmp_path / "c.png"]
    assert sf.scene_clips(piece, panels, tmp_path / "scenes") == panels and "scene_clips" not in piece.ids
    d = tmp_path / "scenes" / piece.id; d.mkdir(parents=True)
    (d / "01.mp4").write_bytes(b"x" * 60_000); (d / "02.mp4").write_bytes(b"tiny")              # a broken upload is not used
    out = sf.scene_clips(piece, panels, tmp_path / "scenes")
    assert out == [panels[0], d / "01.mp4", panels[2]] and piece.ids["scene_clips"] == [1]
