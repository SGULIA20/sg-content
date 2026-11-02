

def test_check_reports_missing_permission_and_counts_asks(monkeypatch):
    from engine import commentdm
    now = "2026-11-02T07:00:00+0000"
    def call(method, path, token, params=None):
        if path == "/me": return {"id": "u", "username": "sanjeev_gulia"}
        if path == "/debug_token": return {"data": {"scopes": ["instagram_business_basic", "instagram_business_manage_comments"]}}
        if path.endswith("/media"): return {"data": [{"id": "m1", "timestamp": now}]}
        return {"data": [{"id": "c1", "text": "app link pls", "from": {"id": "x"}}, {"id": "c2", "text": "nice", "from": {"id": "y"}}]}
    sent = []
    import datetime as dt
    class FakeDT(dt.datetime):
        @classmethod
        def now(cls, tz=None): return dt.datetime(2026, 11, 2, 8, tzinfo=dt.timezone.utc)
    monkeypatch.setattr(commentdm, "datetime", FakeDT)
    rc = commentdm.check({"IG_ACCESS_TOKEN": "t", "IG_USER_ID": "u"}, call=call, notify=sent.append)
    assert rc == 1 and "missing: instagram_business_manage_messages" in sent[0] and "2 comments" in sent[0] and "1 asked" in sent[0]
