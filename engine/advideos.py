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
        lines.append(f"{label}: + " + "; ".join(f"{titles[v][:45]} (youtu.be/{v}, {stats[v][1]:.0f}% watched, {stats[v][0]} views, "
                                                f"+{stats[v][2]} subs)" for v in picks))
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


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    try:
        return run(live="--live" in argv)
    except Exception as e:
        print(f"crashed: {secrets.scrub(str(e))[:2000]}", flush=True)
        telegram.send(f"📣 Ad videos crashed: {secrets.scrub(str(e))[:200]}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
