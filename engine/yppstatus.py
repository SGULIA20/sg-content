"""Where each channel stands against the YouTube Partner Program bar (founder, 1 Nov 2026: "pull exact numbers"). Read-only.

Today's bar: 1,000 subscribers and 4,000 public watch hours on long videos in 12 months, or 10 million Shorts views in 90 days. From
1 Feb 2027 new applicants need 8,000 hours or 20 million Shorts views. Watch time from ads does not count, so ad traffic is taken out.

python -m engine.yppstatus
"""
import sys
import urllib.parse
from datetime import date, datetime, timedelta, timezone

from . import secrets, telegram, youtube
from .config import CHANNELS

DATA = "https://www.googleapis.com/youtube/v3"
ANALYTICS = "https://youtubeanalytics.googleapis.com/v2/reports"
BAR = {"subs": 1000, "hours": 4000, "shorts": 10_000_000}
BAR_2027 = {"hours": 8000, "shorts": 20_000_000}
NEW_BAR_FROM = date(2027, 2, 1)


def _get(url: str, token: str, call):
    status, _h, body = call("GET", url, token)
    if status != 200:
        raise RuntimeError(f"YouTube {status}: {secrets.scrub(str(body))[:200]}")
    return body


def _report(token: str, call, start: date, end: date, metrics: str, dimensions: str = "", filters: str = "") -> list:
    q = {"ids": "channel==MINE", "startDate": start.isoformat(), "endDate": end.isoformat(), "metrics": metrics}
    if dimensions:
        q["dimensions"] = dimensions
    if filters:
        q["filters"] = filters
    return _get(ANALYTICS + "?" + urllib.parse.urlencode(q), token, call).get("rows") or []


def status(token: str, today: date, call=youtube.call) -> dict:
    ch = _get(f"{DATA}/channels?part=statistics,snippet&mine=true", token, call)["items"][0]
    stats = ch.get("statistics", {})
    year, q90, week = today - timedelta(days=365), today - timedelta(days=90), today - timedelta(days=7)
    long_min = sum(r[1] for r in _report(token, call, year, today, "estimatedMinutesWatched", "creatorContentType")
                   if r[0] == "VIDEO_ON_DEMAND")
    try:                                                       # not every dimension pair is allowed; fall back to traffic source alone
        ad_min = sum(r[2] for r in _report(token, call, year, today, "estimatedMinutesWatched", "creatorContentType,insightTrafficSourceType")
                     if r[0] == "VIDEO_ON_DEMAND" and r[1] == "ADVERTISING")
    except RuntimeError:
        ad_min = sum(r[1] for r in _report(token, call, year, today, "estimatedMinutesWatched", "insightTrafficSourceType")
                     if r[0] == "ADVERTISING")
    shorts = sum(r[1] for r in _report(token, call, q90, today, "views", "creatorContentType") if r[0] == "SHORTS")
    wk_long = sum(r[1] for r in _report(token, call, week, today, "estimatedMinutesWatched", "creatorContentType") if r[0] == "VIDEO_ON_DEMAND")
    wk_subs = sum(r[0] for r in _report(token, call, week, today, "subscribersGained"))
    return {"name": ch["snippet"]["title"], "subs": int(stats.get("subscriberCount", 0)), "hidden": stats.get("hiddenSubscriberCount", False),
            "hours": round((long_min - ad_min) / 60, 1), "ad_hours": round(ad_min / 60, 1), "shorts_90d": int(shorts),
            "week_hours": round(wk_long / 60, 1), "week_subs": int(wk_subs)}


def line(s: dict, today: date) -> str:
    weeks_left = max((NEW_BAR_FROM - today).days / 7, 1)
    need = max(BAR["hours"] - s["hours"], 0)
    return (f"{s['name']}: {s['subs']:,} subscribers ({s['subs'] / BAR['subs']:.0%} of 1,000; +{s['week_subs']} last 7 days) · "
            f"{s['hours']:,} public long-video watch hours in 12 months ({s['hours'] / BAR['hours']:.1%} of 4,000; ad watch time left out: "
            f"{s['ad_hours']} h) · {s['week_hours']} h last 7 days · {s['shorts_90d']:,} Shorts views in 90 days "
            f"({s['shorts_90d'] / BAR['shorts']:.2%} of 10 million). To apply on today's bar before 1 Feb 2027: about "
            f"{need / weeks_left:,.0f} hours a week from now.")


def run(env=None, notify=telegram.send, call=youtube.call, token_for=youtube.access_token, now=None) -> int:
    today = (now or datetime.now(timezone.utc)).date()
    lines = []
    for channel in ("sglearning", "arthvan"):
        try:
            lines.append(line(status(token_for(channel, env), today, call), today))
        except Exception as e:                                  # one channel's error never hides the other's numbers
            lines.append(f"{CHANNELS[channel].display_name}: could not read ({secrets.scrub(str(e))[:160]})")
    text = "📊 YouTube Partner Program status:\n" + "\n".join(lines)
    print(text, flush=True)
    notify(text)
    return 0


if __name__ == "__main__":
    sys.exit(run())
