"""An Instagram Story for each new long video (founder, 30 Oct 2026: "I want to automise this", after adding the YouTube link to the
Instagram bio). Instagram's API cannot add a link sticker, so the card shows the video's thumbnail and title and points to the link in
the bio. The card is drawn by the production job (it has the browser; backfill() covers every made long video) and posted by the
publish job once the long video is public (19:00 India on its day), once per long video (ids["ig_teaser_id"]).
"""
import time
from datetime import datetime
from pathlib import Path

from . import cards, instagram, pieces, secrets, slots, storyframe
from .config import CHANNELS, ROOT

SIZE = (1080, 1920)


def _url(piece, repo: str, head=None, tries: int = 6, sleep=time.sleep) -> str:
    url = f"https://raw.githubusercontent.com/{repo}/main/out/{piece.id}/teaser.jpg"
    for _ in range(tries):                                  # raw.githubusercontent.com can lag a push by a few seconds
        if instagram._serves(url, head):
            return url
        sleep(5)
    raise instagram.InstagramError(f"{piece.id}: teaser.jpg is not served on main yet")


def due(root: Path, channel: str, now_utc: datetime):
    """Today's long video of this channel, once it is public and before its Story went out; else None."""
    now_ist = slots.ist(now_utc)
    day = now_ist.date()
    if day.weekday() not in CHANNELS[channel].long_days:
        return None
    p = pieces.load(slots.piece_id(day, channel, "long"), root)
    if p is None or not p.ids.get("yt_id") or p.ids.get("ig_teaser_id") or p.ids.get("unlisted"):
        return None
    if now_utc < slots.publish_at(channel, "long", day):
        return None
    return p


def card(piece, out_dir: Path, render=cards.render) -> Path:
    out_dir = Path(out_dir)
    return render("teaser", {**storyframe.brand(piece.channel), "title_html": storyframe.title_html((piece.script or {}).get("title") or piece.topic.get("title", "")),
                             "thumb_path": out_dir / "thumb.jpg", "logo_path": storyframe.logo(piece.channel, 320)}, out_dir / "teaser.jpg", SIZE)


def backfill(root: Path = ROOT, render=cards.render) -> list:
    """Draws the Story card for every made long video that has none yet; returns their ids. Costs nothing (no picture calls)."""
    done = []
    for p in pieces.list_all(root):
        out = Path(root) / "out" / p.id
        if p.kind == "long" and p.ids.get("yt_id") and not p.ids.get("ig_teaser_id") and (out / "thumb.jpg").exists() \
                and not (out / "teaser.jpg").exists():
            try:
                card(p, out, render)
                done.append(p.id)
            except Exception as e:                                  # a bonus: never stops production
                print(f"{p.id}: teaser card failed: {e}", flush=True)
    return done


def run(root: Path = ROOT, channel: str = "sglearning", now_utc: datetime | None = None, env=None, publish=None, url=_url) -> list:
    """Posts the Story when one is due; returns problems for the publish report (empty when nothing was due or it worked)."""
    from datetime import timezone
    now_utc = now_utc or datetime.now(timezone.utc)
    p = due(root, channel, now_utc)
    if p is None:
        return []
    if not (Path(root) / "out" / p.id / "teaser.jpg").exists():
        return [f"{p.id}: no long-video Story card yet (the next production run draws it)"]
    try:
        repo = (env or {}).get("GITHUB_REPOSITORY") or instagram.DEFAULT_REPO
        post = publish or (lambda params: instagram._create_and_publish(secrets.get("IG_USER_ID", env), secrets.get("IG_ACCESS_TOKEN", env),
                                                                        params, "teaser story", instagram.call, time.sleep))
        p.ids["ig_teaser_id"] = post({"media_type": "STORIES", "image_url": url(p, repo)})
    except Exception as e:
        return [f"{p.id}: long-video Story: {secrets.scrub(str(e))[:200]}"]
    pieces.save(p, root)
    return []
