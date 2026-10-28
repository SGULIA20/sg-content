import json
from datetime import date

import pytest

from engine import instagram, pieces

DISCLAIMER = "Yeh investment advice nahi hai"


def _piece(carousel=False):
    p = pieces.Piece(id="2026-10-20-sglearning-short", channel="sglearning", kind="short", publish_day=date(2026, 10, 20))
    p.script = {"hook": "h", "scenes": [], "cards": [{"big_number": "88%", "line": "x", "source": "PPAC"}] * 3,
                "captions": {"instagram": {"caption": f"Oil 100. {DISCLAIMER}", "hashtags": ["#PaiseKiKhabar", "#SeedhiBaat", "#CrudeOil", "#EMI", "#RBI"]},
                             "threads": {"text": "Oil 100?"}},
                "carousel": carousel}
    p.ids = {"out_sha": "abc123", "yt_id": "yt1"}
    return p


class FakeCall:
    """Records Graph API calls; containers get ids c1, c2...; publishes return m<id>; status is FINISHED."""
    def __init__(self):
        self.calls, self.n = [], 0

    def __call__(self, method, path, token, params=None):
        self.calls.append((method, path, dict(params or {})))
        if path.endswith("/media"):
            self.n += 1; return {"id": f"c{self.n}"}
        if path.endswith("/media_publish"):
            return {"id": "m" + params["creation_id"]}
        if path.endswith("/threads"):
            self.n += 1; return {"id": f"t{self.n}"}
        if path.endswith("/threads_publish"):
            return {"id": "tp" + params["creation_id"]}
        return {"status_code": "FINISHED", "status": "FINISHED"}


def test_media_url_uses_out_sha():
    assert instagram.media_url(_piece(), "reel.mp4", "SGULIA20/sg-content") == \
        "https://raw.githubusercontent.com/SGULIA20/sg-content/abc123/out/2026-10-20-sglearning-short/reel.mp4"


def test_media_url_requires_sha():
    p = _piece(); p.ids["out_sha"] = ""
    with pytest.raises(instagram.InstagramError):
        instagram.media_url(p, "reel.mp4", "r")


def test_caption_text_joins_hashtags():
    assert instagram.caption_text(_piece()).endswith("#PaiseKiKhabar #SeedhiBaat #CrudeOil #EMI #RBI")


def test_publish_piece_posts_reel_and_story_not_carousel(tmp_path):
    fc = FakeCall()
    p = instagram.publish_piece(_piece(), {"IG_ACCESS_TOKEN": "t", "IG_USER_ID": "u", "GITHUB_REPOSITORY": "r"}, call=fc, sleep=lambda s: None, root=tmp_path)
    kinds = [c[2].get("media_type") for c in fc.calls if c[1].endswith("/media")]
    assert kinds == ["REELS", "STORIES"]
    assert p.ids["ig_reel_id"] == "mc1" and p.ids["ig_story_id"] == "mc2" and "ig_post_id" not in p.ids
    reel = next(c for c in fc.calls if c[2].get("media_type") == "REELS")
    assert reel[2]["video_url"].endswith("/reel.mp4") and DISCLAIMER in reel[2]["caption"]
    assert json.loads(reel[2]["trial_params"]) == {"graduation_strategy": "SS_PERFORMANCE"} and "share_to_feed" not in reel[2]   # Trial Reel first
    assert pieces.load(p.id, root=tmp_path).ids["ig_reel_id"] == "mc1"                 # saved after each success


def test_partial_publish_resumes_without_duplicate(tmp_path):
    fc = FakeCall()
    p = _piece(); p.ids["ig_reel_id"] = "already"
    p = instagram.publish_piece(p, {"IG_ACCESS_TOKEN": "t", "IG_USER_ID": "u", "GITHUB_REPOSITORY": "r"}, call=fc, sleep=lambda s: None, root=tmp_path)
    kinds = [c[2].get("media_type") for c in fc.calls if c[1].endswith("/media")]
    assert kinds == ["STORIES"] and p.ids["ig_reel_id"] == "already" and p.ids["ig_story_id"] == "mc1"


