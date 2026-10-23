"""Thumbnails that earn the click: a drawn reaction panel (a face with a strong emotion, the key object) plus at most three big words that the
title does NOT say (youtube skill: information split, faces +20-30 % CTR, legible at 168×94). Longs get 16:9; Shorts get a 9:16 cover
for Instagram and the YouTube Shorts thumbnail, plus a 16:9 for search and the channel page."""
import re
from pathlib import Path

from . import art, cards, cast
from .pieces import Piece

REACTION = ("Close-up, {scene}. Exaggerated, genuine emotion on the face: wide eyes, raised eyebrows, mouth open or jaw dropped; one key object "
            "clearly visible; simple uncluttered background with strong contrast; the face takes most of the frame; same picture style as the panels; "
            "no text in the picture.")
MAX_WORDS, MAX_LEN = 3, 14


def words_for(piece: Piece) -> list:
    """Two or three punchy words for the image, taken from the writer's thumbnail block, else the title's starred keyword plus a number."""
    s = piece.script or {}
    words = [w.strip() for w in (s.get("thumbnail") or {}).get("words", []) if w and w.strip()]
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


def words_b(piece: Piece) -> list:
    """The second thumbnail's words for the click test (founder, 23 Oct 2026): the title's own first words, so the test asks
    "the writer's punch words or the title's words?". [] when they would be the same as the first thumbnail."""
    s = piece.script or {}
    title = (s.get("captions", {}).get("youtube", {}).get("title") or s.get("title") or "")
    words = [w for w in re.sub(r"[^\w\s₹%]", " ", title).split() if len(w) > 1][:MAX_WORDS]
    words = [w[:MAX_LEN] for w in words]
    return words if words and [w.lower() for w in words] != [w.lower() for w in words_for(piece)] else []


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


def make(piece: Piece, out_dir: Path, paint=art.paint, render=cards.render, cast_refs=cast.refs_for) -> dict:
    """Paints the reaction panel once and renders thumb.jpg (16:9) and, for Shorts, cover.jpg (9:16). Returns their paths."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    scene = scene_for(piece)
    prompt = art.style_prompt(piece.channel, REACTION.format(scene=scene))
    aspect = "9:16" if piece.kind == "short" else "16:9"
    panel = paint(prompt, out_dir / "reaction.png", aspect=aspect, refs=cast_refs(scene, channel=piece.channel))
    words = words_for(piece)
    focus = "50% 22%" if piece.kind == "short" else "50% 50%"               # a portrait panel cropped to 16:9 keeps the face, not the belly
    out = {"thumb": render("thumb2", {"words": words, "panel_path": panel, "focus": focus}, out_dir / "thumb.jpg", (1280, 720))}
    alt = words_b(piece) if piece.kind == "long" else []
    if alt:                                                                   # same panel, other words: no extra picture cost
        out["thumb_b"] = render("thumb2", {"words": alt, "panel_path": panel, "focus": focus}, out_dir / "thumb_b.jpg", (1280, 720))
    if piece.kind == "short":
        out["cover"] = render("thumb2", {"words": words, "panel_path": panel, "focus": "50% 50%"}, out_dir / "cover.jpg", (1080, 1920))
    return out
