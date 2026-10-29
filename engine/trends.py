"""The Learning with SG research cycle (founder, 29 Oct 2026 master prompt: "research every four hours ... convert the strongest
opportunities into publish-ready content").

Every 4 hours (trends.yml) it reads the news feeds, scores what is new since the last cycles, and, when today still has room for an
extra Reel and a slot is far enough ahead, makes one (engine/extra.py) from the best fresh story; with no fresh story worth it, from the
evergreen bank (content/evergreen-sglearning.yaml). Two Learning with SG Reels in a row never share a category (YouTube's July 2026
rule against template channels). Each cycle sends one Telegram report: the top 5, what is being made, what was skipped and why, the
rest of the day.

python -m engine.trends
"""
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import yaml

from . import extra, pieces, pipeline, slots, telegram, topics
from .config import CONTENT_DIR, ROOT

CHANNEL = "sglearning"
CYCLE_HOURS = 8                       # a story counts as fresh for two cycles
SLOT_LEAD_MINUTES = 60                # a cycle only takes a slot it can still meet
# extra Reels a day on top of the daily one, ramping while views per Reel hold (founder, 29 Oct 2026, "B")
EXTRAS_FROM = [(date(2026, 10, 29), 1), (date(2026, 11, 5), 2), (date(2026, 11, 12), 3)]

CATEGORIES = {
    "jobs": topics.JOBS + ["salary", "pf ", "epf", "gratuity", "employee", "hiring", "job"],
    "ai": ["ai ", "artificial intelligence", "chatgpt", "openai", "gemini", "deepfake", "automation", "robot", "chip", "semiconductor"],
    "economy": ["gdp", "inflation", "repo", "rbi", "rupee", "gst", "budget", "export", "import", "fiscal", "monsoon", "cpi", "wpi"],
    "psychology": ["behaviour", "behavior", "bias", "psychology", "habit"],
    "management": ["ceo", "leadership", "management", "culture", "strategy", "restructuring"],
    "numbers": ["record", "crore", "billion", "trillion", "biggest", "highest", "lowest"],
}


def category(item: dict) -> str:
    blob = f" {item.get('title', '')} {item.get('summary', '')} ".lower()
    for name, words in CATEGORIES.items():
        if any(w in blob for w in words):
            return name
    return "money"


def extras_today(day: date) -> int:
    n = 0
    for start, count in EXTRAS_FROM:
        if day >= start:
            n = count
    return n


def todays_reels(root: Path, day: date) -> list:
    """Today's Learning with SG Reels in posting order: the daily one and the extras, each with its India time and category."""
    out = []
    main = pieces.load(slots.piece_id(day, CHANNEL, "short"), root)
    if main is not None:
        out.append((main.topic.get("slot_ist") or "18:30", main))
    n = 1
    while (p := pieces.load(f"{day.isoformat()}-{CHANNEL}-x{n}", root)) is not None:
        out.append((p.topic.get("slot_ist") or "23:59", p))
        n += 1
    return sorted(out, key=lambda x: x[0])


def piece_category(p) -> str:
    return p.topic.get("category") or category(p.topic)


def free_slot(root: Path, now_utc: datetime) -> str | None:
    today = slots.ist(now_utc).date()
    taken = {t for t, _p in todays_reels(root, today)}
    earliest = slots.ist(now_utc) + timedelta(minutes=SLOT_LEAD_MINUTES)
    for s in extra.EXTRA_SLOTS_IST:
        h, m = (int(x) for x in s.split(":"))
        if s not in taken and (h, m) >= (earliest.hour, earliest.minute) and earliest.date() == today:
            return s
    return None


def neighbours(root: Path, day: date, slot: str) -> set:
    """Categories of the Reels just before and just after this slot today: the new one must differ from both."""
    reels = todays_reels(root, day)
    before = [p for t, p in reels if t < slot]
    after = [p for t, p in reels if t > slot]
    return {piece_category(x) for x in (before[-1:] + after[:1])}


def load_bank(root: Path = CONTENT_DIR) -> list:
    p = Path(root) / "evergreen-sglearning.yaml"
    return yaml.safe_load(p.read_text()) if p.exists() else []


def ranked(items: list, used: set, now_utc: datetime) -> list:
    """[(score, item, why_skipped|None)] for this cycle's fresh items, best first; skipped ones carry the reason."""
    out = []
    for i in items:
        pub = i.get("published")
        if not pub or now_utc - pub > timedelta(hours=CYCLE_HOURS):
            continue
        title = str(i.get("title", "")).lower()
        why = None
        if i.get("link") in used:
            why = "already made"
        elif any(w in title for w in topics.MARKET_CALL):
            why = "daily market call (stale by evening)"
        elif topics.score(i) <= 0 or not topics.household(i):
            why = "not about the viewer's money, job or decisions"
        out.append((topics.score(i), i, why))
    return sorted(out, key=lambda x: (x[2] is None, x[0], x[1].get("published")), reverse=True)


def run(root: Path = ROOT, now_utc: datetime | None = None, items=None, notify=telegram.send, make=extra.make, bank=None) -> int:
    now_utc = now_utc or datetime.now(timezone.utc)
    root = Path(root)
    if telegram.paused(root):
        print("paused: no research cycle", flush=True)
        return 0
    today = slots.ist(now_utc).date()
    used, _prior = pipeline._used(root)
    rows = ranked(items if items is not None else topics.fetch_all(), used, now_utc)
    lines = [f"🔎 Learning with SG research, {slots.ist(now_utc):%H:%M} India"]
    top = rows[:5]
    lines += ["Top stories since the last cycles:"] + [f"  {n}. [{category(i)}] {i.get('title', '')[:90]}" + (f"  (skip: {why})" if why else "")
                                                       for n, (_s, i, why) in enumerate(top, 1)] if top else ["No new money, jobs or business stories since the last cycle."]
    room = extras_today(today) - len([1 for _t, p in todays_reels(root, today) if p.id.endswith(tuple(f"-x{k}" for k in range(1, 10)))])
    slot = free_slot(root, now_utc) if room > 0 else None
    choice, source = None, ""
    if slot:
        avoid = neighbours(root, today, slot)
        fresh = [i for _s, i, why in rows if why is None and category(i) not in avoid]
        if fresh:
            choice, source = dict(fresh[0]), "fresh news"
        else:
            spare = [t for t in (bank if bank is not None else load_bank()) if t["id"] not in used and t["category"] not in avoid]
            if spare:
                choice, source = dict(spare[0]), "evergreen bank"
        if choice:
            choice["category"] = choice.get("category") or category(choice)
            if isinstance(choice.get("published"), datetime):
                choice["published"] = choice["published"].isoformat()
            lines.append(f"Making now ({source}, {choice['category']}): {choice.get('title', '')[:100]}, posts {slot} India.")
        else:
            lines.append("Nothing suitable to make this cycle.")
    elif room <= 0:
        lines.append(f"Today's {extras_today(today)} extra Reel(s) are made; next cycle reports only.")
    else:
        lines.append("No free slot left today that this cycle can still meet.")
    plan = todays_reels(root, today)
    if plan:
        lines.append("Today: " + "; ".join(f"{t} {piece_category(p)} ({p.status})" for t, p in plan))
    notify("\n".join(lines))
    if choice:
        piece = make(choice, root, now_utc, slot_ist=slot, notify=notify)
        return 0 if piece.status == "uploaded" else 1
    return 0


def main(argv=None) -> int:
    return run()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
