"""Post what is due in this slot to Instagram and Threads (YouTube is scheduled at upload time) (spec §3 step 11, §7).

python -m engine.publish --channel sglearning|arthvan
"""
import argparse
import os
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

from . import digest, instagram, pieces, slots, telegram, threads
from .config import ROOT
from .instagram import InstagramError
from .threads import ThreadsError

PLATFORM_IDS = ("ig_reel_id", "ig_story_id", "threads_id")


def due(root: Path, now_utc: datetime, channel: str) -> list:
    """Uploaded Shorts of this channel publishing today (IST) with some platform id still missing, outside the app job's window."""
    now_ist = slots.ist(now_utc)
    if not slots.ig_slot_ok(now_ist.replace(tzinfo=None)):
        return []
    out = []
    for p in pieces.list_all(root):
        if p.channel != channel or p.kind != "short" or p.status != "uploaded" or p.publish_day != now_ist.date():
            continue
        missing = [k for k in PLATFORM_IDS if not p.ids.get(k)]
        if (p.script or {}).get("carousel") and not p.ids.get("ig_post_id"):
            missing.append("ig_post_id")
        if missing:
            out.append(p)
    return out


def threads_text(piece) -> str:
    return threads.text_for((piece.script or {}).get("captions", {}).get("threads", {}))


def run(root: Path = ROOT, channel: str = "sglearning", now_utc: datetime | None = None, env=None,
        ig_publish=instagram.publish_piece, threads_post=threads.post_video, notify=telegram.send) -> int:
    now_utc = now_utc or datetime.now(timezone.utc)
    env = os.environ if env is None else env
    if telegram.paused(root):
        print("paused: nothing posted", flush=True)
        return 0
    posted, problems = [], []
    for piece in due(root, now_utc, channel):
        try:
            piece = ig_publish(piece, env)
        except InstagramError as e:
            problems.append(f"{piece.id}: instagram: {e}")
            pieces.transition(piece, piece.status, f"instagram: {str(e)[:200]}"); pieces.save(piece, root)
            continue
        if not piece.ids.get("threads_id"):
            try:
                from . import secrets
                repo = env.get("GITHUB_REPOSITORY") or instagram.DEFAULT_REPO
                piece.ids["threads_id"] = threads_post(secrets.get("THREADS_USER_ID", env), secrets.get("THREADS_ACCESS_TOKEN", env),
                                                       instagram.media_url(piece, "reel.mp4", repo), threads_text(piece))
                pieces.save(piece, root)
            except (ThreadsError, Exception) as e:
                problems.append(f"{piece.id}: threads: {e}")
                pieces.transition(piece, piece.status, f"threads: {str(e)[:200]}"); pieces.save(piece, root)
                continue
        if all(piece.ids.get(k) for k in PLATFORM_IDS):
            pieces.save(pieces.transition(piece, "posted"), root)
            posted.append(piece.id)
    text = f"SG Content publish {channel} {slots.ist(now_utc).strftime('%Y-%m-%d %H:%M')} IST: posted {len(posted)}"
    for pid in posted:
        text += f"\n  + {pid}"
    for pr in problems:
        text += f"\n  ! {pr}"
    for a in digest.alerts(root, slots.ist(now_utc).date()):
        text += f"\n  ! {a}"
    if posted or problems:
        notify(text)
    print(text, flush=True)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--channel", required=True, choices=["sglearning", "arthvan"])
    a = ap.parse_args(argv)
    telegram.poll_commands(status_fn=lambda: digest.status_line(ROOT))
    try:
        return run(ROOT, a.channel)
    except Exception as e:
        traceback.print_exc()
        telegram.send(f"publish {a.channel} crashed: {type(e).__name__}: {str(e)[:200]}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
