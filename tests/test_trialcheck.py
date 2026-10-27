from datetime import date, datetime, timezone

from engine import evening, pieces, secrets, trialcheck

NOW = datetime(2026, 10, 27, 20, 5, tzinfo=timezone.utc)


def _piece(root, day, trial="SS_PERFORMANCE", reel="r1"):
    p = pieces.Piece(id=f"2026-10-{day:02d}-sglearning-short", channel="sglearning", kind="short", publish_day=date(2026, 10, day),
                     status="posted", ids={"ig_reel_id": reel, "ig_trial": trial})
    pieces.save(p, root)


def _call(stamps):
    def call(method, path, token, params=None):
        return {"timestamp": stamps[path.strip("/")], "permalink": f"https://instagram.com/reel/{path.strip('/')}",
                "like_count": 12, "comments_count": 3, "is_shared_to_feed": path.strip("/") != "due"}
    return call


def test_lists_only_trial_reels_whose_72_hours_ended_in_the_last_day(tmp_path):
    _piece(tmp_path, 24, reel="due")                     # posted 24 Oct 08:35 UTC: 83.5 h ago, listed
    _piece(tmp_path, 25, reel="young")                   # 59.5 h ago: still in its 72 hours
    _piece(tmp_path, 23, reel="old")                     # 107.5 h ago: listed yesterday
    _piece(tmp_path, 26, trial="no: refused", reel="plain")
    stamps = {"due": "2026-10-24T08:35:00+0000", "young": "2026-10-25T08:35:00+0000", "old": "2026-10-23T08:35:00+0000"}
    out = trialcheck.lines(NOW, tmp_path, {"IG_ACCESS_TOKEN": "t"}, call=_call(stamps),
                           numbers=lambda mid, tok: {"views": 1234, "shares": 4, "saved": 2})
    text = "\n".join(out)
    assert "Learning with SG 24 Oct: 👉 NOT shared" in text and "1,234 views, 12 likes, 3 comments, 4 shares, 2 saves" in text
    assert "reel/due" in text and "young" not in text and "old" not in text and "plain" not in text
    assert "👉 NOT shared: open it and tap Share to followers" in text


def test_nothing_due_or_no_token_means_no_lines(tmp_path, monkeypatch):
    monkeypatch.setattr(secrets, "DOTENV", tmp_path / "no.env")
    monkeypatch.delenv("IG_ACCESS_TOKEN", raising=False)
    _piece(tmp_path, 26, reel="young")
    assert trialcheck.lines(NOW, tmp_path, {"IG_ACCESS_TOKEN": "t"}, call=_call({"young": "2026-10-26T08:35:00+0000"})) == []
    assert trialcheck.lines(NOW, tmp_path, {}) == []


def test_card_carries_the_trial_lines_at_the_end(tmp_path):
    text = evening.build(date(2026, 10, 27), NOW, tmp_path, log=[], trials=["🧪 Trial Reels, 72 hours over", "   x"])
    assert text.endswith("🧪 Trial Reels, 72 hours over\n   x")
    assert "Trial" not in evening.build(date(2026, 10, 27), NOW, tmp_path, log=[])


def test_app_trial_reels_from_the_app_log_are_listed_too(tmp_path):
    log = [{"date": "2026-10-24", "app": "waypoint", "status": "published", "reel_trial": "SS_PERFORMANCE", "ids": {"reel": "app1"}},
           {"date": "2026-10-24", "app": "scoremybiz", "status": "published", "ids": {"reel": "plainapp"}},
           {"date": "2026-10-24", "app": "scoremybiz", "status": "publishing", "reel_trial": "SS_PERFORMANCE"}]
    out = trialcheck.lines(NOW, tmp_path, {"IG_ACCESS_TOKEN": "t"}, call=_call({"app1": "2026-10-24T14:44:00+0000"}),
                           numbers=lambda mid, tok: {"views": 50}, app_log=log)
    text = "\n".join(out)
    assert "Waypoint 24 Oct: ✅ shared with followers" in text and "50 views" in text and "plainapp" not in text
