from datetime import date

from engine import ytwatch


def test_report_splits_long_and_shorts_and_never_raises_on_an_error():
    def call(method, url, token):
        if "dimensions=day%2CcreatorContentType" in url:
            return 200, {}, {"rows": [["2026-11-01", "shorts", 100, 120, 1], ["2026-11-01", "videoOnDemand", 10, 60, 0]]}
        if "insightTrafficSourceType" in url:
            return 200, {}, {"rows": [["ADVERTISING", 8, 40]]}
        return 200, {}, {"rows": [["vid1", 10, 60, 360]]}
    s = ytwatch.summarize("t", date(2026, 11, 1), date(2026, 11, 1), call)
    text = "\n".join(ytwatch.report("x", s))
    assert "TOTAL long-form: 10 views, 1.0 h | Shorts: 100 views, 2.0 h" in text and "ADVERTISING 8/0.7" in text
    bad = ytwatch.summarize("t", date(2026, 11, 1), date(2026, 11, 1), lambda *a, **k: (400, {}, {"error": "no"}))
    assert "error" in "\n".join(ytwatch.report("x", bad))
