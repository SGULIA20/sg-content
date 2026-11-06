"""Last days of YouTube watch time, split the way the Partner Program counts it (founder, 6 Nov 2026: "check the last 10 days only to
predict"). Per channel: long videos versus Shorts per day, how much of the long-video viewing came from paid ads (which does not
qualify), and the best long videos. Read-only.

python -m engine.ytwatch [days]
"""
import sys
import urllib.parse
from datetime import date, timedelta

from . import youtube
from .config import CHANNELS

URL = "https://youtubeanalytics.googleapis.com/v2/reports"


def query(token: str, params: dict, call=youtube.call) -> list:
    q = {"ids": "channel==MINE", **params}
    status, _h, body = call("GET", URL + "?" + urllib.parse.urlencode(q), token)
    if status != 200:
        return [["error", status, str((body or {}).get("error", ""))[:120]]]
    return body.get("rows") or []


def summarize(token: str, start: date, end: date, call=youtube.call) -> dict:
    span = {"startDate": start.isoformat(), "endDate": end.isoformat()}
    per_day = query(token, {**span, "dimensions": "day,creatorContentType", "metrics": "views,estimatedMinutesWatched,subscribersGained", "sort": "day"}, call)
    kinds = {r[1] for r in per_day if r[0] != "error"}
    long_kind = next((k for k in kinds if "demand" in str(k).lower()), None)          # the API's own spelling of "long video"
    if not long_kind:
        return {"per_day": per_day, "sources": [], "top": []}
    sources = query(token, {**span, "dimensions": "insightTrafficSourceType", "metrics": "views,estimatedMinutesWatched",
                            "filters": f"creatorContentType=={long_kind}", "sort": "-views"}, call)
    top = query(token, {**span, "dimensions": "video", "metrics": "views,estimatedMinutesWatched,averageViewDuration",
                        "filters": f"creatorContentType=={long_kind}", "sort": "-views", "maxResults": 8}, call)
    return {"per_day": per_day, "sources": sources, "top": top}


def hours(minutes) -> float:
    return round(float(minutes) / 60, 1)


def report(name: str, s: dict) -> list:
    out = [f"=== {name}"]
    long_h = short_h = long_v = short_v = 0.0
    for row in s["per_day"]:
        if row[0] == "error":
            return out + [f"error: {row}"]
        day, kind, views, minutes, subs = row
        out.append(f"{day} {kind:<18} views {int(views):>5}  hours {hours(minutes):>6}  subs {int(subs)}")
        if str(kind).lower() == "shorts":
            short_h += hours(minutes); short_v += views
        else:
            long_h += hours(minutes); long_v += views
    out.append(f"TOTAL long-form: {int(long_v)} views, {round(long_h, 1)} h | Shorts: {int(short_v)} views, {round(short_h, 1)} h")
    if s["sources"] and s["sources"][0][0] == "error":
        out.append(f"traffic sources: {s['sources'][0]}")
    else:
        out.append("long-form by traffic source (views, hours): " + "; ".join(f"{r[0]} {int(r[1])}/{hours(r[2])}" for r in s["sources"]))
    if s["top"] and s["top"][0][0] == "error":
        out.append(f"top videos: {s['top'][0]}")
    else:
        out.append("top long videos (id, views, hours, avg seconds): " + "; ".join(f"{r[0]} {int(r[1])}/{hours(r[2])}/{int(r[3])}" for r in s["top"]))
    return out


def main(argv=None) -> int:
    days = int((argv if argv is not None else sys.argv[1:] or ["10"])[0])
    end = date.today() - timedelta(days=1)
    for ch in CHANNELS:
        print("\n".join(report(ch, summarize(youtube.access_token(ch), end - timedelta(days=days - 1), end))), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
