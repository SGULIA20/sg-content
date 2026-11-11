"""An Instagram Story for each new long video (founder, 30 Oct 2026: "I want to automise this", after adding the YouTube link to the
Instagram bio). Instagram's API cannot add a link sticker, so the card shows the video's thumbnail and title and points to the link in
the bio. The card is drawn by the production job (it has the browser; backfill() covers every made long video) and posted by the
publish job once the long video is public (19:00 India on its day), once per long video (ids["ig_teaser_id"]).

Founder, 11 Nov 2026 ("why old thumbnail ... why not SG myth world ... why without any music"): the card shows HIS thumbnail when he has
sent one (inbox/thumb/) and is drawn again when that file changes; a long made on any weekday gets its Story (the 9 and 10 Nov longs fell
on a Monday and a Tuesday and were skipped); and the Story is an 8-second video of the card with the channel's music bed, because
Instagram's API cannot add a music sticker to a picture.
"""
import hashlib
import subprocess
import time
from datetime import datetime
from pathlib import Path

from . import cards, instagram, pieces, secrets, slots, storyframe
from .config import ROOT

SIZE = (1080, 1920)
VIDEO_S = 8


def _url(piece, repo: str, name: str = "teaser.jpg", head=None, tries: int = 6, sleep=time.sleep) -> str:
    url = f"https://raw.githubusercontent.com/{repo}/main/out/{piece.id}/{name}"
    for _ in range(tries):                                  # raw.githubusercontent.com can lag a push by a few seconds
        if instagram._serves(url, head):
            return url
        sleep(5)
    raise instagram.InstagramError(f"{piece.id}: {name} is not served on main yet")


def due(root: Path, channel: str, now_utc: datetime):
    """Today's long video of this channel, once it is public and before its Story went out; else None."""
    now_ist = slots.ist(now_utc)
    day = now_ist.date()
    p = pieces.load(slots.piece_id(day, channel, "long"), root)
    if p is None or not p.ids.get("yt_id") or p.ids.get("ig_teaser_id") or p.ids.get("unlisted"):
        return None
    if now_utc < slots.publish_at(channel, "long", day):
        return None
    return p


def thumb_for(piece, out_dir: Path) -> Path:
    """The founder's own thumbnail when he has sent one, else the one the pipeline drew."""
    mine = Path(out_dir).parent.parent / "inbox" / "thumb" / f"{piece.id}.jpg"
    return mine if mine.exists() else Path(out_dir) / "thumb.jpg"


def _sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]


def card(piece, out_dir: Path, render=cards.render) -> Path:
    out_dir = Path(out_dir)
    return render("teaser", {**storyframe.brand(piece.channel), "title_html": storyframe.title_html((piece.script or {}).get("title") or piece.topic.get("title", "")),
                             "thumb_path": thumb_for(piece, out_dir), "logo_path": storyframe.logo(piece.channel, 320)}, out_dir / "teaser.jpg", SIZE)


def video(jpg: Path, out: Path, seconds: int = VIDEO_S) -> Path:
    """The card as a short video with the music bed: a slow push-in so it does not look frozen."""
    from . import music
    frames = seconds * 30
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", str(jpg), "-i", str(music.bed("light", seconds + 4)),
                    "-filter_complex", f"[0:v]scale={SIZE[0] * 2}:{SIZE[1] * 2},zoompan=z='min(1+0.04*on/{frames},1.04)':d={frames}:"
                                       f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={SIZE[0]}x{SIZE[1]}:fps=30,format=yuv420p[v];"
                                       f"[1:a]loudnorm=I=-18:TP=-2:LRA=7,afade=t=in:d=0.4,afade=t=out:st={seconds - 0.8}:d=0.8[a]",
                    "-map", "[v]", "-map", "[a]", "-t", str(seconds), "-c:v", "libx264", "-preset", "medium", "-crf", "26",
                    "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-movflags", "+faststart", str(out)], check=True)
    return out


def backfill(root: Path = ROOT, render=cards.render, make_video=video) -> list:
    """Draws the Story card (and its video) for every made long video whose Story has not gone out and that has none yet, or whose
    thumbnail changed since the card was drawn; returns their ids. Costs nothing (no picture calls)."""
    done = []
    for p in pieces.list_all(root):
        out = Path(root) / "out" / p.id
        if not (p.kind == "long" and p.ids.get("yt_id") and not p.ids.get("ig_teaser_id") and (out / "thumb.jpg").exists()):
            continue
        sha = _sha(thumb_for(p, out))
        if (out / "teaser.jpg").exists() and p.ids.get("teaser_thumb") == sha:
            continue
        try:
            jpg = card(p, out, render)
            (out / "teaser.mp4").unlink(missing_ok=True)
            if make_video and Path(jpg).exists() and Path(jpg).stat().st_size > 1000:
                try:
                    make_video(jpg, out / "teaser.mp4")
                except Exception as e:                              # the picture Story still goes out
                    print(f"{p.id}: teaser video failed: {secrets.scrub(str(e))[:160]}", flush=True)
            p.ids["teaser_thumb"] = sha
            pieces.save(p, root)
            done.append(p.id)
        except Exception as e:                                      # a bonus: never stops production
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
        if (Path(root) / "out" / p.id / "teaser.mp4").exists():      # with music
            p.ids["ig_teaser_id"] = post({"media_type": "STORIES", "video_url": url(p, repo, "teaser.mp4")})
        else:
            p.ids["ig_teaser_id"] = post({"media_type": "STORIES", "image_url": url(p, repo)})
    except Exception as e:
        return [f"{p.id}: long-video Story: {secrets.scrub(str(e))[:200]}"]
    pieces.save(p, root)
    return []
