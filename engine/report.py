"""Weekly report: YouTube Analytics and Instagram insights against the day-90 targets, to Telegram and logs/weekly.json (spec §3 schedules, §E).

python -m engine.report
"""
import json
import sys
import urllib.parse
from datetime import date, timedelta
from pathlib import Path

from . import instagram, pieces, secrets, telegram, youtube
from .config import CHANNELS, ROOT

ANALYTICS_URL = "https://youtubeanalytics.googleapis.com/v2/reports"
TARGETS = {"sglearning": {"subs": 500, "best_short": 100_000, "long_avg_views": 3000},
           "arthvan": {"subs": 1000, "best_short": 300_000, "long_avg_views": 10_000}}
HOOK_CHANGE_THRESHOLD = 200


def youtube_week(rows: dict, shorts: set, longs: set) -> dict:
    """Totals and per-kind averages from an Analytics report with dimension video and metrics views, estimatedMinutesWatched, subscribersGained, averageViewPercentage."""
    cols = [c["name"] for c in rows.get("columnHeaders", [])]
    idx = {name: i for i, name in enumerate(cols)}
    out = {"views": 0, "minutes": 0, "subs_gained": 0, "avg_view_pct": 0.0, "shorts_avg_views": 0, "best_short": 0, "long_avg_views": 0}
    s_views, l_views, pct = [], [], []
    weighted, weight = 0.0, 0
    for r in rows.get("rows", []):
        vid = r[idx["video"]]
        views = int(r[idx.get("views", 1)])
        out["views"] += views
        out["minutes"] += int(r[idx.get("estimatedMinutesWatched", 2)])
        out["subs_gained"] += int(r[idx.get("subscribersGained", 3)])
        pct.append(float(r[idx.get("averageViewPercentage", 4)]))
        weighted += views * pct[-1]; weight += views
        if vid in shorts:
            s_views.append(views)
        elif vid in longs:
            l_views.append(views)
    out["avg_view_pct"] = round(weighted / weight, 1) if weight else 0.0       # weighted by views
    out["shorts_avg_views"] = int(sum(s_views) / len(s_views)) if s_views else 0
    out["best_short"] = max(s_views) if s_views else 0
    out["long_avg_views"] = int(sum(l_views) / len(l_views)) if l_views else 0
    return out


def fetch_youtube_week(channel: str, start: date, end: date, env=None, call=youtube.call) -> dict:
    token = youtube.access_token(channel, env)
    q = {"ids": "channel==MINE", "startDate": start.isoformat(), "endDate": end.isoformat(),
         "metrics": "views,estimatedMinutesWatched,subscribersGained,averageViewPercentage", "dimensions": "video", "sort": "-views", "maxResults": "50"}
    status, _h, body = call("GET", ANALYTICS_URL + "?" + urllib.parse.urlencode(q), token)
    if status != 200:
        raise youtube.YouTubeError(f"analytics {status}: {secrets.scrub(json.dumps(body))[:200]}")
    ours = [p for p in pieces.list_all(ROOT) if p.channel == channel and p.ids.get("yt_id")]
    shorts = {p.ids["yt_id"] for p in ours if p.kind == "short"}
    longs = {p.ids["yt_id"] for p in ours if p.kind == "long"}
    return youtube_week(body, shorts, longs)


def fetch_instagram_week(env=None, call=instagram.call) -> dict:
    try:
        token, ig_id = secrets.get("IG_ACCESS_TOKEN", env), secrets.get("IG_USER_ID", env)
        ins = call("GET", f"/{ig_id}/insights", token, {"metric": "reach", "period": "week"})
        reach = (ins.get("data") or [{}])[0].get("values", [{}])[-1].get("value", 0)
        me = call("GET", f"/{ig_id}", token, {"fields": "followers_count"})
        return {"reach": reach, "followers": me.get("followers_count", 0)}
    except Exception as e:
        return {"error": secrets.scrub(str(e))[:120]}


def _pct(value, target) -> str:
    return f"{value:,} ({int(100 * value / target)}% of {target:,})"


def text(data: dict, targets: dict = TARGETS) -> str:
    lines = ["SG Content weekly report"]
    for ch, d in data.items():
        t = targets.get(ch, {})
        lines.append(f"{ch} ({CHANNELS[ch].display_name if ch in CHANNELS else ch}): views {d.get('views', 0):,}, watch {d.get('minutes', 0):,} min, "
                     f"avg watched {d.get('avg_view_pct', 0)}%")
        lines.append(f"  subs +{d.get('subs_gained', 0)} ({int(100 * d.get('subs_gained', 0) / t.get('subs', 1))}% of {t.get('subs', 0):,}); "
                     f"best Short {_pct(d.get('best_short', 0), t.get('best_short', 1))}; long avg {_pct(d.get('long_avg_views', 0), t.get('long_avg_views', 1))}")
        lines.append(f"  Shorts average {d.get('shorts_avg_views', 0):,} views" +
                     (" — under 200: change the hook formula before raising volume" if d.get("shorts_avg_views", 0) < HOOK_CHANGE_THRESHOLD else ""))
        ig = d.get("ig") or {}
        if ig:
            lines.append("  Instagram: " + ", ".join(f"{k} {v:,}" if isinstance(v, int) else f"{k} {v}" for k, v in ig.items()))
        for c in (d.get("top_comments") or [])[:5]:
            lines.append(f"  💬 {c}")
    return "\n".join(lines)


def main(argv=None) -> int:
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=6)
    data = {}
    for ch in CHANNELS:
        try:
            data[ch] = fetch_youtube_week(ch, start, end)
        except Exception as e:
            data[ch] = {"error": secrets.scrub(str(e))[:120]}
    data["sglearning"]["ig"] = fetch_instagram_week()
    out = text(data)
    (ROOT / "logs").mkdir(parents=True, exist_ok=True)
    (ROOT / "logs" / "weekly.json").write_text(json.dumps({"start": start.isoformat(), "end": end.isoformat(), "data": data}, indent=1, ensure_ascii=False))
    telegram.send(out)
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
