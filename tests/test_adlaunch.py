import json
from datetime import date, datetime, timezone

from engine import adlaunch, pieces

NOW = datetime(2026, 10, 31, 10, 0, tzinfo=timezone.utc)
CFG = {"customer_id": "601-481-4549"}


def _long(root, channel, day, vid):
    p = pieces.Piece(id=f"{day.isoformat()}-{channel}-long", channel=channel, kind="long", publish_day=day, status="posted")
    p.ids = {"yt_id": vid}
    pieces.save(p, root)


def _setup(tmp_path):
    (tmp_path / "pieces").mkdir()
    (tmp_path / "assets" / "logo").mkdir(parents=True)
    for ch in ("sglearning", "arthvan"):
        (tmp_path / "assets" / "logo" / f"{ch}-320.png").write_bytes(b"png")
    _long(tmp_path, "sglearning", date(2026, 10, 28), "old")
    _long(tmp_path, "sglearning", date(2026, 10, 31), "new")        # public at 19:00 India = 13:30 UTC: not yet at NOW
    _long(tmp_path, "arthvan", date(2026, 10, 29), "myth")


def test_check_mode_validates_only_and_picks_the_newest_public_long(tmp_path):
    _setup(tmp_path)
    calls, sent = [], []
    def call(method, url, tok, json_body=None, data=None, headers=None):
        calls.append((url, json_body)); return 200, {}, {"mutateOperationResponses": []}
    assert adlaunch.run(tmp_path, NOW, {}, live=False, notify=sent.append, call=call, token="t", cfg=CFG) == 0
    url, body = calls[0]
    assert url.endswith("/customers/6014814549/googleAds:mutate") and body["validateOnly"] is True
    videos = [o["assetOperation"]["create"]["youtubeVideoAsset"]["youtubeVideoId"] for o in body["mutateOperations"]
              if "assetOperation" in o and o["assetOperation"]["create"]["type"] == "YOUTUBE_VIDEO"]
    assert videos == ["old", "myth"]
    camp = [o["campaignOperation"]["create"] for o in body["mutateOperations"] if "campaignOperation" in o][0]
    assert camp["advertisingChannelType"] == "DEMAND_GEN" and camp["endDateTime"].startswith("2026-11-13")
    assert "check passed" in sent[0] and not (tmp_path / "logs" / "ads-launch.json").exists()


def test_live_launches_each_channel_once(tmp_path):
    _setup(tmp_path)
    calls, sent = [], []
    def call(method, url, tok, json_body=None, data=None, headers=None):
        calls.append(json_body); return 200, {}, {}
    adlaunch.run(tmp_path, NOW, {}, live=True, notify=sent.append, call=call, token="t", cfg=CFG)
    assert calls[0]["validateOnly"] is False and "Ads launched" in sent[0]
    assert set(json.loads((tmp_path / "logs" / "ads-launch.json").read_text())) == {"sglearning", "arthvan"}
    adlaunch.run(tmp_path, NOW, {}, live=True, notify=sent.append, call=call, token="t", cfg=CFG)
    assert len(calls) == 1 and "nothing to launch" in sent[-1]


def test_google_refusal_is_reported(tmp_path):
    _setup(tmp_path)
    sent = []
    call = lambda m, u, t, json_body=None, data=None, headers=None: (400, {}, {"error": {"message": "bad field"}})
    assert adlaunch.run(tmp_path, NOW, {}, live=False, notify=sent.append, call=call, token="t", cfg=CFG) == 1
    assert "check found problems" in sent[0] and "bad field" in sent[0]
