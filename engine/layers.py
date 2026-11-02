"""Layers on the painted daily Shorts (founder, 2 Nov 2026). The Gemini picture and voice stay exactly as they are; code draws on top:
a progress bar of the Reel, and a bar chart in the scenes that compare figures (2 or more numbers the voice says). No sound cues and no
single-number badges: the bold caption already shows the number (founder, 2 Nov 2026: "remove sound cues, it's irritating"; "21.43% was
not necessary, already in the caption").

The test alternates days from 5 Nov 2026: layers on one day, off the next. Each piece records its arm in piece.topic["layers"]."""
import re
from datetime import date
from pathlib import Path

from .config import ASSETS_DIR

TEST_START = date(2026, 11, 5)
LAYERED_CHANNELS = ("sglearning", "arthvan")
BAR_HEIGHT = 8
CHART_AT = 0.5                                         # the chart appears after the picture has settled
FIG = re.compile(r"(₹|rs\.?\s?|\$)?\s?(\d[\d,]*(?:\.\d+)?)\s?(%|percent|lakh|crore|billion|million|trillion|bn|dollar|rupaye|rupees)?",
                 re.IGNORECASE)
YEAR = re.compile(r"^(19|20)\d\d$")


def on_for(day: date) -> bool:
    """Alternate days from the test start: the start day has layers, the next day none, and so on. Before the test: none."""
    if day < TEST_START:
        return False
    return (day - TEST_START).days % 2 == 0


def apply(piece, day: date | None = None) -> bool:
    """Decides this piece's arm and records it. Only the painted daily Shorts of the two channels; the code-drawn news, extra and Top 10
    Reels have their own cards."""
    day = day or piece.publish_day
    t = {**((piece.topic or {}).get("preset") or {}), **(piece.topic or {})}
    cards_already = bool(t.get("graphics") or t.get("news") or t.get("extra") or t.get("roundup"))
    eligible = piece.kind == "short" and piece.channel in LAYERED_CHANNELS and not cards_already
    on = eligible and on_for(day)
    if eligible:
        piece.topic["layers"] = on
    return on


def figures(vo: str) -> list:
    """The figures a line says, in order: (text as spoken, value, unit). Years and bare numbers without a unit are skipped."""
    out = []
    for m in FIG.finditer(vo or ""):
        num, prefix, suffix = m.group(2), (m.group(1) or "").strip().lower(), (m.group(3) or "").strip().lower()
        if prefix:
            unit = "$" if prefix == "$" else "₹"
        elif suffix:
            unit = {"percent": "%", "rupaye": "₹", "rupees": "₹"}.get(suffix, suffix)
        else:
            continue                                            # a bare number, or a year: not a figure to chart
        if YEAR.match(num.replace(",", "")) and not prefix and not suffix:
            continue
        try:
            value = float(num.replace(",", ""))
        except ValueError:
            continue
        out.append((m.group(0).strip(), value, unit))
    return out


def comparison(vo: str) -> list | None:
    """The figures to chart: two or more in the same unit family, else None (no chart, the caption carries the number)."""
    figs = figures(vo)
    if len(figs) < 2:
        return None
    family = {f[2] for f in figs}
    if len(family) != 1:
        return None
    return [(text, value) for text, value, _unit in figs][:4]


def _font(size: int):
    from PIL import ImageFont
    try:
        return ImageFont.truetype(str(Path(ASSETS_DIR) / "fonts" / "Inter.ttf"), size)
    except OSError:
        return ImageFont.load_default()


CHART_W, CHART_H = 640, 340


def chart_png(items: list, out: Path, width: int = CHART_W, height: int = CHART_H) -> Path:
    """A small bar chart on a translucent panel, so the picture stays visible behind it: one bar per figure, the tallest in the
    accent colour, each labelled with the figure as spoken."""
    from PIL import Image, ImageDraw
    im = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, width - 1, height - 1], radius=28, fill=(0, 0, 0, 120))
    f = _font(36)
    top = max(v for _t, v in items) or 1.0
    n = len(items)
    gap = 30
    bw = (width - gap * (n + 1)) // n
    base = height - 26
    max_h = height - 110
    for i, (text, value) in enumerate(items):
        x = gap + i * (bw + gap)
        h = max(18, int(max_h * value / top))
        color = (255, 225, 77, 235) if value == top else (255, 255, 255, 150)
        d.rounded_rectangle([x, base - h, x + bw, base], radius=14, fill=color)
        l, t, r, b = d.textbbox((0, 0), text, font=f)
        d.text((x + (bw - (r - l)) // 2, base - h - (b - t) - 14), text, font=f, fill=(255, 255, 255, 255),
               stroke_width=2, stroke_fill=(0, 0, 0, 255))
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out)
    return out


def bar_png(size: tuple, step: int, steps: int, out: Path, x0: int, y: int) -> Path:
    """A full-width progress track, filled up to this scene's step."""
    from PIL import Image, ImageDraw
    w, h = size
    im = Image.new("RGBA", (w, y + BAR_HEIGHT + 4), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    span = w - 2 * x0
    d.rounded_rectangle([x0, y, w - x0, y + BAR_HEIGHT], radius=4, fill=(255, 255, 255, 70))
    frac = (step + 1) / max(steps, 1)
    d.rounded_rectangle([x0, y, x0 + int(span * frac), y + BAR_HEIGHT], radius=4, fill=(255, 225, 77, 255))
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out)
    return out


def scene_overlays(vo: str, step: int, steps: int, size: tuple, out_dir: Path, top: int, side: int, chart_y: int, dur: float) -> list:
    """(png, x, y, start, end) for one scene, timed to the scene clip (seconds from the scene's own start)."""
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    out = [(bar_png(size, step, steps, Path(out_dir) / f"bar{step:02d}.png", side, top + 10), 0, 0, 0.0, dur)]
    items = comparison(vo)
    if items:
        png = chart_png(items, Path(out_dir) / f"chart{step:02d}.png")
        out.append((png, (size[0] - CHART_W) // 2, chart_y, CHART_AT, max(CHART_AT + 0.1, dur - 0.2)))
    return out
