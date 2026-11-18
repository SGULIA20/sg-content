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
    ("rbi", [" rbi", "reserve bank", "repo rate", "monetary policy"]),     # its own theme, ahead of loan and bank, so Shorts can leave it out (18 Nov 2026)
    ("gold", ["gold", "sona", "sone ", "silver", "chandi"]),
    ("loan", ["loan", " emi", "credit card", "cibil", "karz", "udhaar"]),
    ("tax", [" tax", "gst", "tds", "itr"]),
    ("insurance", ["insurance", "bima", "claim"]),
    ("jobs", ["naukri", "salary", " job", " pf ", "epf", "pension", "layoff", "hadtaal", "tankhwah", "gig "]),
    ("payments", ["upi", " note", "cash", "atm", "wallet", "digital payment"]),
    ("bank", ["bank", " fd", "fixed deposit", "deposit", "moratorium", "byaaj", "interest rate"]),
    ("prices", ["petrol", "diesel", "mehngai", "inflation", "daam", "price", "pyaaz", "onion", "lpg", "rupaya", "rupee", "kiraya", "fare", "tel "]),
    ("business", ["company", "startup", "airline", "telecom", "data ", "brand", "factory", "mill "]),
]
# SG-MYTH-WORLD (founder, 18 Nov 2026: "we are following the same topic for 7-8 days ... every day a new topic, altogether different from
# the previous one"; six of the nine pieces of 16-24 Nov were Ramayan stories). First match wins: Hanuman is a Ramayan story, Jagannath a
# Krishna one, a festival named for a deity counts as the festival.
MYTH_THEMES = [
    ("ramayan", ["ramayan", " ram ", "ram setu", "ravan", "sita", "hanuman", "lanka", "lakshman", "laxman", "jatayu", "surpanakha", "shurpanakha",
                 "manthara", "kaushalya", "kaikeyi", "dashrath", "ayodhya", "valmiki", "sugriv", "kishkindha", "anjan", "bharat milap", "kumbhkaran",
                 "meghnad", "vibhishan", "shabari"]),
    ("mahabharat", ["mahabharat", " karna ", "karna ne", "karna ka", "arjun", "pandav", "kaurav", "draupadi", "kurukshetra", "bhishma", "ashwatthama", "duryodhan", "chakravyuh",
                    "abhimanyu", " gita", "yudhishthir", "bhim ", "eklavya", "barbarik", "shakuni", "dronacharya"]),
    ("festival", ["diwali", "deepawali", "dev uthani", "holi", "navratri", "purnima", "ekadashi", " vrat", "chhath", "kumbh mela", "mahakumbh", " mela",
                  "tulsi vivah", "sankranti", "shivratri", "janmashtami", "rath yatra", "dussehra", "karva"]),
    ("krishna", ["krishna", "dwarka", "vrindavan", "mathura", "radha", "jagannath", "puri ", "govardhan", "kanha", "banke bihari"]),
    ("shiva", ["shiv", "mahadev", "kailash", "kedarnath", "jyotirling", "tripur", "kashi", "nataraj", "amarnath", "somnath", "rudra", "bholenath",
               "kirtimukha", "nandi", "mahakal"]),
    ("vishnu", ["vishnu", "tirupati", "balaji", "narayan", "shaligram", "dashavatar", "narasimha", "vaikunth", "padmanabh", "badrinath", "varaha", "vaman"]),
    ("devi", ["devi", "durga", "kali ", "shakti", "yogini", "kamakhya", "lakshmi", "saraswati", "parvati", " sati", "vaishno", "chamunda"]),
    ("history", ["fort", " kila", "qila", "stupa", "pillar", "stambh", "harappa", "rakhigarhi", "indus", "library", "nalanda", "takshashila", "crater",
                 "jheel", "cave", "gufa", "ellora", "ajanta", "mahabalipuram", "empire", "samrajya", " raja", "rani ", "sanchi", "hampi", "konark",
                 "khajuraho", "lonar", "kumbhalgarh", "asirgarh", "unakoti", "archaeolog", "asi ", "khudai", "sikka", "coin", "inscription", "shilalekh"]),
    ("temple", ["mandir", "temple", "dham", "tirth"]),
]
GAP = {"market": 7}
MYTH_GAP = 2                                 # the same theme at most every third day on SG-MYTH-WORLD
DEFAULT_GAP = 3
SKIP_STATUS = ("rejected", "failed")
# founder, 18 Nov 2026 ("Yes drop stock market and RBI headlines from Learning Shorts"): on Instagram three of four viewers swiped away
# from these in the first 3 seconds (76-82 percent, against 37-41 for SG-MYTH the same evenings). Long videos may still take them.
NEVER_SHORT = ("market", "rbi")


def never(piece) -> tuple:
    """Themes this piece may never take, whatever else is left."""
    short = getattr(piece, "kind", None) == "short" or str(getattr(piece, "id", "")).endswith("-short")
    return NEVER_SHORT if (piece.channel == "sglearning" and short) else ()


def theme_of(topic, channel: str = "sglearning") -> str:
    """The topic's theme, or "" when nothing matches (such a topic never clashes)."""
    if not topic:
        return ""
    if topic.get("theme"):
        return str(topic["theme"])
    head = " " + " ".join(str(x) for x in (topic.get("title"), topic.get("title_hi"), " ".join(topic.get("hooks") or [])) if x).lower() + " "
    back = " " + " ".join(str(topic.get(k) or "") for k in ("summary", "place", "notes")).lower() + " "
    for blob in (head, back):
        for name, words in (MYTH_THEMES if channel == "arthvan" else THEMES):
            if any(w in blob for w in words):
                return name
    return ""


def gap(theme: str, channel: str = "sglearning") -> int:
    return MYTH_GAP if channel == "arthvan" else GAP.get(theme, DEFAULT_GAP)


def blocked(root: Path, piece, extra=()) -> set:
    """Themes `piece` may not take. `extra` is [(day, theme)] for topics planned but not yet saved as pieces (the weekly plan)."""
    near = [(p.publish_day, theme_of(p.topic, piece.channel)) for p in pieces.list_all(root)
            if p.channel == piece.channel and p.id != piece.id and not str(p.status).startswith(SKIP_STATUS)]
    out = set(never(piece))
    for day, th in list(near) + list(extra):
        if th and abs((day - piece.publish_day).days) <= gap(th, piece.channel):
            out.add(th)
    return out


def allowed(topic, avoid, channel: str = "sglearning") -> bool:
    return theme_of(topic, channel) not in set(avoid or ())
