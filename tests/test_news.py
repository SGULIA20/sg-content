from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from engine import news, pieces, pipeline, slots

NOW = datetime(2026, 11, 2, 8, 0, tzinfo=timezone.utc)                       # 09:00 WAT, Monday 2 Nov
TODAY = date(2026, 11, 2)
ITEM = {"title": "Gold price jumps Rs 1,200 after Fed holds rates", "summary": "gold price", "link": "https://x/gold",
        "published": NOW - timedelta(hours=3), "rank": 1}


def _evergreen(root, day=TODAY):
    p = pieces.Piece(id=slots.piece_id(day, "sglearning", "short"), channel="sglearning", kind="short", publish_day=day, status="uploaded")
    p.ids = {"yt_id": "EVER", "out_sha": "abc"}
    p.topic = {"title": "SIP fees"}
    (Path(root) / "out" / p.id).mkdir(parents=True); (Path(root) / "out" / p.id / "reel.mp4").write_bytes(b"e")
    pieces.save(p, root)
    return p


class D:
    def __init__(self, fail_upload=False):
        self.uploaded, self.fail = [], fail_upload
    def upload(self, piece, video, thumb):
        if self.fail:
            raise RuntimeError("quota")
        self.uploaded.append((piece.id, piece.publish_day)); return "NEWS"


def _fake_make(monkeypatch, status="assembled"):
    def make(piece, deps, root, dry_run=False):
        assert dry_run and piece.id.endswith("-news") and deps.topic(piece, set())["link"] == "https://x/gold"
        out = Path(root) / "out" / piece.id; out.mkdir(parents=True, exist_ok=True)
        (out / "reel.mp4").write_bytes(b"n"); (out / "thumb.jpg").write_bytes(b"t")
        piece.topic = {"title": ITEM["title"]}; piece.status = status
        pieces.save(piece, root); return piece
    monkeypatch.setattr(pipeline, "make", make)


def _run(tmp_path, d, moves, **kw):
    return news.run(tmp_path, NOW, deps=d, notify=lambda t: moves.append(("tg", t)), items=[ITEM], token_for=lambda ch, env: "tok",
                    reschedule=lambda tok, vid, when: moves.append((vid, when)) or True, **kw)


def test_the_news_short_takes_todays_slot_and_the_planned_one_moves_to_the_first_free_day(tmp_path, monkeypatch):
    _evergreen(tmp_path)
    for i in range(1, 8):
        _evergreen(tmp_path, TODAY + timedelta(days=i)) if i < 7 else None          # the buffer runs to 8 Nov; 9 Nov is free
    _fake_make(monkeypatch)
    d, moves = D(), []
    assert _run(tmp_path, d, moves) == 0
    today = pieces.load("2026-11-02-sglearning-short", tmp_path)
    assert today.topic["news"] and today.ids["yt_id"] == "NEWS" and today.status == "uploaded" and d.uploaded == [("2026-11-02-sglearning-news", TODAY)]
    moved = pieces.load("2026-11-09-sglearning-short", tmp_path)
    assert moved.ids["yt_id"] == "EVER" and "out_sha" not in moved.ids and (tmp_path / "out" / moved.id / "reel.mp4").read_bytes() == b"e"
    assert ("EVER", slots.publish_at("sglearning", "short", date(2026, 11, 9))) in moves
    assert not (tmp_path / "pieces" / "2026-11-02-sglearning-news.json").exists() and (tmp_path / "out" / "2026-11-02-sglearning-short" / "reel.mp4").read_bytes() == b"n"


def test_a_failed_news_short_leaves_today_as_planned(tmp_path, monkeypatch):
    _evergreen(tmp_path)
    _fake_make(monkeypatch, status="rejected")
    moves = []
    assert _run(tmp_path, D(), moves) == 0
    assert pieces.load("2026-11-02-sglearning-short", tmp_path).ids["yt_id"] == "EVER" and not [m for m in moves if m[0] != "tg"]


def test_a_failed_upload_puts_the_planned_short_back(tmp_path, monkeypatch):
    _evergreen(tmp_path)
    _fake_make(monkeypatch)
    moves = []
    assert _run(tmp_path, D(fail_upload=True), moves) == 1
    back = pieces.load("2026-11-02-sglearning-short", tmp_path)
    assert back.ids["yt_id"] == "EVER" and moves[-2] == ("EVER", slots.publish_at("sglearning", "short", TODAY))


def test_nothing_happens_after_the_deadline_or_once_posted(tmp_path, monkeypatch):
    p = _evergreen(tmp_path)
    monkeypatch.setattr(pipeline, "make", lambda *a, **k: (_ for _ in ()).throw(AssertionError("made")))
    assert news.run(tmp_path, NOW.replace(hour=12, minute=5), deps=D(), notify=lambda t: None, items=[ITEM]) == 0
    p.ids["ig_reel_id"] = "r"; pieces.save(p, tmp_path)
    assert news.run(tmp_path, NOW, deps=D(), notify=lambda t: None, items=[ITEM]) == 0


