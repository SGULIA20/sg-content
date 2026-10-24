"""Thumbnail click test for long videos (founder, 23 Oct 2026). A long video starts with thumbnail A (thumb.jpg). Two days after it
goes public it switches to B (thumb_b.jpg: the same picture, other words). Once YouTube has the numbers for both two-day windows
(about five days after the switch, it reports late), the one with the higher click rate on its thumbnail stays. Too few impressions,
or no click-rate numbers from YouTube: A stays. Only the thumbnail ever changes. Daily: python -m engine.thumbtest
"""
import sys
import urllib.parse
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import pieces, secrets, slots, telegram, youtube
from .config import CHANNELS, ROOT

ANALYTICS_URL = "https://youtubeanalytics.googleapis.com/v2/reports"
WINDOW = timedelta(days=2)
REPORT_LAG = timedelta(days=3)
MIN_IMPRESSIONS = 200


def ctr(channel: str, video_id: str, start: date, end: date, token: str, call=youtube.call) -> tuple:
    """(impressions, click rate %) for one video over whole days, or (0, None) when YouTube has no such numbers."""
    q = {"ids": "channel==MINE", "startDate": start.isoformat(), "endDate": end.isoformat(), "filters": f"video=={video_id}",
         "metrics": "videoThumbnailImpressions,videoThumbnailImpressionsClickRate"}
    status, _h, body = call("GET", ANALYTICS_URL + "?" + urllib.parse.urlencode(q), token)
    rows = body.get("rows") or []
    if status != 200 or not rows:
        return 0, None
    return int(rows[0][0]), float(rows[0][1])


def step(piece, now: datetime, token: str, root: Path = ROOT, call=youtube.call, set_thumb=youtube.set_thumbnail) -> str:
    """Moves one long video's test on by at most one step; returns what happened ('' when nothing was due)."""
    out = Path(root) / "out" / piece.id
    test = piece.topic.get("thumb_test") or {}
    if test.get("phase") == "done" or (not test and not (out / "thumb_b.jpg").exists()):
        return ""                                                            # finished, or made before 23 Oct with no second thumbnail
    piece.topic["thumb_test"] = test
    public = slots.publish_at(piece.channel, "long", piece.publish_day)
    if not test and now >= public + WINDOW:
        if not set_thumb(token, piece.ids["yt_id"], out / "thumb_b.jpg"):
            return ""
        test.update({"phase": "B", "switched": now.isoformat(timespec="minutes")})
        pieces.save(piece, root)
        return f"{piece.id}: thumbnail B is up"
    if test.get("phase") == "B":
        switched = datetime.fromisoformat(test["switched"])
        if now < switched + WINDOW + REPORT_LAG:
            return ""
        a = ctr(piece.channel, piece.ids["yt_id"], public.date(), (public + WINDOW).date() - timedelta(days=1), token, call)
        b = ctr(piece.channel, piece.ids["yt_id"], switched.date() + timedelta(days=1), (switched + WINDOW).date(), token, call)
        keep_b = a[1] is not None and b[1] is not None and min(a[0], b[0]) >= MIN_IMPRESSIONS and b[1] > a[1]
        if not keep_b:
            a_jpg = out / "thumb.jpg"
            if a_jpg.exists():
                set_thumb(token, piece.ids["yt_id"], a_jpg)
        test.update({"phase": "done", "winner": "B" if keep_b else "A", "a": list(a), "b": list(b)})
        pieces.save(piece, root)
        return f"{piece.id}: thumbnail {'B' if keep_b else 'A'} stays (A {a[1]}% of {a[0]:,}, B {b[1]}% of {b[0]:,})"
    return ""


def run(root: Path = ROOT, now: datetime | None = None, env=None, call=youtube.call, set_thumb=youtube.set_thumbnail) -> list:
    now = now or datetime.now(timezone.utc)
    done = []
    for ch in CHANNELS:
        longs = [p for p in pieces.list_all(root) if p.channel == ch and p.kind == "long" and p.ids.get("yt_id")
                 and p.status in ("uploaded", "posted") and (now.date() - p.publish_day).days <= 14]
        if not longs:
            continue
        token = youtube.access_token(ch, env)
        for p in longs:
            msg = step(p, now, token, root, call, set_thumb)
            if msg:
                done.append(msg)
    return done


def main(argv=None) -> int:
    try:
        done = run()
    except Exception as e:
        print("thumbtest failed:", secrets.scrub(str(e))[:200])
        return 0
    print("\n".join(done) or "nothing due")
    if any("stays" in d for d in done):
        telegram.send("🖼 Thumbnail tests:\n" + "\n".join(d for d in done if "stays" in d))
    return 0


if __name__ == "__main__":
    sys.exit(main())
