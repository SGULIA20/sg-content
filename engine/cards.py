"""HTML cards rendered to PNG with one headless Chromium per process: hook, number, source strip, label chip, end card, thumbnail, carousel slide (spec §3 step 7, §C)."""
import atexit
import html
import tempfile
from pathlib import Path

from .config import ASSETS_DIR, TEMPLATES_DIR

KINDS = {"hook", "number", "source", "label", "end", "thumb", "slide", "caption", "avatar", "story", "storytitle", "storycap", "thumb2", "storyend", "logo", "banner"}
TRANSPARENT = {"label", "caption", "logo"}
BG = "#0B0F1A"
_PW = None
_BROWSER = None


def _browser():
    global _PW, _BROWSER
    if _BROWSER is None:
        from playwright.sync_api import sync_playwright
        _PW = sync_playwright().start()
        _BROWSER = _PW.chromium.launch()
        atexit.register(_close)
    return _BROWSER


def _close():
    global _PW, _BROWSER
    try:
        if _BROWSER:
            _BROWSER.close()
        if _PW:
            _PW.stop()
    finally:
        _PW = _BROWSER = None


def _fill(template: str, data: dict, size: tuple) -> str:
    fonts = (Path(ASSETS_DIR) / "fonts").resolve().as_uri()
    out = template.replace("{{FONTS}}", fonts).replace("{{W}}", str(size[0])).replace("{{H}}", str(size[1]))
    for key, val in data.items():
        if isinstance(val, (list, tuple)):
            val = "".join(f"<span class=\"w\">{html.escape(str(v))}</span>" for v in val)
        elif val is None:
            val = ""
        elif key.endswith("_path"):
            val = Path(val).resolve().as_uri()
        elif key.endswith("_html"):
            val = str(val)                                   # already-safe markup from the caller (storyframe.title_html escapes text)
        else:
            val = html.escape(str(val))
        out = out.replace("{{" + key + "}}", val)
    import re
    return re.sub(r"\{\{[a-z_]+\}\}", "", out)          # unused placeholders disappear


def render(kind: str, data: dict, out: Path, size: tuple, templates: Path = TEMPLATES_DIR) -> Path:
    if kind not in KINDS:
        raise KeyError(f"unknown card kind {kind!r}")
    template = (Path(templates) / f"{kind}.html").read_text()
    page_html = _fill(template, data, size)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, dir=out.parent) as f:
        f.write(page_html)
        tmp = Path(f.name)
    try:
        page = _browser().new_page(viewport={"width": size[0], "height": size[1]}, device_scale_factor=1)
        page.goto(tmp.as_uri())
        page.wait_for_function("document.fonts.ready.then(() => true)")
        page.screenshot(path=str(out), clip={"x": 0, "y": 0, "width": size[0], "height": size[1]},
                        omit_background=(kind in TRANSPARENT))
        page.close()
    finally:
        tmp.unlink(missing_ok=True)
    return out
