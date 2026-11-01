from datetime import datetime, timezone

from engine import yppstatus

NOW = datetime(2026, 11, 1, 10, 0, tzinfo=timezone.utc)


def _call(method, url, tok, json_body=None, data=None, headers=None):
    if "/channels?" in url:
        return 200, {}, {"items": [{"snippet": {"title": "SG-MYTH-WORLD"}, "statistics": {"subscriberCount": "212"}}]}
    q = url.split("?", 1)[1]
    if "insightTrafficSourceType" in q:
        return 200, {}, {"rows": [["VIDEO_ON_DEMAND", "ADVERTISING", 600], ["VIDEO_ON_DEMAND", "YT_SEARCH", 900], ["SHORTS", "ADVERTISING", 50]]}
    if "subscribersGained" in q:
        return 200, {}, {"rows": [[9]]}
    if "views" in q:
        return 200, {}, {"rows": [["SHORTS", 45000], ["VIDEO_ON_DEMAND", 900]]}
    if "2026-10-25" in q:                                        # last 7 days
        return 200, {}, {"rows": [["VIDEO_ON_DEMAND", 540], ["SHORTS", 300]]}
    return 200, {}, {"rows": [["VIDEO_ON_DEMAND", 30600], ["SHORTS", 9000]]}


def test_status_leaves_out_ad_watch_time_and_shorts():
    s = yppstatus.status("t", NOW.date(), _call)
    assert s["subs"] == 212 and s["hours"] == round((30600 - 600) / 60, 1) and s["ad_hours"] == 10.0
    assert s["shorts_90d"] == 45000 and s["week_hours"] == 9.0 and s["week_subs"] == 9


def test_one_channel_error_does_not_hide_the_other():
    sent = []
    def tok(channel, env):
        if channel == "sglearning":
            raise RuntimeError("token refresh failed")
        return "t"
    assert yppstatus.run({}, notify=sent.append, call=_call, token_for=tok, now=NOW) == 0
    assert "could not read" in sent[0] and "SG-MYTH-WORLD: 212 subscribers" in sent[0] and "500.0 public long-video watch hours" in sent[0]
