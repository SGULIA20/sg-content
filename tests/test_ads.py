import json
from datetime import datetime, timezone

from engine import ads

NOW = datetime(2026, 11, 3, 19, 30, tzinfo=timezone.utc)
CFG = {"customer_id": "123-456-7890", "test_start": "2026-11-01", "baseline_subs_per_day": 0.5,
       "limits": {"INR": {"monthly_cap": 6000, "budget_per_channel": 2000, "min_spend": 1500, "max_cost_per_sub": 25},
                  "USD": {"monthly_cap": 42, "budget_per_channel": 21, "min_spend": 18, "max_cost_per_sub": 0.30}}}


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
    assert state["subs_above_usual"] == 118 and state["cost_per_sub"] == 13.56
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
    assert ads.decide(CFG, 10, 42, 50, False, "USD") == "this month's spend reached the $42 cap"
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


def test_pause_all_pauses_every_running_campaign():
    calls, sent = [], []
    def call(method, url, tok, json_body=None, headers=None):
        calls.append((url, json_body))
        if url.endswith(":search"):
            return 200, {}, {"results": [{"campaign": {"id": "1", "name": "A", "status": "ENABLED"}},
                                         {"campaign": {"id": "2", "name": "B", "status": "ENABLED"}}]}
        return 200, {}, {}
    assert ads.pause_all({"customer_id": "601-481-4549"}, {}, notify=sent.append, call=call, token="t") == 0
    ops = calls[1][1]["operations"]
    assert [o["update"]["status"] for o in ops] == ["PAUSED", "PAUSED"] and "paused 2" in sent[0]


def test_an_account_in_a_currency_without_limits_is_paused_not_watched(tmp_path, monkeypatch):
    calls, sent = [], []
    def call(method, url, token, json_body=None, data=None, headers=None):
        calls.append((url, json_body))
        if url.endswith(":search") and "currency_code" in json_body["query"]:
            return 200, {}, {"results": [{"customer": {"currencyCode": "EUR"}}]}
        if url.endswith(":search"):
            return 200, {}, {"results": [{"campaign": {"id": "9", "status": "ENABLED"}}]}
        return 200, {}, {}
    monkeypatch.setattr(ads.telegram, "paused", lambda root: False)
    assert ads.run(tmp_path, NOW, {}, notify=sent.append, cfg=CFG, call=call, token="t", subs=lambda ch: 0) == 1
    assert any(u.endswith("campaigns:mutate") for u, _b in calls) and "paused 1" in sent[0]


def test_errors_text_keeps_googles_details():
    from engine import ads
    body = {"error": {"details": [{"errors": [{"message": "below minimum", "errorCode": {"campaignBudgetError": "BUDGET_BELOW_PER_DAY_MINIMUM"},
                                               "details": {"budgetPerDayMinimumErrorDetails": {"minimumBudgetAmountMicros": "5000000"}}}]}]}}
    assert "5000000" in ads.errors_text(body)


def test_status_reports_approvals_and_flags_a_disapproved_ad():
    from engine import ads
    seen = []
    def call(method, url, tok, json_body=None, headers=None):
        q = json_body["query"]
        seen.append(q)
        if "FROM customer" in q:
            return 200, {}, {"results": [{"customer": {"status": "ENABLED", "currencyCode": "USD"}}]}
        if "FROM billing_setup" in q:
            return 200, {}, {"results": [{"billingSetup": {"status": "APPROVED"}}]}
        return 200, {}, {"results": [
            {"campaign": {"name": "SG test A", "status": "ENABLED", "primaryStatus": "ELIGIBLE"},
             "adGroupAd": {"policySummary": {"approvalStatus": "APPROVED", "reviewStatus": "REVIEWED"}}},
            {"campaign": {"name": "SG test B", "status": "ENABLED", "primaryStatus": "NOT_ELIGIBLE", "primaryStatusReasons": ["AD_GROUP_AD_DISAPPROVED"]},
             "adGroupAd": {"policySummary": {"approvalStatus": "DISAPPROVED", "reviewStatus": "REVIEWED",
                                             "policyTopicEntries": [{"topic": "MISLEADING", "type": "PROHIBITED"}]}}}]}
    sent = []
    assert ads.status({"customer_id": "601-481-4549"}, {}, notify=sent.append, call=call, token="t") == 0
    assert sent[0].startswith("⚠️") and "SG test A: campaign ENABLED, serving ELIGIBLE; ad APPROVED" in sent[0]
    assert "MISLEADING (PROHIBITED)" in sent[0] and "billing: APPROVED" in sent[0]
    assert not any("mutate" in q for q in seen)
