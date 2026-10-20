"""The recurring drawn cast (content/cast.yaml): one reference picture per member, drawn once in the channel's doodle style; panels that name a
member get that picture as a reference so faces stay the same across reels. SG is drawn from the founder's own photos."""
import re
from pathlib import Path

import yaml

from . import art
from .config import ASSETS_DIR, CONTENT_DIR

CAST_FILE = CONTENT_DIR / "cast.yaml"
CAST_DIR = ASSETS_DIR / "cast"
SHEET_PROMPT = ("Character reference sheet, single character, full body facing the camera, neutral stance, plain off-white background. {description}. "
                "Keep this exact face and clothes so the character is recognisable in every later panel.")


def load(path: Path = CAST_FILE) -> dict:
    return yaml.safe_load(Path(path).read_text()) or {}


def draw(name: str, channel: str = "sglearning", members: dict | None = None, **kw) -> Path:
    members = members or load()
    m = members[name]
    out = CAST_DIR / f"{name}.png"
    if out.exists():
        return out
    refs = [ASSETS_DIR / "reference" / r for r in m.get("refs", [])]
    prompt = art.style_prompt(channel, SHEET_PROMPT.format(description=m["description"]))
    if refs:
        prompt = "Draw this real person as a doodle cartoon character, recognisable from the reference photos. " + prompt
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
        png = CAST_DIR / f"{name}.png"
        if not png.exists() and draw_missing:
            draw(name, channel, members, **kw)
        if png.exists():
            out.append(png)
    return out


def main(argv=None) -> int:
    members = load()
    for name in members:
        print(("kept " if (CAST_DIR / f"{name}.png").exists() else "drew ") + name, flush=True)
        draw(name, members=members)
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
