from datetime import datetime, timezone

from engine import advideos

CFG = {"customer_id": "601-481-4549"}
NOW = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)


def test_duration_parsing():
    assert advideos._seconds("PT12M3S") == 723 and advideos._seconds("PT59S") == 59 and advideos._seconds("PT1H") == 3600


def test_pick_prefers_share_watched_and_skips_the_current_and_thin_videos():
    stats = {"cur": (500, 90.0, 9), "a": (100, 40.0, 1), "b": (80, 55.0, 0), "c": (5, 99.0, 3), "d": (60, 40.0, 4)}
    assert advideos.pick(stats, {"cur"}) == ["b", "d"]


def _yt(method, url, tok, json_body=None, data=None, headers=None):
    if "/channels?" in url:
        return 200, {}, {"items": [{"contentDetails": {"relatedPlaylists": {"uploads": "UU1"}}}]}
    if "/playlistItems?" in url:
        return 200, {}, {"items": [{"contentDetails": {"videoId": v}} for v in ("cur", "a", "b", "short", "priv")]}
    if "/videos?" in url:
        mk = lambda v, d, p="public": {"id": v, "contentDetails": {"duration": d}, "status": {"privacyStatus": p}, "snippet": {"title": "T " + v}}
        return 200, {}, {"items": [mk("cur", "PT12M"), mk("a", "PT10M"), mk("b", "PT8M"), mk("short", "PT50S"), mk("priv", "PT9M", "private")]}
    assert "short" not in url and "priv" not in url
    return 200, {}, {"rows": [["cur", 500, 90.0, 9], ["a", 100, 40.0, 1], ["b", 80, 55.0, 0]]}


def _ads(calls):
    def call(method, url, tok, json_body=None, headers=None):
        if url.endswith(":search") and "FROM ad_group_ad" in json_body["query"]:
            return 200, {}, {"results": [{"campaign": {"name": "SG test 2026-10-31 SG-MYTH-WORLD"},
                                          "adGroupAd": {"ad": {"resourceName": "customers/6014814549/ads/77",
                                                               "demandGenVideoResponsiveAd": {"videos": [{"asset": "customers/6014814549/assets/5"}]}}}}]}
        if url.endswith(":search"):
            return 200, {}, {"results": [{"asset": {"youtubeVideoAsset": {"youtubeVideoId": "cur"}}}]}
        calls.append(json_body)
        return 200, {}, {}
    return call


def test_check_adds_two_videos_to_the_same_ad_without_touching_budget_or_status():
    calls, sent = [], []
    assert advideos.run(CFG, {}, notify=sent.append, call=_ads(calls), yt_call=_yt, ads_token="t", yt_token=lambda c, e: "y", now=NOW) == 0
    body = calls[0]
    assert body["validateOnly"] is True
    ops = body["mutateOperations"]
    assert [o["assetOperation"]["create"]["youtubeVideoAsset"]["youtubeVideoId"] for o in ops if "assetOperation" in o] == ["b", "a"]
    upd = next(o["adOperation"] for o in ops if "adOperation" in o)
    assert upd["updateMask"] == "demand_gen_video_responsive_ad.videos"
    assert [v["asset"] for v in upd["update"]["demandGenVideoResponsiveAd"]["videos"]][0] == "customers/6014814549/assets/5"
    assert len(upd["update"]["demandGenVideoResponsiveAd"]["videos"]) == 3
    assert not any("campaignBudgetOperation" in o or "campaignOperation" in o for o in ops)
    assert "check passed" in sent[0] and "youtu.be/b" in sent[0] and "55% watched" in sent[0]


def test_founder_pick_wins_and_skips_videos_that_are_not_public_longs():
    calls, sent = [], []
    cfg = {**CFG, "ad_videos": {"arthvan": ["a", "short"]}}
    assert advideos.run(cfg, {}, notify=sent.append, call=_ads(calls), yt_call=_yt, ads_token="t", yt_token=lambda c, e: "y", now=NOW) == 0
    ops = calls[0]["mutateOperations"]
    assert [o["assetOperation"]["create"]["youtubeVideoAsset"]["youtubeVideoId"] for o in ops if "assetOperation" in o] == ["a"]
    assert "youtu.be/short skipped" in sent[0]
