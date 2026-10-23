"""The recurring drawn cast (content/cast.yaml): one reference picture per member and channel, drawn once in that channel's picture style
(assets/cast/<channel>/<name>.png); panels that name a member get that picture as a reference so faces stay the same across reels. SG is
drawn from the founder's own photos. Each channel has its own style (founder, 23 Oct 2026), so each channel has its own drawings; the
doodle drawings in assets/cast/*.png belong to pieces made before that and are no longer used for new panels."""
import re
from pathlib import Path

import yaml

from . import art
from .config import ASSETS_DIR, CONTENT_DIR

CAST_FILE = CONTENT_DIR / "cast.yaml"
CAST_DIR = ASSETS_DIR / "cast"


def cast_dir(channel: str) -> Path:
    return CAST_DIR / channel
SHEET_PROMPT = ("Character reference sheet, single character, full body facing the camera, neutral stance, plain off-white background. {description}. "
                "Keep this exact face and clothes so the character is recognisable in every later panel. One single figure only: no extra panels, "
                "no inset pictures, no turnaround views, no frame or border, no speech bubbles, no signs, no writing anywhere.")


def load(path: Path = CAST_FILE) -> dict:
    return yaml.safe_load(Path(path).read_text()) or {}


def draw(name: str, channel: str = "sglearning", members: dict | None = None, **kw) -> Path:
    members = members or load()
    m = members[name]
    out = cast_dir(channel) / f"{name}.png"
    if out.exists():
        return out
    refs = [ASSETS_DIR / "reference" / r for r in m.get("refs", [])]
    prompt = art.style_prompt(channel, SHEET_PROMPT.format(description=m["description"]))
    if refs:
        prompt = "Draw this real person as a character in the picture style below, recognisable from the reference photos. " + prompt
    kw.setdefault("cache_dir", CAST_DIR / ".cache")
    return art.paint(prompt, out, refs=refs, aspect="4:5", **kw)


def mentioned(prompt: str, members: dict | None = None) -> list:
    """Cast names that a panel prompt mentions (case-insensitive, whole word; 'bank uncle' and 'bank_uncle' both count)."""
    members = members or load()
    found = []
    for name in members:
        pattern = r"\b" + re.escape(name.replace("_", " ")) + r"\b|\b" + re.escape(name) + r"\b"
        if re.search(pattern, prompt, re.IGNORECASE):
            found.append(name)
    return found


def refs_for(prompt: str, channel: str = "sglearning", members: dict | None = None, draw_missing: bool = True, **kw) -> list:
    members = members or load()
    out = []
    for name in mentioned(prompt, members)[:3]:                 # the image model takes a few references well; more dilutes them
        png = cast_dir(channel) / f"{name}.png"
        if not png.exists() and draw_missing:
            draw(name, channel, members, **kw)
        if png.exists():
            out.append(png)
    return out


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="draw every missing cast member for a channel")
    ap.add_argument("--channel", default="sglearning", choices=["sglearning", "arthvan"])
    a = ap.parse_args(argv)
    members = load()
    for name in members:
        print(("kept " if (cast_dir(a.channel) / f"{name}.png").exists() else "drew ") + name, flush=True)
        draw(name, a.channel, members=members, spend=Path("out") / "cast-spend.json")   # its own spend file: the day's video budget is untouched
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
