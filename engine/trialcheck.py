"""Trial Reels whose 72 hours ended today, for the 9 pm card (founder, 24 Oct 2026).

A Trial Reel is shown to non-followers first; Instagram shares it with followers on its own when it does well in its first 72 hours
(graduation SS_PERFORMANCE). Meta's API neither reports nor makes that graduation, so once the 72 hours are over the card lists each
one with its numbers and link: the founder opens it and taps "Share to followers" if Instagram did not. Reads only; changes nothing."""
from datetime import date, datetime, timedelta, timezone

from . import instagram, pieces, secrets, whatworks
from .config import CHANNELS, ROOT

APP_NAMES = {"scoremybiz": "ScoreMyBiz", "waypoint": "Waypoint"}
WINDOW = (timedelta(hours=72), timedelta(hours=96))      # the card runs once a day, so each Reel is listed once


def _when(ts: str) -> datetime:
    return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S%z")


def lines(now: datetime | None = None, root=ROOT, env=None, call=instagram.call, numbers=whatworks.instagram_numbers, app_log=None) -> list:
    """app_log: the app poster's logs/posts.jsonl rows; its Trial Reels (ScoreMyBiz, Waypoint) are listed the same way."""
    now = now or datetime.now(timezone.utc)
    try:
        token = secrets.get("IG_ACCESS_TOKEN", env)
    except secrets.MissingSecret:
        return []
    recent = now.date() - timedelta(days=6)
    reels = [(f"{CHANNELS[p.channel].display_name} {p.publish_day.strftime('%d %b')}", p.ids["ig_reel_id"])
             for p in sorted(pieces.list_all(root), key=lambda p: p.id)
             if p.ids.get("ig_trial") == instagram.TRIAL_GRADUATION and p.ids.get("ig_reel_id") and p.publish_day >= recent]
    for e in app_log or []:
        if e.get("status") == "published" and e.get("reel_trial") and (e.get("ids") or {}).get("reel") and str(e.get("date", "")) >= recent.isoformat():
            reels.append((f"{APP_NAMES.get(e.get('app'), e.get('app'))} {date.fromisoformat(e['date']).strftime('%d %b')}", e["ids"]["reel"]))
    out = []
    for label, reel in reels:
        try:
            m = call("GET", f"/{reel}", token, {"fields": "timestamp,permalink,like_count,comments_count"})
            age = now - _when(m["timestamp"])
            if not (WINDOW[0] <= age < WINDOW[1]):
                continue
            n = numbers(reel, token)
        except Exception as e:
            out.append(f"   {label}: numbers not read ({secrets.scrub(str(e))[:80]})")
            continue
        views = int(n.get("views") or n.get("reach") or 0)
        out.append(f"   {label}: {views:,} views, {int(m.get('like_count') or 0)} likes, "
                   f"{int(m.get('comments_count') or 0)} comments, {int(n.get('shares') or 0)} shares, {int(n.get('saved') or 0)} saves\n"
                   f"      {m.get('permalink', '')}")
    if not out:
        return []
    return ["🧪 Trial Reels, 72 hours over: if one is not on your profile, Instagram did not share it with followers.",
            "   Open it and tap \"Share to followers\" if you want them to see it."] + out
