from datetime import date, datetime, timezone

from engine import pieces, publish, teaser

WED = date(2026, 11, 4)                                                       # a Learning with SG long-video day


def _long(root, **ids):
    (root / "pieces").mkdir(exist_ok=True)
    p = pieces.Piece(id="2026-11-04-sglearning-long", channel="sglearning", kind="long", publish_day=WED, status="uploaded")
    p.ids = {"yt_id": "v", **ids}
    p.script = {"title": "Gold ya SIP?"}
    pieces.save(p, root)
    (root / "out" / p.id).mkdir(parents=True, exist_ok=True)
    (root / "out" / p.id / "thumb.jpg").write_bytes(b"jpg")
    return p


def test_the_card_is_drawn_once_for_each_made_long_video(tmp_path):
    _long(tmp_path)
    drawn = []
    def render(kind, data, out, size):
        drawn.append((kind, data["title_html"], size)); out.write_bytes(b"jpg"); return out
    assert teaser.backfill(tmp_path, render) == ["2026-11-04-sglearning-long"]
    assert drawn == [("teaser", "Gold ya SIP?", (1080, 1920))]
    assert teaser.backfill(tmp_path, render) == []                            # already drawn


def test_the_story_posts_once_after_the_long_video_is_public(tmp_path):
    _long(tmp_path)
    (tmp_path / "out" / "2026-11-04-sglearning-long" / "teaser.jpg").write_bytes(b"jpg")
    posted = []
    post = lambda params: posted.append(params) or "story-1"
    url = lambda p, repo: "https://raw/teaser.jpg"
    before = datetime(2026, 11, 4, 13, 0, tzinfo=timezone.utc)                # 18:30 India: the long video is not public yet
    assert teaser.run(tmp_path, "sglearning", before, {}, publish=post, url=url) == [] and posted == []
    after = datetime(2026, 11, 4, 14, 3, tzinfo=timezone.utc)                 # 19:33 India
    assert teaser.run(tmp_path, "sglearning", after, {}, publish=post, url=url) == []
    assert posted == [{"media_type": "STORIES", "image_url": "https://raw/teaser.jpg"}]
    assert pieces.load("2026-11-04-sglearning-long", tmp_path).ids["ig_teaser_id"] == "story-1"
    assert teaser.run(tmp_path, "sglearning", after, {}, publish=post, url=url) == [] and len(posted) == 1   # once


def test_no_card_yet_is_reported_not_crashed(tmp_path):
    _long(tmp_path)
    after = datetime(2026, 11, 4, 14, 3, tzinfo=timezone.utc)
    assert "no long-video Story card yet" in teaser.run(tmp_path, "sglearning", after, {}, publish=lambda p: "x", url=lambda p, r: "u")[0]


def test_publish_reports_teaser_problems(tmp_path):
    (tmp_path / "pieces").mkdir()
    sent = []
    publish.run(tmp_path, "sglearning", datetime(2026, 11, 4, 14, 3, tzinfo=timezone.utc), env={}, notify=sent.append,
                teaser=lambda root, ch, now, env: ["2026-11-04-sglearning-long: long-video Story: boom"])
    assert "long-video Story: boom" in sent[0]
