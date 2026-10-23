"""What's working (founder, 23 Oct 2026): every Short posted in the last week with its numbers on YouTube, Instagram and Threads,
the strongest and the weakest, and each picture style against the doodle weeks. Report only: it changes nothing that is made or
posted. Monday on Telegram, after the weekly report; also saved to logs/whatworks.json.

python -m engine.whatworks [--send]
"""
import json
import sys
import urllib.parse
from datetime import date, timedelta
from pathlib import Path

from . import instagram, pieces, secrets, telegram, threads, youtube
from .config import CHANNELS, ROOT

ANALYTICS_URL = "https://youtubeanalytics.googleapis.com/v2/reports"
WEEK_DAYS = 7
LOOK_DAYS = 28                       # the style comparison looks back four weeks, so the doodle weeks stay in view
IG_METRICS = ["reach", "views", "saved", "shares", "ig_reels_avg_watch_time", "reels_skip_rate"]
THREADS_METRICS = "views,likes,replies,reposts,quotes,shares"


def shorts_between(start: date, end: date, root: Path = ROOT) -> list:
    return sorted((p for p in pieces.list_all(root) if p.kind == "short" and p.ids.get("yt_id") and start <= p.publish_day <= end),
                  key=lambda p: p.publish_day)


def look_of(piece) -> str:
    return (piece.topic or {}).get("look") or "doodle"          # every piece made before 23 Oct 2026 was drawn as a doodle


def youtube_by_video(channel: str, start: date, end: date, env=None, call=youtube.call) -> dict:
    """{video id: {views, watched_pct, watched_s}} from YouTube Analytics (numbers arrive two to three days late)."""
    token = youtube.access_token(channel, env)
    q = {"ids": "channel==MINE", "startDate": start.isoformat(), "endDate": end.isoformat(), "dimensions": "video",
         "metrics": "views,averageViewPercentage,averageViewDuration", "sort": "-views", "maxResults": "200"}
    status, _h, body = call("GET", ANALYTICS_URL + "?" + urllib.parse.urlencode(q), token)
    if status != 200:
        raise youtube.YouTubeError(f"analytics {status}: {secrets.scrub(json.dumps(body))[:200]}")
    idx = {c["name"]: i for i, c in enumerate(body.get("columnHeaders", []))}
    return {r[idx["video"]]: {"views": int(r[idx["views"]]), "watched_pct": round(float(r[idx["averageViewPercentage"]]), 1),
                              "watched_s": int(float(r[idx["averageViewDuration"]]))} for r in body.get("rows", [])}


def instagram_numbers(media_id: str, token: str, call=instagram.call) -> dict:
    """Reel insights; metric names Meta does not know (they change) are skipped one by one instead of losing the lot."""
    def values(data):
        return {m["name"]: (m.get("values") or [{}])[0].get("value") for m in data.get("data", [])}
    try:
        return values(call("GET", f"/{media_id}/insights", token, {"metric": ",".join(IG_METRICS)}))
    except Exception:
        out = {}
        for m in IG_METRICS:
            try:
                out.update(values(call("GET", f"/{media_id}/insights", token, {"metric": m})))
            except Exception:
                pass
        return out


def threads_numbers(media_id: str, token: str, call=threads.call) -> dict:
    try:
        data = call("GET", f"/{media_id}/insights", token, {"metric": THREADS_METRICS})
        return {m["name"]: (m.get("values") or [{}])[0].get("value", (m.get("total_value") or {}).get("value")) for m in data.get("data", [])}
    except Exception:
        return {}


