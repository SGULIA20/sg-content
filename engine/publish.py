"""Post what is due in this slot to Instagram, Threads and (when configured) LinkedIn (YouTube is scheduled at upload time) (spec §3 step 11, §7).

python -m engine.publish --channel sglearning|arthvan
"""
import argparse
import os
import sys
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import digest, gitsync, instagram, linkedin, pieces, slots, telegram, threads
from .config import ROOT
from .instagram import InstagramError
from .threads import ThreadsError

PLATFORM_IDS = ("ig_reel_id", "ig_story_id", "threads_id")
RETRY_DAYS = 3


def required(env=None) -> tuple:
    """Platform ids a Short needs before it is `posted`; LinkedIn only once its secrets exist."""
    return PLATFORM_IDS + (("linkedin_id",) if linkedin.configured(env) else ())


def due(root: Path, now_utc: datetime, channel: str, env=None) -> list:
    """Uploaded Shorts of this channel publishing today (IST) with some platform id still missing, outside the app job's window."""
    now_ist = slots.ist(now_utc)
    if not slots.ig_slot_ok(now_ist.replace(tzinfo=None)):
        return []
    out = []
    today = now_ist.date()
    for p in pieces.list_all(root):
        if p.channel != channel or p.kind != "short" or p.status not in ("uploaded", "posted"):
            continue
        if p.status == "posted" and not all(p.ids.get(k) for k in PLATFORM_IDS):             # "posted" counts only when it earned it; then a
            continue                                                                        # platform configured later (LinkedIn, 22 Oct) is still owed
        if not (today - timedelta(days=RETRY_DAYS) <= p.publish_day <= today):      # today's slot, or a recent day whose post failed
            continue
        if p.ids.get("unlisted"):                                                  # first-day unlisted uploads stay off Instagram and Threads
            continue
        missing = [k for k in required(env) if not p.ids.get(k)]
        if (p.script or {}).get("carousel") and not p.ids.get("ig_post_id"):
            missing.append("ig_post_id")
        if missing:
            out.append(p)
    return out


def threads_text(piece) -> str:
    return threads.text_for((piece.script or {}).get("captions", {}).get("threads", {}))


def run(root: Path = ROOT, channel: str = "sglearning", now_utc: datetime | None = None, env=None,
        ig_publish=instagram.publish_piece, threads_post=threads.post_video, linkedin_post=linkedin.post_video, notify=telegram.send) -> int:
    now_utc = now_utc or datetime.now(timezone.utc)
    env = os.environ if env is None else env
    if telegram.paused(root):
        print("paused: nothing posted", flush=True)
        return 0
    posted, problems = [], []
    need = required(env)
    for piece in due(root, now_utc, channel, env):
        try:
            piece = ig_publish(piece, env)
        except InstagramError as e:                     # Threads still goes out; the next run retries what Instagram missed
            problems.append(f"{piece.id}: instagram: {e}")
            pieces.transition(piece, piece.status, f"instagram: {str(e)[:200]}"); pieces.save(piece, root)
            gitsync.safe_commit(root, f"publish: {piece.id} partial")
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
        if "linkedin_id" in need and not piece.ids.get("linkedin_id"):
            try:
                from . import secrets
                piece.ids["linkedin_id"] = linkedin_post(secrets.get("LINKEDIN_PERSON_URN", env), secrets.get("LINKEDIN_ACCESS_TOKEN", env),
                                                         Path(root) / "out" / piece.id / "reel.mp4", linkedin.text_for(piece), linkedin.title_for(piece))
                pieces.save(piece, root)
            except Exception as e:                                                  # recorded like Threads; the next run retries LinkedIn only
                problems.append(f"{piece.id}: linkedin: {e}")
                pieces.transition(piece, piece.status, f"linkedin: {str(e)[:200]}"); pieces.save(piece, root)
                gitsync.safe_commit(root, f"publish: {piece.id} partial")
                continue
        if all(piece.ids.get(k) for k in need):
            pieces.save(pieces.transition(piece, "posted"), root)
            posted.append(piece.id)
        gitsync.safe_commit(root, f"publish: {piece.id} {piece.status}")
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
