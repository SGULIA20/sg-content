"""Thumbnails that earn the click (founder, 27 Oct 2026, after comparing ours with StudyIQ's and Mysterious Hindu's on the same topic):
one dramatic, vivid picture of the story's most striking sight (a before/after split when the story is a change), the TOPIC NAME huge
on a red banner, and two or three shock words with the number in a yellow tag (templates/thumb2.html). Longs get 16:9; Shorts get a
9:16 cover for Instagram and the YouTube Shorts thumbnail, plus a 16:9 for search and the channel page. One picture per piece, as before:
thumb, thumb_b and cover all reuse it. Letters: SG-MYTH-WORLD in Devanagari, Learning with SG in Roman; a long's click test (thumb_b)
tries the other script with the same picture."""
import re
from pathlib import Path

from . import art, cards
from .pieces import Piece

DRAMA = ("{scene}. One dramatic, eye-catching sight that makes a stranger stop scrolling: cinematic wide or medium shot, vivid saturated "
         "colours, strong contrast and dramatic light, hyper-detailed digital painting with a realistic look, the main subject large and "
         "clear in the RIGHT half of the frame and the left side calmer. No face close-up, nobody looking at a phone. Deities only from behind, "
         "at a distance, or as a statue or wall painting, never in close-up; no real people, no politicians, no logos. No text, no letters, no numbers.")
MAX_WORDS, MAX_LEN, MAX_NAME = 3, 14, 16
SCRIPT = {"arthvan": "hi", "sglearning": "en"}       # founder, 27 Oct 2026: myth in Devanagari, money in Roman


def _thumb(piece: Piece) -> dict:
    return (piece.script or {}).get("thumbnail") or {}


def name_for(piece: Piece, script: str | None = None) -> str:
    """The topic name for the red banner (Saraswati / सरस्वती, Nvidia), in the given script; "" when the writer gave none."""
    t = _thumb(piece)
    script = script or SCRIPT.get(piece.channel, "en")
    name = (t.get("name_hi") if script == "hi" else t.get("name")) or ""
    return name.strip()[:MAX_NAME]


def words_for(piece: Piece, script: str | None = None) -> list:
    """Two or three punchy words from the writer's thumbnail block (Devanagari ones for "hi" when given), else the title's starred
    keyword plus a number."""
    s = piece.script or {}
    script = script or SCRIPT.get(piece.channel, "en")
    t = _thumb(piece)
    words = [w.strip() for w in ((script == "hi" and t.get("words_hi")) or t.get("words") or []) if w and w.strip()]
    if not words:
        title = s.get("title", "")
        key = re.findall(r"\*(.+?)\*", title)
        number = next((c["big_number"] for c in s.get("cards", []) if c.get("big_number")), "")
        if not number:
            m = re.search(r"\d[\d,.]*\s*(%|percent|crore|lakh|saal|rupaye)?", " ".join(sc.get("vo", "") for sc in s.get("scenes", [])))
            number = m.group(0).strip() if m else ""
        words = [w for w in [key[0] if key else "", number] if w]
        if not words:
            words = re.sub(r"[^\w\s]", "", title).split()[:2]
    return [w[:MAX_LEN] for w in words][:MAX_WORDS]


def other_script(piece: Piece) -> str | None:
    """The script the click test tries second, when the writer gave the name in both; else None."""
    other = "en" if SCRIPT.get(piece.channel, "en") == "hi" else "hi"
    t = _thumb(piece)
    return other if (t.get("name") and t.get("name_hi")) else None


def scene_for(piece: Piece) -> str:
    s = piece.script or {}
    scene = (s.get("thumbnail") or {}).get("scene")
    if scene:
        return scene
    scenes = s.get("scenes", [])
    if not scenes:
        return s.get("hook", "a surprised face")
    twist = scenes[min(len(scenes) - 1, int(len(scenes) * 0.7))]
    return (twist.get("visual") or {}).get("prompt") or twist.get("vo", "")


def paint_prompt(piece: Piece) -> str:
    """The thumbnail picture's prompt; the batch job in pipeline.picture_jobs builds it the same way so the cache is hit."""
    return DRAMA.format(scene=scene_for(piece).rstrip(". "))


def make(piece: Piece, out_dir: Path, paint=art.paint, render=cards.render, cast_refs=None) -> dict:
    """Paints the picture once and renders thumb.jpg (16:9), for longs thumb_b.jpg (the other script) and for Shorts cover.jpg
    (9:16). Returns their paths. cast_refs is accepted for old callers and not used: the picture is a sight, not our cast's faces."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    aspect = "9:16" if piece.kind == "short" else "16:9"
    panel = paint(paint_prompt(piece), out_dir / "reaction.png", aspect=aspect)
    focus = "50% 30%" if piece.kind == "short" else "50% 50%"
    data = lambda script, f: {"name": name_for(piece, script), "words": words_for(piece, script), "panel_path": panel, "focus": f}
    out = {"thumb": render("thumb2", data(None, focus), out_dir / "thumb.jpg", (1280, 720))}
    alt = other_script(piece) if piece.kind == "long" else None
    if alt:                                                                   # same picture, other letters: no extra picture cost
        out["thumb_b"] = render("thumb2", data(alt, focus), out_dir / "thumb_b.jpg", (1280, 720))
    if piece.kind == "short":
        out["cover"] = render("thumb2", data(None, "50% 50%"), out_dir / "cover.jpg", (1080, 1920))
    return out