def test_the_buffer_skips_dated_headlines_and_the_news_pick_skips_market_calls():
    from engine import topics
    now = NOW
    dated = {"title": "Petrol price cut today, 22 Oct: Rs 2 a litre", "summary": "petrol price", "link": "a", "published": now, "rank": 1}   # 4 Nov 2026: results headlines are never Reels
    call = {"title": "Stock market outlook: Sensex prediction", "summary": "sensex price", "link": "b", "published": now, "rank": 1}
    plain = {"title": "Gold price crashes Rs 38,600 from record", "summary": "gold price", "link": "c", "published": now, "rank": 1}
    assert topics.pick_finance([dated, plain], set(), now)["link"] == "c"
    assert topics.pick_finance([dated], set(), now) is None
    assert topics.pick_finance([dated], set(), now, news=True)["link"] == "a"
    assert topics.pick_finance([call], set(), now, news=True) is None


def test_a_short_marked_keep_slot_is_never_swapped(tmp_path, monkeypatch):
    p = _evergreen(tmp_path); p.topic["keep_slot"] = "style test"; pieces.save(p, tmp_path)
    monkeypatch.setattr(pipeline, "make", lambda *a, **k: (_ for _ in ()).throw(AssertionError("made")))
    assert news.run(tmp_path, NOW, deps=D(), notify=lambda t: None, items=[ITEM]) == 0


def test_reverting_a_news_swap_puts_the_planned_short_back_and_parks_the_news_short(tmp_path, monkeypatch):
    """7 Nov 2026: the news Short had no founder intro; the planned Short goes back to today and the news Short is parked, never posted."""
    monkeypatch.setattr(news.gitsync, "safe_commit", lambda *a, **k: "")
    later = TODAY + timedelta(days=7)
    ev = _evergreen(tmp_path, later)
    ev.ids = {"yt_id": "EVER", "out_sha": "abc", "intro": {"ok": 1}}; pieces.save(ev, tmp_path)
    nw = pieces.Piece(id=slots.piece_id(TODAY, "sglearning", "short"), channel="sglearning", kind="short", publish_day=TODAY, status="uploaded")
    nw.ids = {"yt_id": "NEWS"}; nw.topic = {"news": True, "title": "Biyani"}
    (tmp_path / "out" / nw.id).mkdir(parents=True); (tmp_path / "out" / nw.id / "reel.mp4").write_bytes(b"n"); pieces.save(nw, tmp_path)
    moved, parked, said = [], [], []
    out = news.revert(TODAY, later, tmp_path, token_for=lambda ch, env=None: "tok", reschedule=lambda t, v, w: moved.append((v, w)) or True,
                      unschedule=lambda t, v: parked.append(v) or True, notify=said.append)
    assert moved == [("EVER", slots.publish_at("sglearning", "short", TODAY))] and parked == ["NEWS"] and "Reverted" in out and said
    back = pieces.load(slots.piece_id(TODAY, "sglearning", "short"), tmp_path)
    assert back.ids["yt_id"] == "EVER" and back.ids["intro"] and back.publish_day == TODAY and (tmp_path / "out" / back.id / "reel.mp4").read_bytes() == b"e"
    parked_piece = pieces.load(f"{TODAY.isoformat()}-sglearning-news", tmp_path)
    assert parked_piece.status == "rejected" and parked_piece.ids["yt_id"] == "NEWS" and (tmp_path / "out" / parked_piece.id / "reel.mp4").read_bytes() == b"n"
    assert pieces.load(slots.piece_id(later, "sglearning", "short"), tmp_path) is None


def test_a_revert_that_cannot_move_the_planned_short_changes_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(news.gitsync, "safe_commit", lambda *a, **k: "")
    later = TODAY + timedelta(days=7)
    _evergreen(tmp_path, later)
    nw = pieces.Piece(id=slots.piece_id(TODAY, "sglearning", "short"), channel="sglearning", kind="short", publish_day=TODAY, status="uploaded")
    nw.ids = {"yt_id": "NEWS"}; nw.topic = {"news": True}; pieces.save(nw, tmp_path)
    parked = []
    out = news.revert(TODAY, later, tmp_path, token_for=lambda ch, env=None: "tok", reschedule=lambda *a: False, unschedule=lambda t, v: parked.append(v) or True, notify=lambda m: None)
    assert "nothing changed" in out and not parked and pieces.load(slots.piece_id(TODAY, "sglearning", "short"), tmp_path).topic["news"]
    assert "not a news Short" in news.revert(date(2030, 1, 1), later, tmp_path, token_for=lambda *a, **k: "t")


def test_unschedule_sends_no_publish_time_and_keeps_the_video_private():
    from engine import youtube
    sent = []
    assert youtube.unschedule("t", "v", call=lambda m, u, t, json_body=None: sent.append(json_body) or (200, {}, {}))
    assert sent[0]["status"]["privacyStatus"] == "private" and "publishAt" not in sent[0]["status"] and sent[0]["id"] == "v"
