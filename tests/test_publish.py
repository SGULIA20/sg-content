from datetime import date, datetime, timezone

import pytest

from engine import pieces, publish, secrets, telegram

ENV = {"IG_ACCESS_TOKEN": "t", "IG_USER_ID": "u", "THREADS_ACCESS_TOKEN": "tt", "THREADS_USER_ID": "tu", "GITHUB_REPOSITORY": "r"}
NOW = datetime(2026, 10, 20, 7, 30, tzinfo=timezone.utc)          # 13:00 IST on 20 Oct
LI_ENV = {**ENV, "LINKEDIN_ACCESS_TOKEN": "litok1", "LINKEDIN_PERSON_URN": "urn:li:person:p1"}


@pytest.fixture(autouse=True)
def _no_dotenv(tmp_path, monkeypatch):
    """A local .env with LinkedIn values must not switch LinkedIn on in these tests."""
    monkeypatch.setattr(secrets, "DOTENV", tmp_path / "no.env")


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


def test_due_retries_recent_days_with_missing_ids(tmp_path):
    _seed(tmp_path, "2026-10-18-sglearning-short", "sglearning", "short", date(2026, 10, 18), ids={"ig_reel_id": "r"})
    _seed(tmp_path, "2026-10-10-sglearning-short", "sglearning", "short", date(2026, 10, 10))
    assert [p.id for p in publish.due(tmp_path, NOW, "sglearning")] == ["2026-10-18-sglearning-short"]


def test_due_skips_unlisted_day1_pieces(tmp_path):
    _seed(tmp_path, "2026-10-20-sglearning-short", "sglearning", "short", date(2026, 10, 20), ids={"unlisted": True})
    assert publish.due(tmp_path, NOW, "sglearning") == []


def _ig_ok(root):
    def ig_publish(piece, env):
        if not piece.ids.get("ig_reel_id"):
            piece.ids.update({"ig_reel_id": "r1", "ig_story_id": "s1"}); pieces.save(piece, root)
        ig_publish.n += 1
        return piece
    ig_publish.n = 0
    return ig_publish


def test_linkedin_skipped_when_unconfigured(tmp_path):
    p = _seed(tmp_path, "2026-10-20-sglearning-short", "sglearning", "short", date(2026, 10, 20))
    li = []
    publish.run(tmp_path, "sglearning", NOW, ENV, ig_publish=_ig_ok(tmp_path), threads_post=lambda *a: "th1",
                linkedin_post=lambda *a: li.append(a) or "x", notify=lambda t: True)
    q = pieces.load(p.id, tmp_path)
    assert li == [] and q.status == "posted" and "linkedin_id" not in q.ids


def test_linkedin_posts_reel_file_with_text(tmp_path):
    p = _seed(tmp_path, "2026-10-20-sglearning-short", "sglearning", "short", date(2026, 10, 20))
    li = []
    publish.run(tmp_path, "sglearning", NOW, LI_ENV, ig_publish=_ig_ok(tmp_path), threads_post=lambda *a: "th1",
                linkedin_post=lambda *a: li.append(a) or "urn:li:share:9", notify=lambda t: True)
    q = pieces.load(p.id, tmp_path)
    assert q.status == "posted" and q.ids["linkedin_id"] == "urn:li:share:9"
    urn, tok, path, text, title = li[0]
    assert urn == "urn:li:person:p1" and tok == "litok1" and str(path).endswith(f"out/{p.id}/reel.mp4")
    assert "youtu.be/y" in text and title == p.id                       # the seed has no YouTube title, so the piece id stands in


