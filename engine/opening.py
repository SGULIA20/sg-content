"""The new opening style for SG-MYTH-WORLD Shorts, in test (founder, 9 Nov 2026: "yes all 3"; trial Short approved).

Applies to Shorts of the channel dated from..to in content/hero-test.json: 35-45 s (85-125 words, as the money Shorts already run), a payoff
hook with a pivot line, the first `scenes` pictures photoreal (an AI visualisation, tagged as such), and a small data pill on each scene that
states a fact: where it is, or which kind of evidence and which source. Pills are drawn from the script's own labels and fact sheet, so the
writer's schema is unchanged. No file, or a date outside the window: nothing here does anything.
"""
import json
from pathlib import Path

from .config import CONTENT_DIR

TEST_FILE = "hero-test.json"
WORDS = (70, 100)                   # about 30-38 s of narration at 2.5 words a second, so the Short lands near 40-45 s with the founder's intro
PILL_SIZE_H = 90
TAG_TEXT = "AI visualisation"
KIND_FOR = {"scripture": "legend", "legend": "legend", "archaeology": "science", "disputed": "disputed"}
LABEL_TEXT = {"scripture": "Parampara", "legend": "Kahani", "archaeology": "Khoj", "disputed": "Bahas"}
ADDENDUM_FILE = "trial-arthvan.txt"


def _config(root: Path = None) -> dict:
    path = (Path(root) if root else CONTENT_DIR) / TEST_FILE
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def is_trial(piece, root: Path = None) -> bool:
    t = _config(root)
    day = str(piece.id)[:10]
    return bool(t) and piece.kind == "short" and piece.channel == t.get("channel") and t.get("from", "9") <= day <= t.get("to", "0")


def is_hero_scene(piece, i: int, root: Path = None) -> bool:
    return is_trial(piece, root) and i < int(_config(root).get("scenes", 1))


def addendum(root: Path = None) -> str:
    return ((Path(root) if root else CONTENT_DIR) / "prompts" / ADDENDUM_FILE).read_text()


def _short(name: str, n: int = 30) -> str:
    name = " ".join(str(name).split())
    return name if len(name) <= n else name[: n - 1].rstrip(" ,.;:") + "…"


def pill_for(piece, i: int):
    """(text, kind) for scene i, or None. Scene 0 names the place; a scene with a label and a source names the kind of evidence and the source."""
    scenes = (piece.script or {}).get("scenes", [])
    if i >= len(scenes):
        return None
    sc = scenes[i]
    place = (piece.topic or {}).get("place")
    if i == 0 and place:
        return _short(place, 34), ""
    label = sc.get("label")
    used = [j for j in sc.get("facts_used", []) if j < len(piece.facts or [])]
    if label in LABEL_TEXT and used:
        src = (piece.facts[used[0]] or {}).get("source_name")
        if src:
            return f"{LABEL_TEXT[label]} • {_short(src, 15)}", KIND_FOR[label]
    return None


def render_pills(piece, out_dir: Path, size: tuple, render) -> dict:
    """{scene index: pill png} plus 'tag' (the AI visualisation tag) for a trial piece; {} otherwise."""
    if not is_trial(piece):
        return {}
    out_dir = Path(out_dir)
    out = {}
    for i in range(len((piece.script or {}).get("scenes", []))):
        p = pill_for(piece, i)
        if p:
            out[i] = render("pill", {"kind": p[1], "text": p[0]}, out_dir / f"pill{i:02d}.png", (size[0] - 420, PILL_SIZE_H))             # ends before the badge in the top-right corner
    out["tag"] = render("pill", {"kind": "ai", "text": TAG_TEXT}, out_dir / "tag.png", (460, 60))
    return out


def frame_overlays(piece, i: int, dur: float, size: tuple, pills: dict, top: int, side: int, logo_px: int) -> list:
    """Timed overlays (png, x, y, start, end) for the full-screen story frame: the AI tag top-left on a realistic picture, the scene's
    pill on the row below it, both for the whole scene."""
    out = []
    if "tag" in pills and is_hero_scene(piece, i):
        out.append((pills["tag"], side, top, 0.0, dur))
    if i in pills:
        out.append((pills[i], side, top + 80, 0.0, dur))
    return out