def test_carousel_only_when_flagged(tmp_path):
    fc = FakeCall()
    p = instagram.publish_piece(_piece(carousel=True), {"IG_ACCESS_TOKEN": "t", "IG_USER_ID": "u", "GITHUB_REPOSITORY": "r"}, call=fc, sleep=lambda s: None, root=tmp_path)
    media = [c[2] for c in fc.calls if c[1].endswith("/media")]
    children = [m for m in media if m.get("is_carousel_item") == "true"]
    carousel = [m for m in media if m.get("media_type") == "CAROUSEL"]
    assert len(children) == 3 and len(carousel) == 1 and carousel[0]["children"] == "c3,c4,c5"
    assert children[0]["image_url"].endswith("/slide01.jpg") and p.ids["ig_post_id"].startswith("m")


def test_story_failure_keeps_reel_id_and_raises(tmp_path):
    class Flaky(FakeCall):
        def __call__(self, method, path, token, params=None):
            if params and params.get("media_type") == "STORIES":
                raise instagram.InstagramError("media not ready")
            return super().__call__(method, path, token, params)
    fc = Flaky()
    with pytest.raises(instagram.PartialPublish):
        instagram.publish_piece(_piece(), {"IG_ACCESS_TOKEN": "t", "IG_USER_ID": "u", "GITHUB_REPOSITORY": "r"}, call=fc, sleep=lambda s: None, root=tmp_path)
    assert pieces.load("2026-10-20-sglearning-short", root=tmp_path).ids["ig_reel_id"] == "mc1"


def test_wait_polls_until_finished():
    seen = []
    def call(method, path, token, params=None):
        seen.append(path); return {"status_code": "IN_PROGRESS" if len(seen) < 3 else "FINISHED"}
    instagram._wait("c1", "t", "reel", sleep=lambda s: None, call=call, max_polls=5, poll_s=0)
    assert len(seen) == 3


def test_wait_gives_up_with_error():
    with pytest.raises(instagram.InstagramError):
        instagram._wait("c1", "t", "reel", sleep=lambda s: None, call=lambda *a, **k: {"status_code": "IN_PROGRESS"}, max_polls=2, poll_s=0)


def test_api_host_matches_instagram_login_tokens():
    assert instagram.API.startswith("https://graph.instagram.com/")


def test_reel_gets_cover_url_when_cover_exists(tmp_path):
    fc = FakeCall()
    p = _piece()
    (tmp_path / "out" / p.id).mkdir(parents=True); (tmp_path / "out" / p.id / "cover.jpg").write_bytes(b"j")
    instagram.publish_piece(p, {"IG_ACCESS_TOKEN": "t", "IG_USER_ID": "u", "GITHUB_REPOSITORY": "r"}, call=fc, sleep=lambda s: None, root=tmp_path)
    reel = next(c for c in fc.calls if c[2].get("media_type") == "REELS")
    assert reel[2]["cover_url"].endswith("/cover.jpg")


def test_media_url_falls_back_to_the_branch_when_the_recorded_commit_does_not_serve_the_file():
    class R:
        def __init__(self, status): self.status = status
        def __enter__(self): return self
        def __exit__(self, *a): return False
    p = _piece()
    seen = []
    def head(req):
        seen.append(req.full_url); return R(200 if "/main/" in req.full_url else 404)
    url = instagram.resolved_media_url(p, "reel.mp4", "o/r", head=head)
    assert url == "https://raw.githubusercontent.com/o/r/main/out/2026-10-20-sglearning-short/reel.mp4" and len(seen) == 2
    assert instagram.resolved_media_url(p, "reel.mp4", "o/r", head=lambda req: R(200)) == "https://raw.githubusercontent.com/o/r/abc123/out/2026-10-20-sglearning-short/reel.mp4"
    with pytest.raises(instagram.InstagramError):
        instagram.resolved_media_url(p, "reel.mp4", "o/r", head=lambda req: R(404))


