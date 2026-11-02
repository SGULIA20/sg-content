import shutil
from pathlib import Path

import pytest

from engine import newscard, pipeline


def test_step_names():
    assert newscard.step_name(0, 7, False) == "SAWAAL" and newscard.step_name(6, 7, False) == "BHEJO"
    assert newscard.step_name(3, 12, True) == "#3" and newscard.step_name(0, 12, True) == "TOP 10"


class _Deps:
    def __init__(self, fail=False):
        self.fail, self.calls = fail, []

    def render_card(self, kind, data, out, size):
        Path(out).write_bytes(b"png"); return Path(out)

    def animate_card(self, data, i, n, roundup, seconds, size, out):
        self.calls.append((i, n, roundup, round(seconds, 2), size))
        if self.fail:
            raise RuntimeError("no browser")
        Path(out).write_bytes(b"mp4"); return Path(out)


def _piece():
    from datetime import date
    from engine import pieces
    p = pieces.Piece(id="2026-11-02-sglearning-x1", channel="sglearning", kind="short", publish_day=date(2026, 11, 2))
    p.topic = {"preset": {"extra": True, "graphics": True, "category": "crypto"}}
    p.script = {"scenes": [{"vo": "Binance se chori hui?", "visual": {"type": "card", "card": {"big_number": "", "line": "chori"}}}] * 3}
    return p


def test_news_card_moves_and_keeps_the_still_for_the_thumbnail(tmp_path):
    d = _Deps()
    out = pipeline._newscard(_piece(), 1, _piece().script["scenes"][1], d, tmp_path / "visual01.png", (1080, 1920), line=("w.wav", 4.0))
    assert out.suffix == ".mp4" and (tmp_path / "visual01.png").exists() and d.calls[0][:3] == (1, 3, False)


def test_a_failed_animation_falls_back_to_the_still_card(tmp_path):
    out = pipeline._newscard(_piece(), 0, _piece().script["scenes"][0], _Deps(fail=True), tmp_path / "visual00.png", (1080, 1920), line=("w.wav", 4.0))
    assert out.suffix == ".png"


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg")
def test_animate_renders_a_video(tmp_path):
    pytest.importorskip("playwright")
    data = {"tag": "x", "icon": "🪙", "big_number": "90%", "line": "paisa wapas", "accent": "#F7931A", "glow": "#F7931A55"}
    out = newscard.animate(data, 1, 4, False, 0.4, (540, 800), tmp_path / "c.mp4", fps=5)
    assert out.exists() and out.stat().st_size > 1000
