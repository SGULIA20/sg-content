"""Learning with SG's same-day news Short (founder, 30 Oct 2026: "we are not covering latest financial news").

The buffer makes Shorts a week ahead, so a news Short posted days after its news reached almost nobody ("today, 22 Oct" on 25-27 Oct:
3-15 views). Each morning this picks that morning's biggest household money news, makes the Short with no batch waiting, and only once
the video is ready swaps it into today's slot: the evergreen Short that was due today moves to the first free day after the buffer
(its YouTube schedule moves with it), so nothing made is ever lost. Anything that fails before NEWS_DEADLINE leaves today exactly as it
was: the evergreen Short posts. Instagram posts at 18:30 India time, YouTube at 20:00.

python -m engine.news            run once (the news workflow, 08:47 and 09:47 WAT)
"""
import shutil
import sys
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

from . import gitsync, pieces, pipeline, slots, telegram, topics, writer, youtube
from .config import ROOT

CHANNEL = "sglearning"
NEWS_DEADLINE_UTC = time(12, 0)          # 13:00 WAT; Instagram posts at 13:00 UTC (18:30 India), YouTube at 14:30 UTC (20:00 India)
NEWS_HOURS = 18                          # this morning's news: published since yesterday afternoon
PLATFORM_IDS = ("ig_reel_id", "ig_story_id", "threads_id")


def _out(root: Path, pid: str) -> Path:
    return Path(root) / "out" / pid


def free_day(root: Path, start) -> object:
    """The first day from `start` with no Learning with SG Short at all (made, in progress or parked)."""
    day = start
    while pieces.load(slots.piece_id(day, CHANNEL, "short"), root) is not None:
        day += timedelta(days=1)
    return day


def rename(piece, new_id: str, new_day, root: Path):
    """The same piece under another day: its record and out/ folder move; out_sha is dropped so the next commit records the new path."""
    old_id = piece.id
    if _out(root, old_id).exists():
        shutil.move(str(_out(root, old_id)), str(_out(root, new_id)))
    piece.id, piece.publish_day = new_id, new_day
    piece.ids.pop("out_sha", None)
    pieces.save(piece, root)
    old = Path(root) / "pieces" / f"{old_id}.json"
    if old.exists() and old_id != new_id:
        old.unlink()
    return piece


def news_deps(root: Path):
    """The production wiring, minus the batch lanes: a news Short cannot wait for a batch job."""
    deps = pipeline.real_deps(root)
    deps.write = lambda piece, sheet, lib, tags: writer.write(piece, sheet, lib, tags)      # the synchronous writer, about $0.40 a draft
    deps.voice_batch = None
    deps.art_batch = None
    return deps


def run(root: Path = ROOT, now_utc: datetime | None = None, deps=None, notify=telegram.send, items=None, env=None,
        token_for=youtube.access_token, reschedule=youtube.reschedule) -> int:
    now_utc = now_utc or datetime.now(timezone.utc)
    root = Path(root)
    if telegram.paused(root):
        print("paused: no news Short", flush=True)
        return 0
    today = slots.ist(now_utc).date()
    sid = slots.piece_id(today, CHANNEL, "short")
    evergreen = pieces.load(sid, root)
    if evergreen is not None and evergreen.topic.get("keep_slot"):          # a planned test needs this Short on this day (30 Oct gold style test)
        print(f"{sid} keeps its slot: {evergreen.topic['keep_slot']}", flush=True)
        return 0
    if evergreen is not None and evergreen.topic.get("news"):
        print(f"{sid} is already today's news Short", flush=True)
        return 0
    if evergreen is None or evergreen.status != "uploaded" or not evergreen.ids.get("yt_id") or any(evergreen.ids.get(k) for k in PLATFORM_IDS):
        print(f"{sid}: no scheduled evergreen Short to swap ({evergreen.status if evergreen else 'missing'}); nothing done", flush=True)
        return 0
    if now_utc.time() >= NEWS_DEADLINE_UTC:
        print("past the news deadline: today's evergreen Short posts as planned", flush=True)
        return 0
    used, _prior = pipeline._used(root)
    topic = topics.pick_finance(items if items is not None else topics.fetch_all(), used, now_utc, news=True, hours=NEWS_HOURS)
    if not topic:
        print("no fresh household money news this morning: the evergreen Short posts", flush=True)
        return 0
    nid = f"{today.isoformat()}-{CHANNEL}-news"
    news = pieces.load(nid, root) or pieces.Piece(id=nid, channel=CHANNEL, kind="short", publish_day=today)
    deps = deps or news_deps(root)
    topic = {**topic, "news": True}                                                       # the writer builds a news explainer (50-60 s)
    deps.topic = lambda piece, used_links: topic if not piece.topic else None              # this morning's story, one try
    news = pipeline.make(news, deps, root, dry_run=True)
    video, thumb = _out(root, nid) / "reel.mp4", _out(root, nid) / "thumb.jpg"
    if news.status != "assembled" or not video.exists():
        notify(f"News Short not made today ({news.status}: {(news.reasons or [''])[-1][:120]}); the planned Short posts at 18:30 India.")
        return 0
    # swap: move the evergreen Short to the first free day, then upload the news Short into today's slot
    later = free_day(root, today + timedelta(days=7))
    token = token_for(CHANNEL, env)
    if not reschedule(token, evergreen.ids["yt_id"], slots.publish_at(CHANNEL, "short", later)):
        notify("News Short made but the planned Short could not be moved on YouTube; the planned Short posts today.")
        return 0
    rename(evergreen, slots.piece_id(later, CHANNEL, "short"), later, root)
    try:
        news.ids["yt_id"] = deps.upload(news, video, thumb)
    except Exception as e:                                                   # put the planned Short back in today's slot
        reschedule(token, evergreen.ids["yt_id"], slots.publish_at(CHANNEL, "short", today))
        rename(evergreen, sid, today, root)
        notify(f"News Short upload failed ({str(e)[:100]}); the planned Short posts today.")
        return 1
    news.topic["news"] = True
    rename(pieces.transition(news, "uploaded"), sid, today, root)
    gitsync.safe_commit(root, f"news: {sid} is today's news Short; the planned one moved to {later}")
    notify(f"📰 Today's Learning with SG Short is fresh news: {str(topic.get('title', ''))[:90]}. Instagram 18:30, YouTube 20:00 India. "
           f"The planned Short moved to {later:%d %b}.")
    return 0


def main(argv=None) -> int:
    return run()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
