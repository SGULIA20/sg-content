"""Each Short points to its channel's long video (founder, 23 Oct 2026): a comment from the channel and a line in the description,
so Shorts viewers can move to the long videos. YouTube's own "related video" link and pinning a comment have no API, so the
founder may pin the comment by hand; nothing here depends on it.

Runs inside each publish run for Shorts already public; quota: about 100 units a Short (comment 50, description 50).
"""
from datetime import datetime, timezone
from pathlib import Path

from . import pieces, secrets, slots, youtube
from .config import ROOT

API = "https://www.googleapis.com/youtube/v3"
DONE_KEY = "yt_long_link"
RETRY_DAYS = 3


def long_for(short, root: Path = ROOT):
    """The channel's newest long video that is public by the Short's day (or None)."""
    longs = [p for p in pieces.list_all(root) if p.channel == short.channel and p.kind == "long" and p.ids.get("yt_id")
             and p.status in ("uploaded", "posted") and p.publish_day <= short.publish_day]
    return max(longs, key=lambda p: p.publish_day, default=None)


def link_text(long_piece) -> str:
    title = ((long_piece.script or {}).get("captions", {}).get("youtube", {}).get("title") or long_piece.topic.get("title") or "").strip()
    return f"▶ Poori kahani, lambi video mein: {title}\nhttps://youtu.be/{long_piece.ids['yt_id']}".strip()


def due(root: Path, channel: str, now_utc: datetime) -> list:
    """Public Shorts of this channel from the last few days that do not point to a long video yet."""
    today = slots.ist(now_utc).date()
    out = []
    for p in pieces.list_all(root):
        if p.channel != channel or p.kind != "short" or not p.ids.get("yt_id") or p.ids.get(DONE_KEY) or p.ids.get("unlisted"):
            continue
        if not (0 <= (today - p.publish_day).days <= RETRY_DAYS):
            continue
        if now_utc < slots.publish_at(p.channel, "short", p.publish_day):         # still private and scheduled: comments are refused
            continue
        out.append(p)
    return out


def link(short, long_piece, token: str, call=youtube.call) -> str:
    """Adds the line to the description (keeping title, tags and category) and comments it. Returns the comment id."""
    vid, text = short.ids["yt_id"], link_text(long_piece)
    status, _h, body = call("GET", f"{API}/videos?part=snippet&id={vid}", token)
    items = body.get("items") or []
    if status != 200 or not items:
        raise youtube.YouTubeError(f"video {vid} not readable ({status})")
    snip = items[0]["snippet"]
    if text not in snip.get("description", ""):
        new = {k: snip[k] for k in ("title", "categoryId", "tags", "defaultLanguage", "defaultAudioLanguage") if k in snip}
        new["description"] = (text + "\n\n" + snip.get("description", ""))[:5000]
        status, _h, body = call("PUT", f"{API}/videos?part=snippet", token, json_body={"id": vid, "snippet": new})
        if status != 200:
            raise youtube.YouTubeError(f"description update {status}: {secrets.scrub(str(body))[:200]}")
    status, _h, body = call("POST", f"{API}/commentThreads?part=snippet", token,
                            json_body={"snippet": {"videoId": vid, "topLevelComment": {"snippet": {"textOriginal": text}}}})
    if status != 200:
        raise youtube.YouTubeError(f"comment {status}: {secrets.scrub(str(body))[:200]}")
    return body.get("id", "commented")


def run(root: Path, channel: str, now_utc: datetime | None = None, env=None, call=youtube.call) -> list:
    """Links what is due; returns problems (never raises: this must not stop a publish run)."""
    now_utc = now_utc or datetime.now(timezone.utc)
    problems = []
    todo = due(root, channel, now_utc)
    if not todo:
        return problems
    try:
        token = youtube.access_token(channel, env)
    except Exception as e:
        return [f"long-video links: {str(e)[:120]}"]
    for short in todo:
        target = long_for(short, root)
        if not target:
            continue                                                         # no public long video yet: try again next run
        try:
            short.ids[DONE_KEY] = link(short, target, token, call)
            pieces.save(short, root)
        except Exception as e:
            problems.append(f"{short.id}: long-video link: {str(e)[:160]}")
    return problems
