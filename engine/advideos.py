"""Gives each test ad its channel's best-watched long videos (founder, 31 Oct 2026: "add 2 best videos to each campaign today").

One Demand Gen ad holds up to five videos and Google moves the same daily budget toward the one that brings clicks and subscribers, so
adding videos tests them against each other at no extra cost. "Best" is the share of the video people watch without ads
(averageViewPercentage, last 90 days, at least MIN_VIEWS views), then subscribers gained; only public videos of 3 minutes or more.

python -m engine.advideos            check only: prints the picks and lets Google validate the change; nothing changes
python -m engine.advideos --live     adds the picks to each channel's ad
"""
import re
import sys
import urllib.parse
from datetime import datetime, timedelta, timezone

from . import ads, secrets, telegram, youtube
from .config import CHANNELS

DATA = "https://www.googleapis.com/youtube/v3"
ADD = 2
MIN_VIEWS = 20
MIN_SECONDS = 180
MAX_VIDEOS = 5


def _seconds(iso: str) -> int:
    m = re.fullmatch(r"P(?:\d+D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    return 0 if not m else int(m.group(1) or 0) * 3600 + int(m.group(2) or 0) * 60 + int(m.group(3) or 0)


def _get(url: str, token: str, call):
    status, _h, body = call("GET", url, token)
    if status != 200:
        raise ads.AdsError(f"YouTube {status}: {secrets.scrub(str(body))[:200]}")
    return body


def long_videos(token: str, call=youtube.call) -> dict:
    """{video id: title} of the channel's public uploads of MIN_SECONDS or more."""
    ch = _get(f"{DATA}/channels?part=contentDetails&mine=true", token, call)
    uploads = ch["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    ids, page = [], ""
    for _ in range(4):                                         # newest 200 uploads are plenty
        body = _get(f"{DATA}/playlistItems?part=contentDetails&maxResults=50&playlistId={uploads}{'&pageToken=' + page if page else ''}", token, call)
        ids += [i["contentDetails"]["videoId"] for i in body.get("items", [])]
        page = body.get("nextPageToken", "")
        if not page:
            break
    out = {}
    for i in range(0, len(ids), 50):
        body = _get(f"{DATA}/videos?part=contentDetails,status,snippet&id={','.join(ids[i:i + 50])}", token, call)
        for v in body.get("items", []):
            if v["status"].get("privacyStatus") == "public" and _seconds(v["contentDetails"].get("duration")) >= MIN_SECONDS:
                out[v["id"]] = v["snippet"].get("title", "")
    return out


def watch_stats(token: str, ids: list, today, call=youtube.call) -> dict:
    """{video id: (views, averageViewPercentage, subscribersGained)} over the last 90 days."""
    if not ids:
        return {}
    q = {"ids": "channel==MINE", "startDate": (today - timedelta(days=90)).isoformat(), "endDate": today.isoformat(),
         "metrics": "views,averageViewPercentage,subscribersGained", "dimensions": "video", "filters": "video==" + ",".join(ids),
         "maxResults": 200, "sort": "-views"}
    body = _get(ads.ANALYTICS_URL + "?" + urllib.parse.urlencode(q), token, call)
    return {r[0]: (int(r[1]), float(r[2]), int(r[3])) for r in body.get("rows", [])}


def pick(stats: dict, exclude: set, n: int = ADD) -> list:
    ok = [(v, s) for v, s in stats.items() if v not in exclude and s[0] >= MIN_VIEWS]
    return [v for v, _s in sorted(ok, key=lambda x: (-x[1][1], -x[1][2], -x[1][0]))[:n]]


def run(cfg=None, env=None, live: bool = False, notify=telegram.send, call=ads.call_full, yt_call=youtube.call,
        ads_token=None, yt_token=youtube.access_token, now=None) -> int:
    sent = notify

    def notify(text):                                         # also in the run log
        print(text, flush=True)
        sent(text)
    cfg = ads.settings() if cfg is None else cfg
    cid = str(cfg.get("customer_id", "")).replace("-", "")
    today = (now or datetime.now(timezone.utc)).date()
    tok = ads_token or ads.access_token(env)
    rows = ads.search(cid, "SELECT campaign.name, ad_group_ad.ad.resource_name, ad_group_ad.ad.demand_gen_video_responsive_ad.videos "
                           "FROM ad_group_ad WHERE campaign.name LIKE 'SG test %' AND campaign.status != 'REMOVED' "
                           "AND ad_group_ad.status != 'REMOVED'", tok, cfg, call)
    if not rows:
        notify("📣 Ad videos: no test ads found.")
        return 1
    ops, lines, n = [], [], 0
    for r in rows:
        name = r["campaign"]["name"]
        channel = next((c for c in ("sglearning", "arthvan") if name.endswith(CHANNELS[c].display_name)), None)
        if channel is None:
            continue
        ad = r["adGroupAd"]["ad"]
        have = [v["asset"] for v in (ad.get("demandGenVideoResponsiveAd") or {}).get("videos", [])]
        have_ids = set()
        if have:
            q = "SELECT asset.resource_name, asset.youtube_video_asset.youtube_video_id FROM asset WHERE asset.resource_name IN (" + \
                ",".join(f"'{a}'" for a in have) + ")"
            have_ids = {a["asset"]["youtubeVideoAsset"]["youtubeVideoId"] for a in ads.search(cid, q, tok, cfg, call)}
        ytok = yt_token(channel, env)
        titles = long_videos(ytok, yt_call)
        stats = watch_stats(ytok, list(titles), today, yt_call)
        chosen = (cfg.get("ad_videos") or {}).get(channel)      # the founder's own pick wins over the data (31 Oct 2026: views too thin)
        if chosen:
            picks = [v for v in chosen if v in titles and v not in have_ids][:MAX_VIDEOS - len(have)]
            lines += [f"{CHANNELS[channel].display_name}: youtu.be/{v} skipped (not a public long video)" for v in chosen if v not in titles]
        else:
            picks = pick(stats, have_ids, min(ADD, MAX_VIDEOS - len(have)))
        label = CHANNELS[channel].display_name
        if not picks:
            lines.append(f"{label}: no other long video with {MIN_VIEWS}+ views yet; ad unchanged")
            continue
        new = []
        for v in picks:
            n += 1
            res = f"customers/{cid}/assets/-{900 + n}"
            ops.append({"assetOperation": {"create": {"resourceName": res, "name": f"{name} video {v}", "type": "YOUTUBE_VIDEO",
                                                      "youtubeVideoAsset": {"youtubeVideoId": v}}}})
            new.append(res)
        ops.append({"adOperation": {"update": {"resourceName": ad["resourceName"],
                                               "demandGenVideoResponsiveAd": {"videos": [{"asset": a} for a in have + new]}},
                                    "updateMask": "demand_gen_video_responsive_ad.videos"}})
        lines.append(f"{label}: + " + "; ".join(f"{titles[v][:45]} (youtu.be/{v}" + (f", {stats[v][1]:.0f}% watched, {stats[v][0]} views, "
                                                f"+{stats[v][2]} subs)" if v in stats else ")") for v in picks))
    if not ops:
        notify("📣 Ad videos: nothing to add (" + "; ".join(lines) + ").")
        return 0
    status, _h, body = call("POST", f"{ads.API}/customers/{cid}/googleAds:mutate", tok,
                            json_body={"mutateOperations": ops, "validateOnly": not live}, headers=ads._headers(cfg))
    if status != 200:
        notify(f"📣 Ad videos {'FAILED' if live else 'check found problems'} ({status}):\n{secrets.scrub(ads.errors_text(body))[:2000]}\n"
               + "\n".join(lines))
        return 1
    notify(f"📣 Ad videos {'added' if live else 'check passed (nothing changed)'}; same $5 a day per campaign, Google moves it to the "
           "best video:\n" + "\n".join(lines))
    return 0


def _ads_and_ids(cid, tok, cfg, call) -> list:
    """[(channel, campaign name, ad resource name, [(asset resource name, youtube id)])] for every live test ad."""
    rows = ads.search(cid, "SELECT campaign.name, ad_group_ad.ad.resource_name, ad_group_ad.ad.demand_gen_video_responsive_ad.videos "
                           "FROM ad_group_ad WHERE campaign.name LIKE 'SG test %' AND campaign.status != 'REMOVED' "
                           "AND ad_group_ad.status != 'REMOVED'", tok, cfg, call)
    out = []
    for r in rows:
        name = r["campaign"]["name"]
        channel = next((c for c in ("sglearning", "arthvan") if name.endswith(CHANNELS[c].display_name)), None)
        if channel is None:
            continue
        ad = r["adGroupAd"]["ad"]
        have = [v["asset"] for v in (ad.get("demandGenVideoResponsiveAd") or {}).get("videos", [])]
        ids = {}
        if have:
            q = "SELECT asset.resource_name, asset.youtube_video_asset.youtube_video_id FROM asset WHERE asset.resource_name IN (" + \
                ",".join(f"'{a}'" for a in have) + ")"
            ids = {a["asset"]["resourceName"]: a["asset"]["youtubeVideoAsset"]["youtubeVideoId"] for a in ads.search(cid, q, tok, cfg, call)}
        out.append((channel, name, ad["resourceName"], [(a, ids.get(a, "?")) for a in have]))
    return out


def report(cfg=None, env=None, notify=telegram.send, call=ads.call_full, yt_call=youtube.call, ads_token=None,
           yt_token=youtube.access_token, now=None, days: int = 7) -> int:
    """Read-only: per video in each test ad, the last `days` days of ad cost and clicks (where Google reports them per video) and YouTube
    views, subscribers gained and subscribers gained from ads; plus each channel's newest public long video not yet in its ad."""
    sent = notify

    def notify(text):
        print(text, flush=True)
        sent(text)
    cfg = ads.settings() if cfg is None else cfg
    cid = str(cfg.get("customer_id", "")).replace("-", "")
    today = (now or datetime.now(timezone.utc)).date()
    start = today - timedelta(days=days)
    tok = ads_token or ads.access_token(env)
    per_asset = {}
    try:                                                        # Google may not report Demand Gen spend per video; then it is left out
        q = ("SELECT asset.youtube_video_asset.youtube_video_id, metrics.cost_micros, metrics.clicks, metrics.impressions FROM ad_group_ad_asset_view "
             f"WHERE segments.date BETWEEN '{start.isoformat()}' AND '{today.isoformat()}' AND ad_group_ad_asset_view.field_type = 'YOUTUBE_VIDEO'")
        for r in ads.search(cid, q, tok, cfg, call):
            v = r.get("asset", {}).get("youtubeVideoAsset", {}).get("youtubeVideoId")
            m = r.get("metrics", {})
            a = per_asset.setdefault(v, [0.0, 0, 0])
            a[0] += int(m.get("costMicros", 0)) / 1e6; a[1] += int(m.get("clicks", 0)); a[2] += int(m.get("impressions", 0))
    except Exception as e:
        print(f"per-video ad numbers not available: {secrets.scrub(str(e))[:200]}", flush=True)
    lines = []
    for channel, name, _ad, vids in _ads_and_ids(cid, tok, cfg, call):
        ytok = yt_token(channel, env)
        ids = [v for _a, v in vids]
        q = {"ids": "channel==MINE", "startDate": start.isoformat(), "endDate": today.isoformat(), "metrics": "views,subscribersGained",
             "dimensions": "video", "filters": "video==" + ",".join(ids)}
        yt = {r[0]: (int(r[1]), int(r[2])) for r in _get(ads.ANALYTICS_URL + "?" + urllib.parse.urlencode(q), ytok, yt_call).get("rows", [])}
        titles = long_videos(ytok, yt_call)
        newest = next((v for v in titles if v not in ids), None)          # uploads come newest first
        lines.append(f"{CHANNELS[channel].display_name}:")
        for v in ids:
            cost, clicks, imps = per_asset.get(v, (None, None, None))
            views, subs = yt.get(v, (0, 0))
            ad_part = f"ad ${cost:.2f}, {clicks} clicks, {imps} shown" if cost is not None else "ad per-video n/a"
            lines.append(f"  youtu.be/{v} {titles.get(v, '')[:40]}: {ad_part}; YouTube {views} views, +{subs} subs")
        lines.append(f"  newest long video not in the ad: " + (f"youtu.be/{newest} {titles[newest][:40]}" if newest else "none"))
    notify(f"📣 Ad videos, last {days} days (read-only):\n" + "\n".join(lines))
    return 0


def set_videos(wanted: dict, cfg=None, env=None, live: bool = False, notify=telegram.send, call=ads.call_full, ads_token=None) -> int:
    """Sets each named channel's test ad to exactly these YouTube ids (founder, 1 Nov 2026: "swap automatically and tell me after").
    Kept videos reuse their assets; new ones get new assets. Check-only unless live; budgets and status are never touched."""
    sent = notify

    def notify(text):
        print(text, flush=True)
        sent(text)
    cfg = ads.settings() if cfg is None else cfg
    cid = str(cfg.get("customer_id", "")).replace("-", "")
    tok = ads_token or ads.access_token(env)
    ops, lines, n = [], [], 0
    for channel, name, ad, vids in _ads_and_ids(cid, tok, cfg, call):
        ids = wanted.get(channel)
        if not ids:
            continue
        if not 1 <= len(ids) <= MAX_VIDEOS:
            notify(f"📣 Ad videos: {channel} needs 1 to {MAX_VIDEOS} videos, got {len(ids)}; nothing changed.")
            return 1
        by_id = {v: a for a, v in vids}
        assets = []
        for v in ids:
            if v in by_id:
                assets.append(by_id[v])
                continue
            n += 1
            res = f"customers/{cid}/assets/-{950 + n}"
            ops.append({"assetOperation": {"create": {"resourceName": res, "name": f"{name} video {v}", "type": "YOUTUBE_VIDEO",
                                                      "youtubeVideoAsset": {"youtubeVideoId": v}}}})
            assets.append(res)
        ops.append({"adOperation": {"update": {"resourceName": ad, "demandGenVideoResponsiveAd": {"videos": [{"asset": a} for a in assets]}},
                                    "updateMask": "demand_gen_video_responsive_ad.videos"}})
        old = [v for _a, v in vids]
        lines.append(f"{CHANNELS[channel].display_name}: out {', '.join(v for v in old if v not in ids) or '-'}; "
                     f"in {', '.join(v for v in ids if v not in old) or '-'}; now {', '.join(ids)}")
    if not ops:
        notify("📣 Ad videos: nothing to change.")
        return 0
    status, _h, body = call("POST", f"{ads.API}/customers/{cid}/googleAds:mutate", tok,
                            json_body={"mutateOperations": ops, "validateOnly": not live}, headers=ads._headers(cfg))
    if status != 200:
        notify(f"📣 Ad videos swap {'FAILED' if live else 'check found problems'} ({status}):\n{secrets.scrub(ads.errors_text(body))[:2000]}")
        return 1
    notify(f"🔁 Ad videos {'swapped' if live else 'swap check passed (nothing changed)'}; same $5 a day:\n" + "\n".join(lines))
    return 0


def parse_wanted(text: str) -> dict:
    """'sglearning=a,b arthvan=c' -> {"sglearning": ["a", "b"], "arthvan": ["c"]}"""
    out = {}
    for part in (text or "").split():
        ch, _, ids = part.partition("=")
        out[ch] = [i for i in ids.split(",") if i]
    return out


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    try:
        if "--report" in argv:
            return report()
        if "--set" in argv:
            return set_videos(parse_wanted(argv[argv.index("--set") + 1]), live="--live" in argv)
        return run(live="--live" in argv)
    except Exception as e:
        print(f"crashed: {secrets.scrub(str(e))[:2000]}", flush=True)
        telegram.send(f"📣 Ad videos crashed: {secrets.scrub(str(e))[:200]}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
