import json
from datetime import date, datetime, timezone

from engine import adlaunch, pieces

NOW = datetime(2026, 10, 31, 10, 0, tzinfo=timezone.utc)
CFG = {"customer_id": "601-481-4549", "limits": {"INR": {"budget_per_channel": 2000}, "USD": {"budget_per_channel": 21}}}


def _api(calls, currency="USD", status=200, body=None):
    def call(method, url, tok, json_body=None, data=None, headers=None):
        if url.endswith(":search"):
            return 200, {}, {"results": [{"customer": {"currencyCode": currency}}]}
        calls.append((url, json_body))
        return status, {}, body if body is not None else {}
    return call


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
    assert adlaunch.run(tmp_path, NOW, {}, live=False, notify=sent.append, call=_api(calls), token="t", cfg=CFG) == 0
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
    adlaunch.run(tmp_path, NOW, {}, live=True, notify=sent.append, call=_api(calls), token="t", cfg=CFG)
    assert calls[0][1]["validateOnly"] is False and "Ads launched: $21 per channel" in sent[0] and "$1.50 a day" in sent[0]
    assert set(json.loads((tmp_path / "logs" / "ads-launch.json").read_text())) == {"sglearning", "arthvan"}
    adlaunch.run(tmp_path, NOW, {}, live=True, notify=sent.append, call=_api(calls), token="t", cfg=CFG)
    assert len(calls) == 1 and "nothing to launch" in sent[-1]


def test_google_refusal_is_reported(tmp_path):
    _setup(tmp_path)
    sent = []
    assert adlaunch.run(tmp_path, NOW, {}, live=False, notify=sent.append, call=_api([], status=400, body={"error": {"message": "bad field"}}),
                        token="t", cfg=CFG) == 1
    assert "check found problems" in sent[0] and "bad field" in sent[0]


def test_budget_follows_the_account_currency(tmp_path):
    """31 Oct 2026: Rs 143 a day was sent as a plain number to a USD account and became $143 a day."""
    _setup(tmp_path)
    for currency, daily in (("USD", "1500000"), ("INR", "142860000")):
        calls = []
        adlaunch.run(tmp_path, NOW, {}, live=False, notify=lambda m: None, call=_api(calls, currency), token="t", cfg=CFG)
        budgets = [o["campaignBudgetOperation"]["create"]["amountMicros"] for o in calls[0][1]["mutateOperations"] if "campaignBudgetOperation" in o]
        assert budgets == [daily, daily]


def test_unknown_currency_launches_nothing(tmp_path):
    _setup(tmp_path)
    calls, sent = [], []
    assert adlaunch.run(tmp_path, NOW, {}, live=True, notify=sent.append, call=_api(calls, "EUR"), token="t", cfg=CFG) == 1
    assert calls == [] and "nothing launched" in sent[0]


def test_set_budgets_fixes_the_test_campaigns_and_never_resumes():
    calls, sent = [], []
    def call(method, url, tok, json_body=None, data=None, headers=None):
        if url.endswith(":search") and "currency_code" in json_body["query"]:
            return 200, {}, {"results": [{"customer": {"currencyCode": "USD"}}]}
        if url.endswith(":search"):
            return 200, {}, {"results": [{"campaign": {"name": "SG test A", "status": "PAUSED"}, "campaignBudget": {"resourceName": "customers/1/campaignBudgets/7"}}]}
        calls.append(json_body); return 200, {}, {}
    assert adlaunch.set_budgets(CFG, {}, notify=sent.append, call=call, token="t", live=True) == 0
    op = calls[0]["mutateOperations"][0]["campaignBudgetOperation"]
    assert op["update"]["amountMicros"] == "1500000" and op["updateMask"] == "amount_micros" and "status" not in op["update"]
    assert "$1.50 a day" in sent[0] and "stay paused" in sent[0]


def _resume_api(calls, budgets):
    def call(method, url, tok, json_body=None, data=None, headers=None):
        if url.endswith(":search") and "currency_code" in json_body["query"]:
            return 200, {}, {"results": [{"customer": {"currencyCode": "USD"}}]}
        if url.endswith(":search"):
            return 200, {}, {"results": [{"campaign": {"id": str(i), "name": f"SG test {i}", "status": "PAUSED"},
                                          "campaignBudget": {"amountMicros": str(m)}} for i, m in enumerate(budgets, 1)]}
        calls.append((url, json_body)); return 200, {}, {}
    return call


def test_resume_turns_on_only_campaigns_within_the_limit():
    calls, sent = [], []
    assert adlaunch.resume(CFG, {}, notify=sent.append, call=_resume_api(calls, [1_500_000, 143_000_000]), token="t") == 1
    url, body = calls[0]
    assert url.endswith("/campaigns:mutate") and body["operations"] == [
        {"update": {"resourceName": "customers/6014814549/campaigns/1", "status": "ENABLED"}, "updateMask": "status"}]
    assert "$1.50 a day" in sent[0] and "SG test 2" in sent[0]


def test_resume_never_turns_on_a_campaign_still_on_the_old_budget():
    calls, sent = [], []
    assert adlaunch.resume(CFG, {}, notify=sent.append, call=_resume_api(calls, [143_000_000, 143_000_000]), token="t") == 1
    assert calls == [] and "nothing resumed" in sent[0]
