import json
from datetime import datetime, timezone

from engine import ads

NOW = datetime(2026, 11, 3, 19, 30, tzinfo=timezone.utc)
CFG = {"customer_id": "123-456-7890", "test_start": "2026-11-01", "monthly_cap_inr": 6000, "baseline_subs_per_day": 0.5,
       "pause_rule": {"min_spend_inr": 1500, "max_cost_per_sub_inr": 25}}


def _api(cost_rupees, calls):
    def call(method, url, token, json_body=None, data=None, headers=None):
        calls.append((method, url, json_body))
        if url.endswith(":search"):
            if "currency_code" in json_body["query"]:
                return 200, {}, {"results": [{"customer": {"currencyCode": "INR"}}]}
            return 200, {}, {"results": [{"campaign": {"id": "9", "name": "Grow SG", "status": "ENABLED"},
                                          "metrics": {"costMicros": str(int(cost_rupees * 1_000_000))}}]}
        return 200, {}, {"results": []}
    return call


def _run(tmp_path, cost, subs_each, monkeypatch, paused=False):
    (tmp_path / "logs").mkdir(exist_ok=True)
    monkeypatch.setattr(ads.telegram, "paused", lambda root: paused)
    calls, sent = [], []
    ads.run(tmp_path, NOW, {}, notify=sent.append, report=True, cfg=CFG, call=_api(cost, calls), token="t", subs=lambda ch: subs_each)
    return calls, sent, json.loads((tmp_path / "logs" / "ads.json").read_text())


def test_cheap_subscribers_are_reported_and_nothing_is_paused(tmp_path, monkeypatch):
    calls, sent, state = _run(tmp_path, 1600, 60, monkeypatch)           # 120 new, 2 usual over 3 days
    assert state["subs_above_usual"] == 118 and state["cost_per_sub"] == 13.6
    assert not any(":mutate" in u for _m, u, _b in calls)
    assert sent[-1].startswith("📣 Ads: Rs 1,600 today, Rs 1,600 since 11-01")


def test_dear_subscribers_after_the_minimum_spend_pause_the_campaigns(tmp_path, monkeypatch):
    calls, sent, state = _run(tmp_path, 1600, 10, monkeypatch)           # 18 above usual: Rs 89 each
    mutate = [b for _m, u, b in calls if u.endswith("campaigns:mutate")]
    assert mutate and mutate[0]["operations"][0]["update"]["status"] == "PAUSED"
    assert "costs more than Rs 25" in sent[0] and state["paused_now"] == ["9"]


def test_a_founder_pause_pauses_the_ads_too(tmp_path, monkeypatch):
    calls, sent, state = _run(tmp_path, 100, 60, monkeypatch, paused=True)
    assert state["reason"] == "the system is paused (/pause)" and any(u.endswith("campaigns:mutate") for _m, u, _b in calls)


def test_the_monthly_cap_pauses_and_no_customer_id_does_nothing(tmp_path, monkeypatch):
    assert ads.decide(CFG, 100, 6000, 50, False).startswith("this month's spend reached")
    assert ads.run(tmp_path, NOW, {}, notify=lambda m: None, cfg={}) == 0


def test_check_lists_the_reachable_accounts():
    sent = []
    call = lambda m, url, tok, json_body=None, data=None, headers=None: (200, {}, {"resourceNames": ["customers/1234567890"]})
    assert ads.check({}, notify=sent.append, call=call, token="t") == 0
    assert "step 4 works" in sent[0] and "123-456-7890" in sent[0]


def test_check_says_when_step_4_is_missing(monkeypatch):
    sent = []
    def missing(env=None, post=None):
        raise ads.secrets.MissingSecret("ADS_REFRESH_TOKEN")
    monkeypatch.setattr(ads, "access_token", missing)
    assert ads.check({}, notify=sent.append) == 1 and "not saved in GitHub yet" in sent[0]


def test_google_errors_read_as_field_and_message():
    body = {"error": {"details": [{"errors": [{"errorCode": {"fieldError": "REQUIRED"}, "message": "The required field was not present.",
                                               "location": {"fieldPathElements": [{"fieldName": "mutate_operations", "index": 3},
                                                                                  {"fieldName": "campaign_operation"}]}}]}]}}
    assert ads.errors_text(body) == 'mutate_operations[3].campaign_operation: The required field was not present. {"fieldError": "REQUIRED"}'