def test_linkedin_failure_recorded_then_retried_without_reposting(tmp_path):
    p = _seed(tmp_path, "2026-10-20-sglearning-short", "sglearning", "short", date(2026, 10, 20))
    ig, th = _ig_ok(tmp_path), []

    def bad(*a):
        from engine.linkedin import LinkedInError
        raise LinkedInError("HTTP 500: nope")

    publish.run(tmp_path, "sglearning", NOW, LI_ENV, ig_publish=ig, threads_post=lambda *a: th.append(a) or "th1", linkedin_post=bad, notify=lambda t: True)
    q = pieces.load(p.id, tmp_path)
    assert q.status == "uploaded" and q.ids["threads_id"] == "th1" and "linkedin" in q.reasons[-1] and "linkedin_id" not in q.ids
    assert [x.id for x in publish.due(tmp_path, NOW, "sglearning", LI_ENV)] == [p.id]
    assert publish.due(tmp_path, NOW, "sglearning", ENV) == []                 # without LinkedIn configured nothing is missing
    li = []
    publish.run(tmp_path, "sglearning", NOW, LI_ENV, ig_publish=ig, threads_post=lambda *a: th.append(a) or "th2",
                linkedin_post=lambda *a: li.append(a) or "urn:li:share:9", notify=lambda t: True)
    q = pieces.load(p.id, tmp_path)
    assert q.status == "posted" and q.ids["linkedin_id"] == "urn:li:share:9" and len(li) == 1
    assert len(th) == 1 and q.ids["threads_id"] == "th1" and q.ids["ig_reel_id"] == "r1"     # Threads not posted again; Instagram ids untouched


def test_existing_linkedin_id_is_never_posted_again(tmp_path):
    p = _seed(tmp_path, "2026-10-20-sglearning-short", "sglearning", "short", date(2026, 10, 20),
              ids={"linkedin_id": "urn:li:share:1"})
    li = []
    publish.run(tmp_path, "sglearning", NOW, LI_ENV, ig_publish=_ig_ok(tmp_path), threads_post=lambda *a: "th1",
                linkedin_post=lambda *a: li.append(a) or "x", notify=lambda t: True)
    q = pieces.load(p.id, tmp_path)
    assert li == [] and q.status == "posted" and q.ids["linkedin_id"] == "urn:li:share:1"
    publish.run(tmp_path, "sglearning", NOW, LI_ENV, ig_publish=_ig_ok(tmp_path), threads_post=lambda *a: "th1",
                linkedin_post=lambda *a: li.append(a) or "x", notify=lambda t: True)
    assert li == []


def test_instagram_failure_still_posts_threads(tmp_path):
    """21 Oct 2026: the Story failed and the loop skipped Threads, so neither went out."""
    p = _seed(tmp_path, "2026-10-20-sglearning-short", "sglearning", "short", date(2026, 10, 20))

    def ig_publish(piece, env):
        from engine.instagram import PartialPublish
        piece.ids["ig_reel_id"] = "r1"; pieces.save(piece, tmp_path)
        raise PartialPublish("story container failed with status ERROR (already live: ['reel'])")

    th = []
    code = publish.run(tmp_path, "sglearning", NOW, ENV, ig_publish=ig_publish, threads_post=lambda *a: th.append(a) or "th1", notify=lambda t: True)
    q = pieces.load(p.id, tmp_path)
    assert code == 0 and th and q.ids["threads_id"] == "th1" and q.ids["ig_reel_id"] == "r1"
    assert q.status == "uploaded"                                    # the Story is still missing: the next run retries it


def test_a_posted_short_is_due_again_when_a_newly_configured_platform_is_missing(tmp_path):
    from datetime import datetime, timezone
    (tmp_path / "pieces").mkdir()
    p = pieces.Piece(id="2026-10-22-sglearning-short", channel="sglearning", kind="short", publish_day=date(2026, 10, 22))
    p.status = "posted"; p.ids = {"yt_id": "y", "ig_reel_id": "r", "ig_story_id": "s", "threads_id": "t", "out_sha": "abc"}
    pieces.save(p, tmp_path)
    now = datetime(2026, 10, 22, 9, 30, tzinfo=timezone.utc)
    assert publish.due(tmp_path, now, "sglearning", {}) == []                                           # nothing owed without LinkedIn keys
    env = {"LINKEDIN_ACCESS_TOKEN": "t", "LINKEDIN_PERSON_URN": "urn:li:person:x"}
    assert [q.id for q in publish.due(tmp_path, now, "sglearning", env)] == [p.id]                        # LinkedIn owed once its keys exist
