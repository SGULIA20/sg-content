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


def test_the_founders_thumbnail_redraws_the_card_and_the_story_goes_as_a_video_with_music(tmp_path):
    p = _long(tmp_path)
    used, vids = [], []
    def render(kind, data, out, size):
        used.append(data["thumb_path"].parent.name); out.write_bytes(b"j" * 2000); return out
    make = lambda jpg, out: vids.append(out.name) or out.write_bytes(b"mp4")
    assert teaser.backfill(tmp_path, render, make) == [p.id] and used == [p.id]           # the pipeline's own thumbnail first
    (tmp_path / "inbox" / "thumb").mkdir(parents=True)
    (tmp_path / "inbox" / "thumb" / f"{p.id}.jpg").write_bytes(b"founder")
    assert teaser.backfill(tmp_path, render, make) == [p.id] and used[-1] == "thumb"       # his thumbnail arrived: drawn again from it
    assert teaser.backfill(tmp_path, render, make) == [] and vids == ["teaser.mp4", "teaser.mp4"]
    posted = []
    after = datetime(2026, 11, 4, 14, 0, tzinfo=timezone.utc)
    assert teaser.run(tmp_path, "sglearning", after, {}, publish=lambda prm: posted.append(prm) or "s", url=lambda pc, repo, name="teaser.jpg": name) == []
    assert posted == [{"media_type": "STORIES", "video_url": "teaser.mp4"}]


def test_a_long_on_any_weekday_gets_its_story(tmp_path):
    (tmp_path / "pieces").mkdir()
    mon = date(2026, 11, 9)
    p = pieces.Piece(id="2026-11-09-sglearning-long", channel="sglearning", kind="long", publish_day=mon, status="uploaded")
    p.ids = {"yt_id": "v"}
    pieces.save(p, tmp_path)
    assert teaser.due(tmp_path, "sglearning", datetime(2026, 11, 9, 14, 0, tzinfo=timezone.utc)).id == p.id
