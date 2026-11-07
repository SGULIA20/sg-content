"""One scoring rule for topics, built from what viewers are watching on YouTube and not from our own Reels (founder, 7 Nov 2026:
"don't research my reels, research YouTube", then "build the scoring rule for topics").

Evidence (engine/ytresearch.py, the most-viewed Hindi videos in India over 14 days to 7 Nov 2026):
  finance  - gold and silver crash videos 2.1M, 373K and 316K views; "PNB Rs 35 crore fraud" 1.2M; "banking shut, UPI shut, crash coming?" 1.4M;
             "Rs 1 crore in FD, biggest mistake? tax trick" 528K; "should you stop your SIP now?" 378K. A scare or a choice tied to the
             viewer's own money, with a number.
  mythology - "How was Vishnu's head cut off? (Hayagriva)" 6.2M; "Ravana kidnapped Rama's mother" 3.6M; Surpanakha misconception 1.7M;
             temple that vanishes twice a day 1.2M; festival stories (Karva Chauth, Diwali, Sharad Purnima) 1.4-3M each. A famous name, a shock
             question, an untold angle, and the festival of the week.
Company results, roundups and party politics score down; an obscure site with no famous name and no mystery scores low.

score(text, channel, today) -> (points, reasons). python -m engine.topicscore prints the banks in the order they would now be picked.
"""
import re
from datetime import date, datetime, timedelta
from pathlib import Path

import yaml

from .config import CONTENT_DIR

SCARE = ["crash", "girawat", "gira ", "girna", "dhadam", "plunge", "collapse", "bubble", "fraud", "scam", "loot", "band ", "default", "panic",
         "scare", "dooba", "dubaya", "doob", "hack", "ban ", "fine", "penalty", "shock"]
WALLET = ["gold", "silver", "sona", "chandi", "petrol", "diesel", "emi", "loan", "fd ", "fixed deposit", "tax", "sip", "mutual fund", "upi", "bank",
          "salary", "pension", "ppf", "epf", "nps", "rent", "insurance", "credit card", "cibil", "gst", "rupee", "inflation", "mehngai", "lpg",
          "savings", "deposit", "refund", "atm"]
DECISION = ["should you", "sahi", "khareed", "becho", "rukein", "stop", "band karein", "kaun sa", "ya ", "better", "galti", "mistake", "trick"]
QUESTION = ["?", "kyun", "kyon", "kaise", "kya ", "kab ", "kitna", "kisne", "kaun", "why", "how", "what"]
NUMBER = re.compile(r"\d|lakh|crore|%|\$|₹")
CORPORATE = ["quarterly", "q1 ", "q2 ", "q3 ", "q4 ", "net profit", "profit rises", "profit jumps", "profit falls", "results", "earnings", "revenue",
             "ebitda", "stake", "acquisition", "merger", "takeover", "ipo", "funding", "valuation", "ceo", "chairman", "board meeting"]
ROUNDUP = ["top 10", "10 badi khabrein", "khabrein", "roundup", "round-up", "news today", "market wrap", "today's"]
BANNED = ["modi", "rahul gandhi", "bjp", "congress", "election", "rally", "pakistan", "minister", "parliament"]
TOP_FAMOUS = ["mahabharat", "ramayan", "shiv", "mahadev", "vishnu", "krishna", "hanuman", "ram setu", "ravan", "kedarnath", "kailash", "jagannath",
              "dwarka", "lakshmi", "ganesh", "diwali"]
FAMOUS = ["mahabharat", "ramayan", "shiv", "mahadev", "vishnu", "krishna", "hanuman", "ram setu", "ram ", "ravan", "dwarka", "kedarnath", "kailash",
          "kailasa", "jagannath", "konark", "somnath", "tirupati", "balaji", "ayodhya", "kashi", "varanasi", "ganga", "lakshmi", "ganesh", "durga",
          "kali", "sita", "arjun", "karna", "draupadi", "ashoka", "ashwatthama", "chakravyuh", "harappa", "nalanda", "sanchi", "ajanta", "ellora"]
SHOCK = ["kaise", "kyun", "kyon", "kisne", "rahasya", "raaz", "sach", "untold", "mystery", "secret", "chamatkar", "shraap", "curse", "gayab",
         "zinda", "ajeeb", "hairan", "pehli baar", "kabhi nahi", "asli", "sabut", "hidden", "lost"]
