from engine import ytretitle

SNIP = {"title": "old", "description": "keep me", "categoryId": "27", "tags": ["a"], "channelId": "x", "publishedAt": "2026-11-01T00:00:00Z", "thumbnails": {}}


def test_check_changes_nothing_and_apply_writes_the_whole_snippet_with_only_the_title_changed():
    sent = []
    def call(method, url, token, json_body=None):
        if method == "GET":
            return 200, {}, {"items": [{"snippet": dict(SNIP)}]}
        sent.append(json_body); return 200, {}, {}
    assert "would change" in ytretitle.retitle("t", "v", "new", False, call) and not sent
    assert "changed to" in ytretitle.retitle("t", "v", "new", True, call)
    s = sent[0]["snippet"]
    assert s["title"] == "new" and s["description"] == "keep me" and s["categoryId"] == "27" and s["tags"] == ["a"] and "thumbnails" not in s and "publishedAt" not in s
    assert "already" in ytretitle.retitle("t", "v", "old", True, call) and len(sent) == 1


def test_a_failure_is_reported_and_the_shipped_plan_has_seven_distinct_titles():
    import json
    bad = lambda *a, **k: (403, {}, {})
    assert "cannot read" in ytretitle.retitle("t", "v", "new", True, bad)
    plan = json.loads(ytretitle.PLAN.read_text(encoding="utf-8"))
    titles = list(plan["titles"].values())
    assert len(titles) == 7 and len(set(titles)) == 7 and all(t.endswith("#Shorts") and len(t) <= 100 for t in titles)
