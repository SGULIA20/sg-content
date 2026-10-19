from datetime import date, datetime, timezone

from engine import pieces, publish, telegram

ENV = {"IG_ACCESS_TOKEN": "t", "IG_USER_ID": "u", "THREADS_ACCESS_TOKEN": "tt", "THREADS_USER_ID": "tu", "GITHUB_REPOSITORY": "r"}
NOW = datetime(2026, 10, 20, 7, 30, tzinfo=timezone.utc)          # 13:00 IST on 20 Oct


def _seed(root, pid, ch, kind, day, status="uploaded", ids=None, carousel=False):
    p = pieces.Piece(id=pid, channel=ch, kind=kind, publish_day=day)
    p.status = status
    p.ids = {"out_sha": "sha1", "yt_id": "y", **(ids or {})}
    p.script = {"hook": "h", "scenes": [], "cards": [], "carousel": carousel,
                "captions": {"instagram": {"caption": "c Yeh investment advice nahi hai", "hashtags": ["#A", "#B", "#C", "#D", "#E"]},
                             "threads": {"text": "t", "hashtags": ["#A", "#B"]}}}
    pieces.save(p, root)
    return p


def test_due_only_today_uploaded_shorts_missing_ids(tmp_path):
    _seed(tmp_path, "2026-10-20-sglearning-short", "sglearning", "short", date(2026, 10, 20))
    _seed(tmp_path, "2026-10-21-sglearning-short", "sglearning", "short", date(2026, 10, 21))
    _seed(tmp_path, "2026-10-20-arthvan-short", "arthvan", "short", date(2026, 10, 20))
    _seed(tmp_path, "2026-10-25-sglearning-long", "sglearning", "long", date(2026, 10, 25))
    _seed(tmp_path, "2026-10-19-sglearning-short", "sglearning", "short", date(2026, 10, 19), status="posted")
    due = publish.due(tmp_path, NOW, "sglearning")
    assert [p.id for p in due] == ["2026-10-20-sglearning-short"]


def test_due_respects_app_job_window(tmp_path):
    _seed(tmp_path, "2026-10-20-sglearning-short", "sglearning", "short", date(2026, 10, 20))
    at_2030_ist = datetime(2026, 10, 20, 15, 0, tzinfo=timezone.utc)
    assert publish.due(tmp_path, at_2030_ist, "sglearning") == []


def test_pause_flag_skips_everything(tmp_path):
    _seed(tmp_path, "2026-10-20-sglearning-short", "sglearning", "short", date(2026, 10, 20))
    telegram.set_paused(True, tmp_path)
    posted = []
    code = publish.run(tmp_path, "sglearning", NOW, ENV, ig_publish=lambda p, env: posted.append(p) or p, threads_post=lambda *a, **k: "x", notify=lambda t: True)
    assert code == 0 and posted == []


def test_posted_when_all_ids_present(tmp_path):
    p = _seed(tmp_path, "2026-10-20-sglearning-short", "sglearning", "short", date(2026, 10, 20))

    def ig_publish(piece, env):
        piece.ids.update({"ig_reel_id": "r1", "ig_story_id": "s1"}); return piece

    sent = []
    code = publish.run(tmp_path, "sglearning", NOW, ENV, ig_publish=ig_publish, threads_post=lambda uid, tok, url, text: "th1", notify=lambda t: sent.append(t) or True)
    q = pieces.load(p.id, tmp_path)
    assert code == 0 and q.status == "posted" and q.ids["threads_id"] == "th1"
    assert sent and "posted 1" in sent[0]


def test_threads_failure_leaves_piece_uploaded_with_reason(tmp_path):
    p = _seed(tmp_path, "2026-10-20-sglearning-short", "sglearning", "short", date(2026, 10, 20))

    def ig_publish(piece, env):
        piece.ids.update({"ig_reel_id": "r1", "ig_story_id": "s1"}); pieces.save(piece, tmp_path); return piece

    def threads_post(*a, **k):
        from engine.threads import ThreadsError
        raise ThreadsError("boom")

    code = publish.run(tmp_path, "sglearning", NOW, ENV, ig_publish=ig_publish, threads_post=threads_post, notify=lambda t: True)
    q = pieces.load(p.id, tmp_path)
    assert code == 0 and q.status == "uploaded" and q.ids["ig_reel_id"] == "r1" and "threads" in q.reasons[-1].lower()


def test_threads_text_uses_caption_builder(tmp_path):
    p = _seed(tmp_path, "2026-10-20-sglearning-short", "sglearning", "short", date(2026, 10, 20))
    assert publish.threads_text(p) == "t\n\n#A #B"
