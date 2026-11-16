"""Which pieces are written and spoken in English (founder, 16 Nov 2026: "for SG learning keep all future scripts and founder scripts in
English only"; "Yes, English from 23 November"). content/language.json names the first publish day per channel; pieces before it, and
channels not named, stay Hinglish. Everything language-specific asks here: the writer's rules, the fixed lines the checks look for, the
founder's closing lines, the YouTube language."""
import json
from pathlib import Path

from .config import CONTENT_DIR

DISCLAIMER_HI = "Yeh investment advice nahi hai"
DISCLAIMER_EN = "This is not investment advice"
TAGLINE_EN = {"sglearning": "Money news, straight talk"}
CLOSINGS_EN = ["Stay with me, here is the twist!",
               "Wait, the real story starts now!",
               "Nobody tells you this part, listen!",
               "The twist is coming!",
               "You won't believe what comes next!",
               "Let me open this up, step by step!",
               "Don't skip this, you need to see it!",
               "Watch closely, this will surprise you!"]


def _config(root: Path = None) -> dict:
    try:
        return json.loads(((Path(root) if root else CONTENT_DIR) / "language.json").read_text())
    except (OSError, ValueError):
        return {}


def english(piece, root: Path = None) -> bool:
    start = (_config(root).get(getattr(piece, "channel", "")) or {}).get("english_from")
    return bool(start) and str(getattr(piece, "publish_day", "") or str(piece.id)[:10])[:10] >= start


def disclaimer(piece, root: Path = None) -> str:
    return DISCLAIMER_EN if english(piece, root) else DISCLAIMER_HI


def english_rules() -> str:
    return (CONTENT_DIR / "prompts" / "english-sglearning.txt").read_text()


def say_number(n: int) -> str:
    """A rupee-style number the founder can say in English in one breath: 95,93,875 -> "about 96 lakh"; 1,50,000 -> "1.5 lakh"."""
    def fmt(x: float, unit: str) -> str:
        r = round(x, 1)
        text = str(int(r)) if r == int(r) else str(r)
        return ("about " if abs(x - r) > 1e-9 else "") + f"{text} {unit}"
    if n >= 10000000:
        return fmt(n / 10000000, "crore")
    if n >= 100000:
        return fmt(n / 100000, "lakh")
    if n >= 1000:
        return fmt(n / 1000, "thousand")
    return str(n)