def test_caption_carries_the_channels_youtube_link_before_the_hashtags():
    cap = instagram.caption_text(_piece())
    assert "https://www.youtube.com/@sanjeev_gulia?sub_confirmation=1" in cap and cap.rstrip().endswith("#RBI")
    assert cap.index("youtube.com") < cap.index("#PaiseKiKhabar")


def test_a_story_file_over_60_s_is_skipped_not_retried_forever(tmp_path, monkeypatch):
    # 21 Oct 2026: a piece made before the no-trim rule had a 91 s story.mp4; Instagram answered ERROR on every run
    out = tmp_path / "out" / "2026-10-20-sglearning-short"
    out.mkdir(parents=True)
    (out / "story.mp4").write_bytes(b"x")
    monkeypatch.setattr(instagram, "_too_long_for_story", lambda video, max_s=60.0: True)
    fc = FakeCall()
    p = instagram.publish_piece(_piece(), {"IG_ACCESS_TOKEN": "t", "IG_USER_ID": "u", "GITHUB_REPOSITORY": "r"}, call=fc, sleep=lambda s: None, root=tmp_path)
    assert [c[2].get("media_type") for c in fc.calls if c[1].endswith("/media")] == ["REELS"]
    assert p.ids["ig_story_id"].startswith("skipped")


def test_a_refused_trial_reel_falls_back_to_a_normal_reel(tmp_path):
    class NoTrial(FakeCall):
        def __call__(self, method, path, token, params=None):
            if params and params.get("trial_params"):
                raise instagram.InstagramError("HTTP 400: trial reels not available")
            return super().__call__(method, path, token, params)
    fc = NoTrial()
    p = instagram.publish_piece(_piece(), {"IG_ACCESS_TOKEN": "t", "IG_USER_ID": "u", "GITHUB_REPOSITORY": "r"}, call=fc, sleep=lambda s: None, root=tmp_path)
    reel = next(c for c in fc.calls if (c[2] or {}).get("media_type") == "REELS")
    assert reel[2]["share_to_feed"] == "true" and p.ids["ig_reel_id"] and p.ids["ig_trial"].startswith("no")


def test_mp4_length_is_read_from_the_file_header_without_ffprobe(tmp_path):
    import struct
    mvhd = b"mvhd" + bytes([0, 0, 0, 0]) + struct.pack(">II", 0, 0) + struct.pack(">II", 1000, 91267)   # version 0: timescale, duration
    f = tmp_path / "story.mp4"
    f.write_bytes(b"\x00\x00\x00\x20ftypisom" + b"\x00" * 16 + b"\x00\x00\x00\x6cmoov\x00\x00\x00\x64" + mvhd + b"\x00" * 80)
    assert abs(instagram.mp4_seconds(f) - 91.267) < 0.001 and instagram._too_long_for_story(f)
    (tmp_path / "stub.mp4").write_bytes(b"x")
    assert instagram.mp4_seconds(tmp_path / "stub.mp4") is None and not instagram._too_long_for_story(tmp_path / "stub.mp4")


def test_the_cover_comes_from_main_so_a_redone_cover_is_used():
    from engine import instagram, pieces
    from datetime import date
    p = pieces.Piece(id="2026-10-30-sglearning-short", channel="sglearning", kind="short", publish_day=date(2026, 10, 30))
    p.ids["out_sha"] = "abc123"
    assert instagram.cover_url(p, "o/r", head=lambda req: _Ok()).endswith("/main/out/2026-10-30-sglearning-short/cover.jpg")
    def only_sha(req):
        if "/main/" in req.full_url:
            raise OSError("404")
        return _Ok()
    assert "/abc123/" in instagram.cover_url(p, "o/r", head=only_sha)


class _Ok:
    status = 200
    def __enter__(self): return self
    def __exit__(self, *a): return False
