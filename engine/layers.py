"""Layers on the painted daily Shorts (founder, 2 Nov 2026: "go to build it"). The Gemini picture stays exactly as it is; code draws on top:
a badge with the number the voice says (pops in, stays about 3 s), a progress bar of the Reel, and sound cues (whoosh, pop, tick).
The test alternates days from 5 Nov 2026: layers on one day, off the next (the picture and voice are identical both ways). Each piece
records its arm in piece.topic["layers"], so the Monday and Thursday reports can compare the two.

Not in this first version: the word-by-word caption highlight and the fixed highlight ring (the sample showed a ring in the centre of
every picture, which looked random). Both can come later, per scene, once the test shows the layers help."""
import re
from datetime import date
from pathlib import Path

from .config import ASSETS_DIR

TEST_START = date(2026, 11, 5)
LAYERED_CHANNELS = ("sglearning", "arthvan")
BADGE_SECONDS = 3.0                      # the badge pops in at 0.4 s and stays this long
POP_AT = 0.4
BAR_HEIGHT = 8
UNIT = re.compile(r"(?:₹|rs\.?\s?|\$)?\s?\d[\d,]*(?:\.\d+)?\s?(%|percent|lakh|crore|billion|million|trillion|bn|dollar|rupaye|rupees|rupay)?",
                  re.IGNORECASE)
YEAR = re.compile(r"^(19|20)\d\d$")


def on_for(day: date) -> bool:
    """Alternate days from the test start: the start day has layers, the next day none, and so on. Before the test: none."""
    if day < TEST_START:
        return False
    return (day - TEST_START).days % 2 == 0


def apply(piece, day: date | None = None) -> bool:
    """Decides this piece's arm and records it. Only the painted daily Shorts of the two channels; the code-drawn news, extra and Top 10
    Reels already have their own moving cards."""
    day = day or piece.publish_day
    t = {**((piece.topic or {}).get("preset") or {}), **(piece.topic or {})}
    cards_already = bool(t.get("graphics") or t.get("news") or t.get("extra") or t.get("roundup"))
    eligible = piece.kind == "short" and piece.channel in LAYERED_CHANNELS and not cards_already
    on = eligible and on_for(day)
    if eligible:
        piece.topic["layers"] = on
    return on


def badge_text(vo: str) -> str | None:
    """The first figure the voice says, as the badge shows it: '21.43 percent' -> '21.43%'. Years and bare numbers are skipped."""
    for m in UNIT.finditer(vo or ""):
        raw = m.group(0).strip()
        if YEAR.match(raw.replace(",", "")) and not m.group(1):
            continue
        if not m.group(1) and not raw.startswith(("₹", "$", "Rs")):
            continue
        text = re.sub(r"\s+", " ", raw).replace("percent", "%").replace("rupaye", "").replace("rupees", "").strip()
        text = re.sub(r"\s?%", "%", text)
        if len(text) > 16:
            text = text[:16]
        return text
    return None


def _font(size: int):
    from PIL import ImageFont
    for path in (Path(ASSETS_DIR) / "fonts" / "Inter.ttf",):
        try:
            return ImageFont.truetype(str(path), size)
        except OSError:
            pass
    return ImageFont.load_default()


def badge_png(text: str, out: Path) -> Path:
    from PIL import Image, ImageDraw
    f = _font(60)
    probe = ImageDraw.Draw(Image.new("RGBA", (4, 4)))
    l, t, r, b = probe.textbbox((0, 0), text, font=f)
    w, h = r - l + 60, b - t + 34
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, w - 1, h - 1], radius=26, fill=(255, 225, 77, 235))
    d.text((30 - l, 17 - t), text, font=f, fill=(0, 0, 0, 255))
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out)
    return out


def bar_png(size: tuple, step: int, steps: int, out: Path, x0: int, y: int) -> Path:
    """A full-width progress track, filled up to this scene's step. Drawn once per scene, transparent elsewhere."""
    from PIL import Image, ImageDraw
    w, h = size
    im = Image.new("RGBA", (w, y + BAR_HEIGHT + 4), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    span = w - 2 * x0
    d.rounded_rectangle([x0, y, w - x0, y + BAR_HEIGHT], radius=4, fill=(255, 255, 255, 70))
    frac = (step + 1) / max(steps, 1)
    d.rounded_rectangle([x0, y, x0 + int(span * frac), y + BAR_HEIGHT], radius=4, fill=(255, 225, 77, 255))
    out = Path(out)
    im.save(out)
    return out


def scene_overlays(text: str | None, step: int, steps: int, size: tuple, out_dir: Path, top: int, side: int, badge_y: int, dur: float) -> list:
    """(png, x, y, start, end) for one scene, timed to the scene clip (seconds from the scene's own start)."""
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    out = [(bar_png(size, step, steps, Path(out_dir) / f"bar{step:02d}.png", side, top + 10), 0, 0, 0.0, dur)]
    if text:
        png = badge_png(text, Path(out_dir) / f"badge{step:02d}.png")
        out.append((png, side, badge_y, POP_AT, min(dur - 0.1, POP_AT + BADGE_SECONDS)))
    return out


def sfx_events(start: float, text: str | None) -> list:
    """Sound cues for a layered scene: a whoosh as the scene starts, and a pop and a tick with the badge."""
    out = [(start + 0.05, "whoosh")]
    if text:
        out += [(start + POP_AT, "pop"), (start + 1.15, "tick")]
    return out
