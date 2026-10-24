"""Trial Reels whose 72 hours ended today, for the 9 pm card (founder, 24 Oct 2026).

A Trial Reel is shown to non-followers first; Instagram shares it with followers on its own when it does well in its first 72 hours
(graduation SS_PERFORMANCE). Meta's API neither reports nor makes that graduation, so once the 72 hours are over the card lists each
one with its numbers and link: the founder opens it and taps "Share to followers" if Instagram did not. Reads only; changes nothing."""
from datetime import datetime, timedelta, timezone

from . import instagram, pieces, secrets, whatworks
from .config import CHANNELS, ROOT

WINDOW = (timedelta(hours=72), timedelta(hours=96))      # the card runs once a day, so each Reel is listed once


def _when(ts: str) -> datetime:
    return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S%z")


def lines(now: datetime | None = None, root=ROOT, env=None, call=instagram.call, numbers=whatworks.instagram_numbers) -> list:
    now = now or datetime.now(timezone.utc)
    try:
        token = secrets.get("IG_ACCESS_TOKEN", env)
    except secrets.MissingSecret:
        return []
    out = []
    recent = now.date() - timedelta(days=6)
    for p in sorted(pieces.list_all(root), key=lambda p: p.id):
        if p.ids.get("ig_trial") != instagram.TRIAL_GRADUATION or not p.ids.get("ig_reel_id") or p.publish_day < recent:
            continue
        try:
            m = call("GET", f"/{p.ids['ig_reel_id']}", token, {"fields": "timestamp,permalink,like_count,comments_count"})
            age = now - _when(m["timestamp"])
            if not (WINDOW[0] <= age < WINDOW[1]):
                continue
            n = numbers(p.ids["ig_reel_id"], token)
        except Exception as e:
            out.append(f"   {p.id}: numbers not read ({secrets.scrub(str(e))[:80]})")
            continue
        views = int(n.get("views") or n.get("reach") or 0)
        out.append(f"   {CHANNELS[p.channel].display_name} {p.publish_day.strftime('%d %b')}: {views:,} views, {int(m.get('like_count') or 0)} likes, "
                   f"{int(m.get('comments_count') or 0)} comments, {int(n.get('shares') or 0)} shares, {int(n.get('saved') or 0)} saves\n"
                   f"      {m.get('permalink', '')}")
    if not out:
        return []
    return ["🧪 Trial Reels, 72 hours over: if one is not on your profile, Instagram did not share it with followers.",
            "   Open it and tap \"Share to followers\" if you want them to see it."] + out
