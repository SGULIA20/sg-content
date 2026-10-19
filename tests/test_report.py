from engine import report

TARGETS = {"sglearning": {"subs": 500, "best_short": 100000, "long_avg_views": 3000}, "arthvan": {"subs": 1000, "best_short": 300000, "long_avg_views": 10000}}


def _data():
    return {"sglearning": {"views": 1200, "minutes": 340, "subs_gained": 12, "avg_view_pct": 38.0, "shorts_avg_views": 150, "best_short": 900, "long_avg_views": 400,
                           "ig": {"reach": 800, "plays": 1500, "followers": 17700}, "top_comments": ["Bahut sahi", "Oil ka kya hoga?"]},
            "arthvan": {"views": 5000, "minutes": 1500, "subs_gained": 80, "avg_view_pct": 44.0, "shorts_avg_views": 2200, "best_short": 9000, "long_avg_views": 3000,
                        "ig": {}, "top_comments": []}}


def test_text_marks_short_average_under_200_as_hook_change_needed():
    t = report.text(_data(), TARGETS)
    assert "sglearning" in t and "hook" in t.lower() and "change the hook" in t.lower()
    assert "arthvan" in t and t.count("change the hook") == 1


def test_targets_progress_percent():
    t = report.text(_data(), TARGETS)
    assert "subs +12 (2% of 500)" in t and "subs +80 (8% of 1,000)" in t
    assert "best Short 9,000 (3% of 300,000)" in t


def test_youtube_week_parses_analytics_rows():
    rows = {"columnHeaders": [{"name": "video"}, {"name": "views"}, {"name": "estimatedMinutesWatched"}, {"name": "subscribersGained"}, {"name": "averageViewPercentage"}],
            "rows": [["a", 100, 20, 1, 40.0], ["b", 300, 90, 5, 36.0]]}
    out = report.youtube_week(rows, shorts={"a"}, longs={"b"})
    assert out["views"] == 400 and out["minutes"] == 110 and out["subs_gained"] == 6
    assert out["shorts_avg_views"] == 100 and out["long_avg_views"] == 300 and out["best_short"] == 100
    assert out["avg_view_pct"] == 37.0
