import struct
from datetime import date
from pathlib import Path

from engine import pieces, thumbs
from tests.test_writer import good_script


def _piece(kind="short"):
    p = pieces.Piece(id=f"2026-10-22-sglearning-{kind}", channel="sglearning", kind=kind, publish_day=date(2026, 10, 22))
    p.script = good_script()
    p.script["title"] = "FD *safe* hai, par paisa bacha kya? 🤔"
    p.script["thumbnail"] = {"words": ["7%", "KAHAN GAYA"], "scene": "PAPA stares at a melting ice cube on a steel plate, eyes wide, mouth open"}
    return p


def test_make_paints_a_reaction_panel_and_renders_cover_and_thumb(tmp_path):
    painted, rendered = [], []
    def paint(prompt, out, **kw):
        painted.append((prompt, kw.get("aspect"))); Path(out).parent.mkdir(parents=True, exist_ok=True); Path(out).write_bytes(b"png"); return Path(out)
    def render(kind, data, out, size):
        rendered.append((kind, size, data.get("words"))); Path(out).parent.mkdir(parents=True, exist_ok=True); Path(out).write_bytes(b"jpg"); return Path(out)
    out = thumbs.make(_piece(), tmp_path, paint=paint, render=render, cast_refs=lambda prompt, **kw: [])
    assert "eyes wide" in painted[0][0] and "exaggerated" in painted[0][0].lower() and painted[0][1] == "9:16"
    assert out["thumb"] == tmp_path / "thumb.jpg" and out["cover"] == tmp_path / "cover.jpg"
    kinds = {k: (s, w) for k, s, w in rendered}
    assert kinds["thumb2"][0] in ((1280, 720), (1080, 1920)) and kinds["thumb2"][1] == ["7%", "KAHAN GAYA"]


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


def test_long_videos_get_a_second_thumbnail_with_the_titles_words(tmp_path):
    from engine import pieces as P
    piece = P.Piece(id="2026-10-24-sglearning-long", channel="sglearning", kind="long", publish_day=__import__("datetime").date(2026, 10, 24))
    piece.script = {"hook": "h", "scenes": [], "thumbnail": {"words": ["MINIMUM", "TRAP"], "scene": "s"},
                    "captions": {"youtube": {"title": "Credit card ka minimum due"}}}
    renders = []
    def render(kind, data, out, size):
        renders.append((Path(out).name, data["words"])); Path(out).write_bytes(b"j"); return Path(out)
    out = thumbs.make(piece, tmp_path, paint=lambda prompt, out, **kw: Path(out).write_bytes(b"p") or Path(out), render=render, cast_refs=lambda p, **kw: [])
    assert renders == [("thumb.jpg", ["MINIMUM", "TRAP"]), ("thumb_b.jpg", ["Credit", "card", "ka"])] and "thumb_b" in out
