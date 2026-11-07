"""What is working on YouTube right now, from YouTube itself and not from our own Reels (founder, 7 Nov 2026: "don't research my reels,
research YouTube"). For each topic query: the most-viewed videos in India from the last 14 days, with views, length and channel, so
topic choices rest on what viewers are actually watching. Read-only. Costs 100 quota units a search.

python -m engine.ytresearch
"""
import json
import sys
import urllib.parse
from datetime import datetime, timedelta, timezone

from . import youtube

API = "https://www.googleapis.com/youtube/v3"
QUERIES = {
    "sglearning": ["paisa kaise bachaye", "share market kyun gira", "RBI EMI kam", "petrol diesel daam", "gold silver price kyun", "tax bachane ke tarike",
                   "bank FD interest", "mehngai kyun badh rahi", "UPI fraud", "SIP mutual fund"],
    "arthvan": ["mandir ka rahasya", "mahabharat ka sach", "ramayan ka sach", "shiv mandir rahasya", "bharat ka itihas rahasya", "kedarnath rahasya",
                "ancient india mystery", "ashoka ka itihas", "temple unsolved mystery", "pauranik katha sach"],
}


def _seconds(iso: str) -> int:
    import re
    m = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    h, mi, s = (int(x or 0) for x in m.groups()) if m else (0, 0, 0)
    return h * 3600 + mi * 60 + s


def search(token: str, q: str, since: datetime, call=youtube.call, n: int = 12) -> list:
    params = {"part": "snippet", "type": "video", "order": "viewCount", "regionCode": "IN", "relevanceLanguage": "hi", "maxResults": n,
              "publishedAfter": since.strftime("%Y-%m-%dT%H:%M:%SZ"), "q": q}
    status, _h, body = call("GET", f"{API}/search?" + urllib.parse.urlencode(params), token)
    if status != 200:
        return [{"error": status, "q": q, "why": str(body)[:160]}]
    ids = [i["id"]["videoId"] for i in body.get("items", [])]
    if not ids:
        return []
    status, _h, vids = call("GET", f"{API}/videos?part=statistics,contentDetails,snippet&id={','.join(ids)}", token)
    out = []
    for v in (vids.get("items") or []) if status == 200 else []:
        out.append({"id": v["id"], "title": v["snippet"]["title"], "channel": v["snippet"]["channelTitle"], "views": int(v["statistics"].get("viewCount", 0)),
                    "seconds": _seconds(v["contentDetails"].get("duration", "")), "published": v["snippet"]["publishedAt"][:10], "q": q})
    return sorted(out, key=lambda r: -r["views"])


def main(argv=None) -> int:
    since = datetime.now(timezone.utc) - timedelta(days=14)
    for ch, queries in QUERIES.items():
        token = youtube.access_token(ch)
        seen, rows = set(), []
        for q in queries:
            for r in search(token, q, since):
                if r.get("error"):
                    print(f"{ch}: search failed {r}", flush=True)
                    break
                if r["id"] not in seen:
                    seen.add(r["id"]); rows.append(r)
        rows.sort(key=lambda r: -r["views"])
        print(f"=== {ch}: top viewed Hindi videos in India, last 14 days (views | seconds | channel | title | query)", flush=True)
        for r in rows[:25]:
            print(f"{r['views']:>9} | {r['seconds']:>5} | {r['channel'][:22]:<22} | {r['title'][:80]} | {r['q']}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
