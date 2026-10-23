"""Post what is due in this slot to Instagram, Threads and (when configured) LinkedIn (YouTube is scheduled at upload time) (spec §3 step 11, §7).

python -m engine.publish --channel sglearning|arthvan
"""
import argparse
import os
import sys
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import config, digest, gitsync, instagram, linkedin, pieces, slots, telegram, threads
from .config import ROOT
from .instagram import InstagramError
from .threads import ThreadsError

PLATFORM_IDS = ("ig_reel_id", "ig_story_id", "threads_id")
RETRY_DAYS = 3


def required(env=None) -> tuple:
    """Platform ids a Short needs before it is `posted`; LinkedIn only once its secrets exist."""
    return PLATFORM_IDS + (("linkedin_id",) if (config.LINKEDIN_VIDEOS and linkedin.configured(env)) else ())


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
        if p.publish_day == today and now_ist.replace(tzinfo=None) < _slot_opens(p.channel, today):
            continue                                                                # 22 Oct 2026: a run that GitHub delayed past India's midnight
                                                                                    # posted the next day's Short about 20 hours early
        if p.ids.get("unlisted"):                                                  # first-day unlisted uploads stay off Instagram and Threads
            continue
        missing = [k for k in required(env) if not p.ids.get(k)]
        if (p.script or {}).get("carousel") and not p.ids.get("ig_post_id"):
            missing.append("ig_post_id")
        if missing:
            out.append(p)
    return out


EARLY_MINUTES = 60                 # a run may post today's Short up to an hour before its slot, never earlier


def _slot_opens(channel: str, day) -> datetime:
    """When today's Short of this channel may first go out (IST, naive): its Instagram slot minus EARLY_MINUTES."""
    h, m = (int(x) for x in config.CHANNELS[channel].ig_slot_ist.split(":"))
    return datetime(day.year, day.month, day.day, h, m) - timedelta(minutes=EARLY_MINUTES)


def threads_text(piece) -> str:
    return threads.text_for((piece.script or {}).get("captions", {}).get("threads", {}), config.YOUTUBE_URLS.get(piece.channel, ""))


def run(root: Path = ROOT, channel: str = "sglearning", now_utc: datetime | None = None, env=None,
        ig_publish=instagram.publish_piece, threads_post=threads.post_video, linkedin_post=linkedin.post_video, notify=telegram.send, check_media: bool = False,
        threads_poll=None, long_links=None) -> int:
    now_utc = now_utc or datetime.now(timezone.utc)
    env = os.environ if env is None else env
    if telegram.paused(root):
        print("paused: nothing posted", flush=True)
        return 0
    posted, problems = [], []
    need = required(env)
    for piece in due(root, now_utc, channel, env):
        try:
            piece = ig_publish(piece, env, check_media=True) if check_media else ig_publish(piece, env)
        except InstagramError as e:                     # Threads still goes out; the next run retries what Instagram missed
            problems.append(f"{piece.id}: instagram: {e}")
            pieces.transition(piece, piece.status, f"instagram: {str(e)[:200]}"); pieces.save(piece, root)
            gitsync.safe_commit(root, f"publish: {piece.id} partial")
        if not piece.ids.get("threads_id"):
            try:
                from . import secrets
                repo = env.get("GITHUB_REPOSITORY") or instagram.DEFAULT_REPO
                piece.ids["threads_id"] = threads_post(secrets.get("THREADS_USER_ID", env), secrets.get("THREADS_ACCESS_TOKEN", env),
                                                       (instagram.resolved_media_url if check_media else instagram.media_url)(piece, "reel.mp4", repo), threads_text(piece),
                                                       topic_tag=threads.TOPIC_TAGS.get(piece.channel, ""))
                pieces.save(piece, root)
            except (ThreadsError, Exception) as e:
                problems.append(f"{piece.id}: threads: {e}")
                pieces.transition(piece, piece.status, f"threads: {str(e)[:200]}"); pieces.save(piece, root)
                continue
        if threads_poll and piece.ids.get("threads_id") and not piece.ids.get("threads_poll_id"):
            try:                                                            # a bonus: never holds a piece back from "posted"
                from . import secrets
                piece.ids["threads_poll_id"] = threads_poll(secrets.get("THREADS_USER_ID", env), secrets.get("THREADS_ACCESS_TOKEN", env), piece.ids["threads_id"])
            except Exception as e:
                piece.ids["threads_poll_id"] = f"skipped: {str(e)[:120]}"            # tried once; not retried every run
            pieces.save(piece, root)
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
    if long_links is not None:
        problems += long_links(root, channel, now_utc, env)                  # each public Short points to the long video (founder, 23 Oct 2026)
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
        from . import ytlink
        return run(ROOT, a.channel, check_media=True, threads_poll=threads.post_poll, long_links=ytlink.run)   # production: every media URL is verified on GitHub first
    except Exception as e:
        traceback.print_exc()
        telegram.send(f"publish {a.channel} crashed: {type(e).__name__}: {str(e)[:200]}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
