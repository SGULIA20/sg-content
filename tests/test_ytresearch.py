from datetime import datetime, timezone

from engine import ytresearch


def test_search_lists_the_most_viewed_with_length_and_survives_an_error():
    def call(method, url, token):
        if "/search?" in url:
            return 200, {}, {"items": [{"id": {"videoId": "a"}}, {"id": {"videoId": "b"}}]}
        return 200, {}, {"items": [
            {"id": "a", "snippet": {"title": "t1", "channelTitle": "c1", "publishedAt": "2026-11-01T00:00:00Z"}, "statistics": {"viewCount": "10"}, "contentDetails": {"duration": "PT59S"}},
            {"id": "b", "snippet": {"title": "t2", "channelTitle": "c2", "publishedAt": "2026-11-02T00:00:00Z"}, "statistics": {"viewCount": "500"}, "contentDetails": {"duration": "PT10M5S"}}]}
    got = ytresearch.search("t", "q", datetime(2026, 11, 1, tzinfo=timezone.utc), call)
    assert [r["id"] for r in got] == ["b", "a"] and got[0]["seconds"] == 605 and got[1]["seconds"] == 59
    assert ytresearch.search("t", "q", datetime(2026, 11, 1, tzinfo=timezone.utc), lambda *a, **k: (403, {}, {"error": "x"}))[0]["error"] == 403
