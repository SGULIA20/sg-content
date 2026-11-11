"""One theme per Learning with SG topic, and the gap between two videos of the same theme (founder, 11 Nov 2026: "why only SIP, Sensex?
... should not repeat in future ... viewers will feel bored").

A topic's theme is its own `theme` field (the banks carry one) or, for news and weekly-plan topics, the first keyword list below that
matches its title and hooks, then its summary. blocked(root, piece) gives the themes a new piece may not take: any theme another
piece of the same channel (Short or long, made or planned) has within GAP days of it. Share market / SIP waits a full week; with
nine videos a week and ten themes a full week for every theme cannot be met, so the others wait three days.
"""
from pathlib import Path

from . import pieces

THEMES = [                                    # first match wins: a bank fraud is a scam story, not a bank story
    ("scam", ["scam", "fraud", "ghotala", "chit fund", "ponzi", "loot", "thagi", "fake ", "farzi"]),
    ("market", ["sensex", "nifty", "share", "stock", " sip", "mutual fund", "ipo", "demat", "circuit", "bull run", "market", "fii", "dalal"]),
    ("gold", ["gold", "sona", "sone ", "silver", "chandi"]),
    ("loan", ["loan", " emi", "credit card", "cibil", "karz", "udhaar"]),
    ("tax", [" tax", "gst", "tds", "itr"]),
    ("insurance", ["insurance", "bima", "claim"]),
    ("jobs", ["naukri", "salary", " job", " pf ", "epf", "pension", "layoff", "hadtaal", "tankhwah", "gig "]),
    ("payments", ["upi", " note", "cash", "atm", "wallet", "digital payment"]),
    ("bank", ["bank", " fd", "fixed deposit", "deposit", "rbi", "moratorium", "byaaj", "interest rate"]),
    ("prices", ["petrol", "diesel", "mehngai", "inflation", "daam", "price", "pyaaz", "onion", "lpg", "rupaya", "rupee", "kiraya", "fare", "tel "]),
    ("business", ["company", "startup", "airline", "telecom", "data ", "brand", "factory", "mill "]),
]
GAP = {"market": 7}
DEFAULT_GAP = 3
SKIP_STATUS = ("rejected", "failed")


def theme_of(topic) -> str:
    """The topic's theme, or "" when nothing matches (such a topic never clashes)."""
    if not topic:
        return ""
    if topic.get("theme"):
        return str(topic["theme"])
    head = " " + " ".join(str(x) for x in (topic.get("title"), topic.get("title_hi"), " ".join(topic.get("hooks") or [])) if x).lower() + " "
    back = " " + str(topic.get("summary") or "").lower() + " "
    for blob in (head, back):
        for name, words in THEMES:
            if any(w in blob for w in words):
                return name
    return ""


def gap(theme: str) -> int:
    return GAP.get(theme, DEFAULT_GAP)


def blocked(root: Path, piece, extra=()) -> set:
    """Themes `piece` may not take. `extra` is [(day, theme)] for topics planned but not yet saved as pieces (the weekly plan)."""
    near = [(p.publish_day, theme_of(p.topic)) for p in pieces.list_all(root)
            if p.channel == piece.channel and p.id != piece.id and not str(p.status).startswith(SKIP_STATUS)]
    out = set()
    for day, th in list(near) + list(extra):
        if th and abs((day - piece.publish_day).days) <= gap(th):
            out.add(th)
    return out


def allowed(topic, avoid) -> bool:
    return theme_of(topic) not in set(avoid or ())
