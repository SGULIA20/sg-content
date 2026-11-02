"""News cards drawn in code for the news Reels (founder, 30 Oct 2026: "use graphics made internally by claude with zero cost" for the Top 10
and the 3-4 daily breaking-news Reels). One card per scene: a tag, a big icon, the number and a few plain words; the narration's
captions run underneath as usual. No picture model is called, so a news Reel costs only its voice and its script."""
import re
from pathlib import Path

ACCENT = {"ai": "#7C5CFF", "tech": "#3BA4FF", "crypto": "#F7931A", "markets": "#22C55E", "economy": "#FFD166", "jobs": "#FF6B6B",
          "companies": "#3BA4FF", "commodities": "#FFB703", "money": "#FFD166", "world": "#EF476F", "numbers": "#FFD166"}
ICONS = [("bitcoin", "🪙"), ("crypto", "🪙"), ("hack", "🕵️"), ("ai ", "🤖"), ("google", "🔍"), ("chip", "💾"), ("oil", "🛢️"),
         ("crude", "🛢️"), ("gold", "🥇"), ("silver", "🥈"), ("rupee", "💱"), ("rupaya", "💱"), ("dollar", "💵"), ("job", "💼"),
         ("layoff", "📦"), ("naukri", "💼"), ("bank", "🏦"), ("loan", "🏦"), ("emi", "🏦"), ("tax", "🧾"), ("gira", "📉"), ("fall", "📉"),
         ("upar", "📈"), ("badh", "📈"), ("china", "🌏"), ("america", "🌎"), ("us ", "🌎"), ("japan", "🌏"), ("sip", "🌱"),
         ("phone", "📱"), ("car", "🚗"), ("ev", "🔋"), ("startup", "🚀"), ("ipo", "🔔"), ("price", "🏷️"), ("daam", "🏷️")]
NUMBER = re.compile(r"(?:[$₹]\s?)?\d[\d,.]*\s?(?:%|percent|crore|lakh|billion|million|trillion|bn)?", re.I)


def icon_for(text: str) -> str:
    blob = f" {text.lower()} "
    return next((emoji for word, emoji in ICONS if word in blob), "📰")


def data(scene: dict, index: int, total: int, category: str, roundup: bool) -> dict:
    """What the card shows: the writer's card block when given, else drawn from the narration."""
    card = ((scene.get("visual") or {}).get("card") or {}) if (scene.get("visual") or {}).get("type") == "card" else {}
    vo = str(scene.get("vo") or "")
    num = card.get("big_number")
    if num is None:
        m = NUMBER.search(vo)
        num = m.group(0).strip() if m else ""
    line = card.get("line") or " ".join(re.sub(r"[^\w\s%₹$.,]", "", vo).split()[:6])
    if index == 0 and vo:                    # 1 Nov 2026: the first 2 seconds decide; frame 1 carries the spoken question itself
        line = " ".join(vo.split()[:10])
    if roundup and 0 < index < total - 1:
        tag = f"#{index}"
    else:
        tag = card.get("tag") or ("BREAKING" if index == 0 else category.upper())
    cat = category if category in ACCENT else "money"
    return {"tag": tag, "icon": card.get("icon") or icon_for(vo), "big_number": num, "line": line, "accent": ACCENT[cat],
            "glow": ACCENT[cat] + "55"}


# 2 Nov 2026 (founder): the Claude-drawn Reels move every second, like the motion Reels that hold people: a progress bar of the story's
# steps, the icon popping in on a tilting tile, the number counting up and the line appearing word by word. The daily painted Shorts are
# not touched.
MOTION = True
MOTION_FPS = 15
NEWS_STEPS = ["SAWAAL", "KYA HUA", "KYUN", "ASAR", "AAPKA PAISA", "KYA KAREIN", "YAAD RAKHO", "BHEJO"]


def step_name(index: int, total: int, roundup: bool) -> str:
    if roundup:
        return "TOP 10" if index == 0 else ("BHEJO" if index == total - 1 else f"#{index}")
    if index == total - 1:
        return "BHEJO"
    return NEWS_STEPS[min(index, len(NEWS_STEPS) - 2)]


def animate(data: dict, index: int, total: int, roundup: bool, seconds: float, size: tuple, out: Path, fps: int = MOTION_FPS) -> Path:
    """Renders the moving card for one scene to an mp4 by drawing every frame with seek(t) in the headless browser."""
    import subprocess
    from . import cards
    tpl = (cards.TEMPLATES_DIR / "newscardmotion.html").read_text()
    fields = {**data, "words": str(data.get("line") or "").split(), "tag": step_name(index, total, roundup), "pop": ""}
    from . import storyframe
    limit = size[1] - storyframe.CAP_H - storyframe.LIFT - 30           # the card's text ends above the captions
    page_html = cards._fill(tpl.replace("{{D}}", f"{seconds:.3f}").replace("{{I}}", str(index)).replace("{{N}}", str(total))
                            .replace("{{LIMIT}}", str(limit)), fields, size)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".html")
    tmp.write_text(page_html)
    page = cards._browser().new_page(viewport={"width": size[0], "height": size[1]}, device_scale_factor=1)
    ff = subprocess.Popen(["ffmpeg", "-loglevel", "error", "-y", "-f", "image2pipe", "-framerate", str(fps), "-i", "-", "-c:v", "libx264",
                           "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", str(out)], stdin=subprocess.PIPE)
    try:
        page.goto(tmp.as_uri())
        page.wait_for_function("document.fonts.ready.then(() => true)")
        for f in range(max(1, int(round(seconds * fps)))):
            page.evaluate(f"seek({f / fps:.4f})")
            ff.stdin.write(page.screenshot(type="jpeg", quality=90, clip={"x": 0, "y": 0, "width": size[0], "height": size[1]}))
    finally:
        page.close()
        ff.stdin.close()
        ff.wait()
        tmp.unlink(missing_ok=True)
    if ff.returncode != 0:
        raise RuntimeError(f"ffmpeg could not encode {out.name}")
    return out

