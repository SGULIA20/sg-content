from datetime import date, datetime, timezone

from engine import newscard, pieces, publish, topics


def test_company_results_and_rate_tables_fall_behind_for_news_only():
    jio = {"title": "Jio Platforms Q2 net profit rises 14% to Rs 8,387 crore", "summary": "", "rank": 0}
    why = {"title": "Why Google shares and Bitcoin crashed together", "summary": "", "rank": 0}
    rates = {"title": "Weighted average lending rate on fresh loans falls to 8.51%", "summary": "", "rank": 0}
    assert topics.news_score(jio) == topics.score(jio) - 4 and topics.news_score(rates) == topics.score(rates) - 4
    assert topics.news_score(why) == topics.score(why)
    assert topics.news_score(why) > topics.news_score(jio)


def test_first_card_carries_the_spoken_question():
    sc = {"vo": "Google aur Bitcoin dono ek saath kyun gire? Wajah aapke SIP se judi hai.", "visual": {"type": "card", "card": {"big_number": "", "line": "dono gire"}}}
    d = newscard.data(sc, 0, 8, "tech", False)
    assert d["line"].startswith("Google aur Bitcoin dono ek saath kyun gire?")
    d2 = newscard.data({**sc, "vo": "Dusri baat."}, 1, 8, "tech", False)
    assert d2["line"] == "dono gire"


def _piece(root, pid, slot):
    p = pieces.Piece(id=pid, channel="sglearning", kind="short", publish_day=date(2026, 11, 1), status="uploaded")
    p.topic = {"preset": {"extra": True, "slot_ist": slot}, "slot_ist": slot}
    p.ids = {"yt_id": "y" + pid[-1]}
    p.script = {"captions": {"threads": {"text": "t"}}}
    pieces.save(p, root)


def test_only_one_new_reel_per_run(tmp_path, monkeypatch):
    (tmp_path / "pieces").mkdir()
    _piece(tmp_path, "2026-11-01-sglearning-x1", "09:30")
    _piece(tmp_path, "2026-11-01-sglearning-x2", "13:00")
    monkeypatch.setattr(publish.telegram, "paused", lambda root: False)
    posted = []
    def ig(piece, env, **kw):
        posted.append(piece.id); piece.ids["ig_reel_id"] = "r" + piece.id[-1]; piece.ids["ig_story_id"] = "s"; return piece
    now = datetime(2026, 11, 1, 7, 37, tzinfo=timezone.utc)                  # 13:07 India
    publish.run(tmp_path, "sglearning", now, env={}, ig_publish=ig, threads_post=lambda *a, **k: "t", linkedin_post=lambda *a, **k: "l",
                notify=lambda t: None)
    assert len(posted) == 1
