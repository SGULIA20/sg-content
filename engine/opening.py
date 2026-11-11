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
PILL_SIZE_H = 104
TAG_TEXT = "AI visualisation"
WORDS_BY_CHANNEL = {"sglearning": (75, 110)}     # room for the spoken disclaimer line
KIND_FOR = {"scripture": "legend", "legend": "legend", "archaeology": "science", "disputed": "disputed",
            "official": "science", "reported": "", "analyst-view": "disputed"}
LABEL_TEXT = {"scripture": "Parampara", "legend": "Kahani", "archaeology": "Khoj", "disputed": "Bahas",
              "official": "Sarkari", "reported": "Report", "analyst-view": "Raay"}
ADDENDUM_FILE = "trial-arthvan.txt"


def _config(root: Path = None) -> dict:
    path = (Path(root) if root else CONTENT_DIR) / TEST_FILE
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def _window(channel: str, root: Path = None, kind: str = "short") -> tuple:
    """(from, to) for a channel's Shorts or longs, or None. Shorts: "channels": {name: first day} (or the older "channel" + "from");
    long videos: "longs": {name: first day}."""
    t = _config(root)
    if not t:
        return None
    if kind == "long":
        start = (t.get("longs") or {}).get(channel)
    else:
        start = (t.get("channels") or {}).get(channel) or (t.get("from") if t.get("channel") == channel else None)
    return (start, t.get("to", "9999-12-31")) if start else None


def is_trial(piece, root: Path = None) -> bool:
    if piece.kind not in ("short", "long"):
        return False
    import os
    if os.environ.get("SG_FORCE_NEW_STYLE") == "1" and root is None:      # a preview of an older piece in the new style (scripts/preview_piece.py)
        return True
    win = _window(piece.channel, root, piece.kind)
    return bool(win) and win[0] <= str(piece.id)[:10] <= win[1]


def speed(piece, root: Path = None) -> float:
    """How much faster a new-style Short is spoken, the founder's intro and the narration alike (founder, 11 Nov 2026: "speed like 1.2x so
    reel timings can be maintained and the explanation will also be there"). 1.0 for everything else."""
    if piece.kind != "short" or not is_trial(piece, root):
        return 1.0
    try:
        return min(1.3, max(1.0, float(_config(root).get("speed", 1.0))))
    except (TypeError, ValueError):
        return 1.0


def cutout_on(root: Path = None) -> bool:
    """Whether the founder is cut out and placed over the story's pictures (off: his clip full-screen, its own background set in the prompt)."""
    return bool(_config(root).get("cutout", False))


def is_hero_scene(piece, i: int, root: Path = None) -> bool:
    return is_trial(piece, root) and i < int(_config(root).get("scenes", 1))


def addendum(channel: str = "arthvan", root: Path = None, kind: str = "short") -> str:
    name = f"trial-{channel}.txt" if kind == "short" else "trial-long.txt"
    return ((Path(root) if root else CONTENT_DIR) / "prompts" / name).read_text()


def words(channel: str) -> tuple:
    """Allowed words of narration for a new-style Short."""
    return WORDS_BY_CHANNEL.get(channel, WORDS)


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
    used = [j for j in sc.get("facts_used", []) if j < len(piece.facts or [])]
    label = sc.get("label")
    if label not in LABEL_TEXT and used:                    # a money scene's label names its story beat ("twist", "cost"): the fact's own label counts
        label = (piece.facts[used[0]] or {}).get("label")
    if label in LABEL_TEXT and used:
        src = (piece.facts[used[0]] or {}).get("source_name")
        if src:
            return f"{LABEL_TEXT[label]} • {_short(src, 13)}", KIND_FOR[label]
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
            out[i] = render("pill", {"kind": p[1], "text": p[0]}, out_dir / f"pill{i:02d}.png", (size[0] - 240, PILL_SIZE_H))             # its own row under the badge, the full safe width
    out["tag"] = render("pill", {"kind": "ai", "text": TAG_TEXT}, out_dir / "tag.png", (460, 66))
    return out


POP_S = 0.28                        # a pill slides in from the left in this time


def frame_overlays(piece, i: int, dur: float, size: tuple, pills: dict, top: int, side: int, logo_px: int) -> list:
    """Timed overlays (png, x, y, start, end) for the full-screen story frame: the AI tag top-left on a realistic picture for the whole
    scene; the scene's pill on its own row under the badge, sliding in from the left (x is an ffmpeg expression)."""
    out = []
    if "tag" in pills and is_hero_scene(piece, i):
        out.append((pills["tag"], side, top, 0.0, dur))
    if i in pills:
        slide = f"'min({side},-{size[0]}+({size[0]}+{side})*(t-0.15)/{POP_S})'"
        out.append((pills[i], slide, top + logo_px + 18, 0.15, dur))
    return out


def active(today=None, root: Path = None, ahead: int = 9) -> bool:
    """True while a test window overlaps the days being produced (the workflows install the picture-movement and cut-out tools only then)."""
    from datetime import date, timedelta
    t = _config(root)
    today = today or date.today()
    spans = [_window(ch, root) for ch in list((t.get("channels") or {})) + ([t["channel"]] if t.get("channel") else [])]
    spans += [_window(ch, root, "long") for ch in (t.get("longs") or {})]
    for start, end in spans:
        if start <= (today + timedelta(days=ahead)).isoformat() and (today - timedelta(days=1)).isoformat() <= end:
            return True
    return False


if __name__ == "__main__":
    import sys
    sys.exit(0 if active() else 1)