UNTOLD = ["untold", "galatfehmi", "misconception", "jo kisi ne", "kam log", "nahi bataya", "alag", "asli kahani", "sabse badi"]


def _parts(topic) -> tuple:
    """(headline text, background text): the title and hooks are what a viewer sees first, so a feature found there counts in full and
    one found only in the summary counts for half."""
    if isinstance(topic, str):
        return f" {topic.lower()} ", " "
    head = " ".join(str(p) for p in (topic.get("title"), topic.get("title_hi"), topic.get("place"), " ".join(topic.get("hooks") or [])) if p)
    back = " ".join(str(p) for p in (topic.get("summary"), topic.get("notes")) if p)
    return f" {head.lower()} ", f" {back.lower()} "


def load_calendar(content: Path = CONTENT_DIR) -> list:
    try:
        return yaml.safe_load((Path(content) / "festival-calendar.yaml").read_text()) or []
    except (OSError, yaml.YAMLError):
        return []


def festival(blob: str, today: date, calendar: list) -> str | None:
    """The name of the festival this text is timely for today, if any."""
    for ev in calendar:
        try:
            d = ev["date"] if isinstance(ev["date"], date) else datetime.strptime(str(ev["date"]), "%Y-%m-%d").date()
        except ValueError:
            continue
        if d - timedelta(days=int(ev.get("lead_days", 3))) <= today <= d + timedelta(days=int(ev.get("after_days", 1))):
            if any(re.search(rf"\b{re.escape(str(t).lower())}", blob) for t in ev.get("terms", [])):
                return ev.get("name")
    return None


def score(topic, channel: str, today: date | None = None, calendar: list | None = None) -> tuple:
    """(points, reasons): higher is a better topic for this channel today."""
    head, back = _parts(topic)
    both = head + back
    today = today or date.today()
    pts, why = 0, []

    def add(n, label):
        nonlocal pts
        pts += n
        why.append(f"{n:+d} {label}")

    def feature(words, n, label, penalty=False):
        """Full points when a word is in the headline, half (at least 1) when only in the background text."""
        if any(w in head for w in words):
            add(n, label)
        elif any(w in back for w in words):
            add(-(max(1, abs(n) // 2)) if penalty else max(1, n // 2), label + " (in the summary)")
    if any(b in both for b in BANNED):
        return -10, ["-10 party politics"]
    if channel == "sglearning":
        feature(WALLET, 3, "touches the viewer's own money")
        feature(SCARE, 3, "a scare or a crash")
        feature(DECISION, 1, "a choice the viewer faces")
        feature(CORPORATE, -4, "company results or deals", penalty=True)
        feature(ROUNDUP, -4, "a roundup, not one story", penalty=True)
    else:
        if any(w in head for w in TOP_FAMOUS):
            add(4, "one of the most-watched names")
        elif any(w in both for w in FAMOUS):
            add(2, "a famous name")
        else:
            add(-2, "no famous name")
        feature(SHOCK, 3, "a shock question or a mystery")
        feature(UNTOLD, 2, "an untold angle")
        fest = festival(both, today, calendar if calendar is not None else load_calendar())
        if fest:
            add(3, f"timely: {fest}")
    if NUMBER.search(head):
        add(1, "a concrete number")
    if any(w in head for w in QUESTION):
        add(1, "asks a question")
    return pts, why


def rank(topics: list, channel: str, today: date | None = None, calendar: list | None = None) -> list:
    """[(points, reasons, topic)], best first; ties keep the bank's own order."""
    scored = [(*score(t, channel, today, calendar), t) for t in topics]
    return sorted(scored, key=lambda r: -r[0])


def main(argv=None) -> int:
    from . import topics
    today = date.today()
    print(f"Learning with SG money-history bank, best first ({today}):")
    for pts, why, t in rank(topics.load_money_history(), "sglearning", today)[:12]:
        print(f"  {pts:>3}  {t['id']}  [{'; '.join(why)}]")
    print("SG-MYTH-WORLD bank, best first:")
    for pts, why, t in rank(topics.load_myth_bank(), "arthvan", today)[:12]:
        print(f"  {pts:>3}  {t['id']}  [{'; '.join(why)}]")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
