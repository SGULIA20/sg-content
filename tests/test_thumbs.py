import struct
from datetime import date
from pathlib import Path

from engine import pieces, thumbs
from tests.test_writer import good_script


def _piece(kind="short"):
    p = pieces.Piece(id=f"2026-10-22-sglearning-{kind}", channel="sglearning", kind=kind, publish_day=date(2026, 10, 22))
    p.script = good_script()
    p.script["title"] = "FD *safe* hai, par paisa bacha kya? 🤔"
    p.script["thumbnail"] = {"name": "FD", "name_hi": "एफडी", "words": ["7%", "KAHAN GAYA"], "words_hi": ["7%", "कहाँ गया"],
                             "scene": "LEFT: a fat stack of rupee notes; RIGHT: the same stack melted to a few notes"}
    return p


def test_make_paints_one_dramatic_picture_and_renders_cover_and_thumb_with_the_topic_name(tmp_path):
    painted, rendered = [], []
    def paint(prompt, out, **kw):
        painted.append((prompt, kw.get("aspect"))); Path(out).parent.mkdir(parents=True, exist_ok=True); Path(out).write_bytes(b"png"); return Path(out)
    def render(kind, data, out, size):
        rendered.append((kind, size, data.get("words"), data.get("name"))); Path(out).parent.mkdir(parents=True, exist_ok=True); Path(out).write_bytes(b"jpg"); return Path(out)
    out = thumbs.make(_piece(), tmp_path, paint=paint, render=render, cast_refs=lambda prompt, **kw: [])
    assert len(painted) == 1 and "LEFT: a fat stack" in painted[0][0] and "No face close-up" in painted[0][0] and painted[0][1] == "9:16"
    assert out["thumb"] == tmp_path / "thumb.jpg" and out["cover"] == tmp_path / "cover.jpg"
    assert {(s, tuple(w), n) for _k, s, w, n in rendered} == {((1280, 720), ("7%", "KAHAN GAYA"), "FD"), ((1080, 1920), ("7%", "KAHAN GAYA"), "FD")}


def test_myth_thumbnails_are_in_devanagari():
    p = _piece(); p.channel = "arthvan"
    assert thumbs.name_for(p) == "एफडी" and thumbs.words_for(p) == ["7%", "कहाँ गया"]
    assert thumbs.name_for(p, "en") == "FD" and thumbs.other_script(p) == "en"


def test_long_thumb_is_16_9_short_cover_is_9_16(tmp_path):
    sizes = []
    def render(kind, data, out, size):
        sizes.append(size); Path(out).write_bytes(b"j"); return Path(out)
    thumbs.make(_piece("long"), tmp_path, paint=lambda prompt, out, **kw: Path(out).write_bytes(b"p") or Path(out), render=render, cast_refs=lambda p, **kw: [])
    assert (1280, 720) in sizes
    sizes.clear()
    thumbs.make(_piece("short"), tmp_path, paint=lambda prompt, out, **kw: Path(out).write_bytes(b"p") or Path(out), render=render, cast_refs=lambda p, **kw: [])
    assert (1080, 1920) in sizes and (1280, 720) in sizes            # Shorts get a vertical cover and a landscape thumb


def test_words_fall_back_to_title_keyword_when_missing(tmp_path):
    p = _piece(); p.script.pop("thumbnail")
    words = thumbs.words_for(p)
    assert words and all(len(w) <= 14 for w in words) and len(words) <= 3 and "safe" in " ".join(words).lower()


def test_long_videos_test_the_other_script_with_the_same_picture(tmp_path):
    p = _piece("long")
    renders, painted = [], []
    def render(kind, data, out, size):
        renders.append((Path(out).name, data["name"], data["words"])); Path(out).write_bytes(b"j"); return Path(out)
    def paint(prompt, out, **kw):
        painted.append(prompt); Path(out).write_bytes(b"p"); return Path(out)
    out = thumbs.make(p, tmp_path, paint=paint, render=render)
    assert len(painted) == 1 and "thumb_b" in out
    assert renders == [("thumb.jpg", "FD", ["7%", "KAHAN GAYA"]), ("thumb_b.jpg", "एफडी", ["7%", "कहाँ गया"])]
    p.script["thumbnail"].pop("name_hi"); renders.clear()
    assert "thumb_b" not in thumbs.make(p, tmp_path, paint=paint, render=render)     # an old script without both names: no test
