from engine import ytdescribe


def test_describe_lists_title_and_description_and_survives_an_error():
    ok = lambda *a, **k: (200, {}, {"items": [{"id": "a", "snippet": {"title": "t", "description": "d"}, "contentDetails": {"duration": "PT50S"}, "status": {"publishAt": "2026-12-02T14:30:00Z"}}]})
    assert ytdescribe.describe("t", ["a"], ok) == [{"id": "a", "title": "t", "duration": "PT50S", "publishAt": "2026-12-02T14:30:00Z", "description": "d"}]
    assert ytdescribe.describe("t", ["a"], lambda *a, **k: (403, {}, {}))[0]["error"] == 403
