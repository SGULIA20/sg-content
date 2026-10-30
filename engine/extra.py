"""Extra Learning with SG Reels beyond the daily one (founder, 29 Oct 2026: 3-4 a day, "from today onwards").

An extra Reel is a Short with its own id (YYYY-MM-DD-sglearning-x1, -x2 ...) and its own Instagram/YouTube time (topic["slot_ist"]);
publish.due() opens it at that time and the upload schedules YouTube for it. It is made like the news Short: a topic chosen up front,
the synchronous writer, no batch waits.

python -m engine.extra --title "..." --link URL [--summary "..."] [--slot HH:MM]     a chosen story (blank slot = as soon as it is made)
"""
import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import news, pieces, pipeline, slots, telegram
from .config import ROOT

CHANNEL = "sglearning"
EXTRA_SLOTS_IST = ("13:00", "16:30", "22:45")     # around the 18:30 main Reel, clear of the app Reel's 19:07-21:07 window and myth at 21:30
LEAD_MINUTES = 15                                  # "now": the first slot a run can still meet


def next_id(root: Path, day) -> str:
    n = 1
    while pieces.load(f"{day.isoformat()}-{CHANNEL}-x{n}", root) is not None:
        n += 1
    return f"{day.isoformat()}-{CHANNEL}-x{n}"


def now_slot(now_utc: datetime) -> str:
    t = slots.ist(now_utc) + timedelta(minutes=LEAD_MINUTES)
    return t.strftime("%H:%M")


def make(topic: dict, root: Path = ROOT, now_utc: datetime | None = None, slot_ist: str | None = None, deps=None, notify=telegram.send):
    """Makes and uploads one extra Reel for today; returns the piece (status "uploaded" when it worked)."""
    now_utc = now_utc or datetime.now(timezone.utc)
    root = Path(root)
    today = slots.ist(now_utc).date()
    slot = slot_ist or now_slot(now_utc)
    piece = pieces.Piece(id=next_id(root, today), channel=CHANNEL, kind="short", publish_day=today)
    from . import trends
    topic = {**topic, "category": topic.get("category") or trends.category(topic)}
    piece.topic = {"preset": {**topic, "slot_ist": slot, "extra": True, "graphics": True}}   # news cards, no paid pictures (30 Oct 2026)
    deps = deps or news.news_deps(root)
    deps.topic = lambda p, used: None                       # one story per extra Reel: if its drafts fail, nothing else slips in
    piece = pipeline.make(piece, deps, root)
    if piece.status == "uploaded":
        notify(f"➕ Extra Learning with SG Reel ready: {str(topic.get('title', ''))[:90]}. Posts at {slot} India "
               f"({_wat(today, slot)} WAT) on Instagram and YouTube.")
    else:
        notify(f"Extra Reel not made ({piece.status}: {(piece.reasons or [''])[-1][:140]}).")
    return piece


def _wat(day, slot_ist: str) -> str:
    return (slots.utc_for(day, slot_ist) + timedelta(hours=1)).strftime("%H:%M")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--title", required=True)
    ap.add_argument("--link", required=True)
    ap.add_argument("--summary", default="")
    ap.add_argument("--slot", default="")
    a = ap.parse_args(argv)
    if telegram.paused(ROOT):
        print("paused: no extra Reel", flush=True)
        return 0
    topic = {"title": a.title, "link": a.link, "summary": a.summary or a.title, "source": "chosen", "published": datetime.now(timezone.utc).isoformat()}
    piece = make(topic, ROOT, slot_ist=a.slot or None)
    print(f"{piece.id}: {piece.status}", flush=True)
    return 0 if piece.status == "uploaded" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
