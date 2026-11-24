from datetime import date
from types import SimpleNamespace as P

from engine import instagram, pieces, publish, storyframe, tracks

LIST = {"source": "https://incompetech.com/music/royalty-free/mp3-royaltyfree/",
        "arthvan": [{"title": "Five Armies", "filename": "Five Armies.mp3"}, {"title": "Heroic Age", "filename": "Heroic Age.mp3"}], "sglearning": []}


def test_a_piece_always_gets_the_same_track_and_a_channel_with_none_gets_nothing():
    """Founder, 24 Nov 2026: 'Why can't this music automised. You have everything just do it'."""
    a = tracks.pick(P(id="2026-12-03-arthvan-short", channel="arthvan"), LIST)
    assert a == tracks.pick(P(id="2026-12-03-arthvan-short", channel="arthvan"), LIST) and a["title"] in ("Five Armies", "Heroic Age")
    assert tracks.url({**a, "filename": "Five Armies.mp3"}).endswith("/mp3-royaltyfree/Five%20Armies.mp3")
    assert tracks.pick(P(id="2026-12-03-sglearning-short", channel="sglearning"), LIST) is None
    real = tracks.load()
    assert len(real["sglearning"]) >= 10 and len(real["arthvan"]) >= 10 and all(t["filename"].endswith(".mp3") for t in real["arthvan"])


def test_a_failed_or_tiny_download_gives_none_so_the_code_made_sound_is_used(tmp_path):
    t = {"title": "Five Armies", "filename": "Five Armies.mp3", "source": LIST["source"]}
    def boom(u):
        raise OSError("no network")
    assert tracks.fetch(t, tmp_path / "t.mp3", get=boom) is None
    assert tracks.fetch(t, tmp_path / "t.mp3", get=lambda u: b"<html>not found</html>") is None
    assert tracks.fetch(t, tmp_path / "t.mp3", get=lambda u: b"x" * 300_000).stat().st_size == 300_000


def test_the_credit_goes_wherever_the_video_goes():
    p = pieces.Piece(id="2026-12-03-arthvan-short", channel="arthvan", kind="short", publish_day=date(2026, 12, 3))
    p.script = {"captions": {"instagram": {"caption": "Trojan Horse sach tha?", "hashtags": ["#SGMythWorld"]}, "threads": {"text": "Trojan Horse sach tha?", "hashtags": []}}, "scenes": []}
    assert "Kevin MacLeod" not in instagram.caption_text(p) and "Kevin MacLeod" not in publish.threads_text(p)      # no track, no credit
    p.ids["music"] = {"title": "Five Armies"}
    assert 'Music: "Five Armies" Kevin MacLeod (incompetech.com), CC BY 4.0' in instagram.caption_text(p)
    assert "Kevin MacLeod (incompetech.com)" in publish.threads_text(p) and len(publish.threads_text(p)) <= 500
    full = tracks.credit(p.ids["music"])
    assert "Creative Commons: By Attribution 4.0" in full and "creativecommons.org/licenses/by/4.0" in full
    p.script["captions"]["threads"]["text"] = "x" * 480
    assert publish.threads_text(p).endswith("CC BY 4.0") and len(publish.threads_text(p)) <= 500                   # a long post is trimmed, the credit stays
    assert "anullsink" in storyframe.designed_mix(58.0, track=True) and "anullsink" not in storyframe.designed_mix(58.0)
