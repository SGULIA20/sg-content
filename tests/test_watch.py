import json
from datetime import date
from pathlib import Path

from engine import pieces, watch


def _piece(n=10, kind="short"):
    p = pieces.Piece(id=f"2026-12-05-arthvan-{kind}", channel="arthvan", kind=kind, publish_day=date(2026, 12, 5))
    p.script = {"title": "Ravan ki seedhi bane *Shani*?", "scenes": [{"vo": f"line {i}"} for i in range(n)]}
    p.timings = [i * 5.0 for i in range(n)]
    return p


def _grab(video, second, out):
    Path(out).write_bytes(b"jpg")
    return out


def test_the_opening_scenes_are_always_looked_at_and_a_long_is_sampled():
    short = watch.moments([i * 5.0 for i in range(10)], 50.0, "short")
    assert [i for i, _s in short] == list(range(10)) and all(0 < s < 50 for _i, s in short)
    long_ = watch.moments([i * 10.0 for i in range(70)], 700.0, "long")
    assert len(long_) == watch.FRAMES_LONG and [i for i, _s in long_][:4] == [0, 1, 2, 3] and long_[-1][0] > 60


def test_a_good_video_sends_nothing_and_a_weak_one_tells_the_founder_what_a_viewer_sees(tmp_path):
    """Founder, 24 Nov 2026: 'yes, run the test'. Report only: the review never stops a video."""
    p, told, asked = _piece(), [], []
    good = json.dumps({"opening": 8, "opening_why": "a statue lying face down", "issues": [], "best_change": "", "verdict": "good"})
    r = watch.review(p, tmp_path / "v.mp4", tmp_path / "w", ask=lambda c: asked.append(c) or good, grab=_grab, duration=50.0)
    assert r["verdict"] == "good" and r["frames"] == 10 and watch.message(p, r) == ""
    sent = asked[0]
    assert sum(1 for b in sent if b["type"] == "image") == 10 and "line 0" in sent[2]["text"] and "Ravan ki seedhi" in sent[0]["text"]
    weak = "Here you go:\n" + json.dumps({"opening": 4, "opening_why": "a calm temple, nothing happens", "verdict": "fix", "best_change": "open on the dice",
                                           "issues": [{"frame": 6, "second": 27, "problem": "the app form is shown while the line says a result line", "fix": "show the result screen"}]})
    r = watch.review(p, tmp_path / "v.mp4", tmp_path / "w", ask=lambda c: weak, grab=_grab, duration=50.0)
    text = watch.message(p, r)
    assert "Opening 4/10" in text and "second 27" in text and "Report only" in text


def test_a_review_that_fails_is_forgotten_and_the_piece_keeps_the_score_of_one_that_works(tmp_path, monkeypatch):
    monkeypatch.setattr(watch.qa if hasattr(watch, "qa") else __import__("engine.qa", fromlist=["probe"]), "probe", lambda v: {"duration": 50.0})
    p, told = _piece(), []
    assert watch.look(p, tmp_path / "v.mp4", tmp_path, notify=told.append, ask=lambda c: "sorry", grab=_grab) is None and told == [] and "watch" not in p.ids
    ok = json.dumps({"opening": 5, "opening_why": "skippable", "issues": [], "best_change": "start on the question", "verdict": "good"})
    r = watch.look(p, tmp_path / "v.mp4", tmp_path, notify=told.append, ask=lambda c: ok, grab=_grab)
    assert r["opening"] == 5 and p.ids["watch"] == {"opening": 5, "verdict": "good", "best_change": "start on the question", "issues": 0}
    assert len(told) == 1 and "Opening 5/10" in told[0]                                       # a skippable opening is worth telling him