def collect(start: date, end: date, env=None, root: Path = ROOT, yt=youtube_by_video, ig=instagram_numbers, th=threads_numbers) -> list:
    rows, yt_cache = [], {}
    ig_token = th_token = ""
    try:
        ig_token = secrets.get("IG_ACCESS_TOKEN", env)
    except secrets.MissingSecret:
        pass
    try:
        th_token = secrets.get("THREADS_ACCESS_TOKEN", env)
    except secrets.MissingSecret:
        pass
    for p in shorts_between(start, end, root):
        if p.channel not in yt_cache:
            try:
                yt_cache[p.channel] = yt(p.channel, start, date.today(), env)   # views since posting, up to today
            except Exception as e:
                yt_cache[p.channel] = {"_error": str(e)[:120]}
        y = yt_cache[p.channel].get(p.ids["yt_id"], {})
        i = ig(p.ids["ig_reel_id"], ig_token) if ig_token and p.ids.get("ig_reel_id") else {}
        t = th(p.ids["threads_id"], th_token) if th_token and p.ids.get("threads_id") else {}
        title = ((p.script or {}).get("captions", {}).get("youtube", {}).get("title") or p.topic.get("title") or p.id)
        rows.append({"id": p.id, "channel": p.channel, "day": p.publish_day.isoformat(), "look": look_of(p), "title": title[:70],
                     "yt_views": y.get("views", 0), "yt_watched_pct": y.get("watched_pct"), "ig_views": i.get("views") or i.get("reach") or 0,
                     "ig_saves": i.get("saved") or 0, "ig_skip_rate": i.get("reels_skip_rate"), "th_views": t.get("views") or 0,
                     "reach": (y.get("views", 0) or 0) + (i.get("views") or i.get("reach") or 0) + (t.get("views") or 0)})
    return rows


def by_look(rows: list) -> dict:
    """{channel: {look: {shorts, avg_reach, avg_watched_pct}}}: the new picture styles against the doodle weeks."""
    out = {}
    for r in rows:
        g = out.setdefault(r["channel"], {}).setdefault(r["look"], {"shorts": 0, "reach": 0, "pct": []})
        g["shorts"] += 1
        g["reach"] += r["reach"]
        if r["yt_watched_pct"] is not None:
            g["pct"].append(r["yt_watched_pct"])
    return {ch: {lk: {"shorts": g["shorts"], "avg_reach": round(g["reach"] / g["shorts"]),
                      "avg_watched_pct": round(sum(g["pct"]) / len(g["pct"]), 1) if g["pct"] else None}
                 for lk, g in looks.items()} for ch, looks in out.items()}


def text(week: list, looks: dict) -> str:
    lines = ["📊 What's working (last 7 days, report only: nothing changes on its own)"]
    for ch in CHANNELS:
        rs = sorted((r for r in week if r["channel"] == ch), key=lambda r: r["reach"], reverse=True)
        lines.append("")
        lines.append(f"{CHANNELS[ch].display_name}: {len(rs)} Shorts")
        for r in rs:
            pct = f", watched {r['yt_watched_pct']}%" if r["yt_watched_pct"] is not None else ""
            skip = f", skipped early {r['ig_skip_rate']}%" if r["ig_skip_rate"] is not None else ""
            lines.append(f"  {r['day'][5:]} {r['title']}: reach {r['reach']:,} (YT {r['yt_views']:,}{pct}; IG {r['ig_views']:,}, saves {r['ig_saves']}{skip}; Threads {r['th_views']:,})")
        if len(rs) >= 2:
            lines.append(f"  ⬆ strongest: {rs[0]['title']}")
            lines.append(f"  ⬇ weakest: {rs[-1]['title']}")
        for lk, g in sorted((looks.get(ch) or {}).items()):
            pct = f", watched {g['avg_watched_pct']}%" if g["avg_watched_pct"] is not None else ""
            lines.append(f"  look {lk}: {g['shorts']} Shorts, average reach {g['avg_reach']:,}{pct} (last 4 weeks)")
    lines.append("")
    lines.append("YouTube numbers arrive 2-3 days late, so the newest Shorts look small.")
    return "\n".join(lines)


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    end = date.today() - timedelta(days=1)
    month = collect(end - timedelta(days=LOOK_DAYS - 1), end)                    # one pull serves both the week and the looks
    week_start = (end - timedelta(days=WEEK_DAYS - 1)).isoformat()
    week = [r for r in month if r["day"] >= week_start]
    looks = by_look(month)
    out = text(week, looks)
    (ROOT / "logs").mkdir(parents=True, exist_ok=True)
    (ROOT / "logs" / "whatworks.json").write_text(json.dumps({"end": end.isoformat(), "week": week, "looks": looks}, indent=1, ensure_ascii=False))
    print(out)
    if "--send" in argv:
        telegram.send(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
