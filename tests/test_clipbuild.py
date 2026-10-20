import json
import subprocess
from datetime import date
from pathlib import Path

import pytest

from engine import clipbuild, pieces

pytestmark = pytest.mark.slow


def _clip(path, seconds=3.0, size="720x1280", silent_tail=0.0):
    tone = f"sine=frequency=300:sample_rate=48000"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c=blue:s={size}:r=24", "-f", "lavfi", "-i", tone,
                    "-t", str(seconds), "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-ac", "2", str(path)], check=True)
    return path


def _probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height,r_frame_rate:format=duration",
                          "-of", "json", str(path)], capture_output=True, text=True, check=True).stdout
    d = json.loads(out)
    return d["streams"][0]["width"], d["streams"][0]["height"], d["streams"][0]["r_frame_rate"], float(d["format"]["duration"])


def _piece(kind="short"):
    p = pieces.Piece(id=f"2026-10-21-sglearning-{kind}", channel="sglearning", kind=kind, publish_day=date(2026, 10, 21))
    p.script = {"hook": "h", "scenes": [{"vo": "a", "visual": {"type": "avatar", "card": None}, "facts_used": [0], "label": "reported"},
                                        {"vo": "b", "visual": {"type": "card", "card": {"big_number": "8,110 cr", "line": "anchor", "source": "Mint"}}, "facts_used": [1], "label": "reported"}],
                "cards": [], "captions": {"youtube": {"title": "t", "description": "d", "tags": [], "chapters": ["00:00 Hook", "00:00 LIC"]}}}
    p.facts = [{"source_name": "Mint", "source_date": "2026-10-19"}, {"source_name": "BS", "source_date": "2026-10-19"}]
    p.topic = {"pack": [{"part": 1, "scene": 0, "narration": "India ka sabse bada IPO aa gaya", "prompt": "x"},
                        {"part": 2, "scene": 1, "narration": "Anchor investors ne 8,110 crore daale", "prompt": "y"}]}
    return p


def test_normalise_scales_to_1080_and_30fps(tmp_path):
    clip = _clip(tmp_path / "c.mp4")
    out = clipbuild.normalise(clip, (1080, 1920), tmp_path / "n.mp4")
    w, h, fps, dur = _probe(out)
    assert (w, h, fps) == (1080, 1920, "30/1") and dur == pytest.approx(3.0, abs=0.3)


def test_build_merges_with_overlays_captions_and_music(tmp_path):
    p = _piece()
    clips = [_clip(tmp_path / "p1.mp4"), _clip(tmp_path / "p2.mp4")]
    out = clipbuild.build(p, p.topic["pack"], clips, tmp_path / "out")
    w, h, fps, dur = _probe(out)
    assert (w, h, fps) == (1080, 1920, "30/1") and out.name == "reel.mp4"
    assert dur == pytest.approx(6.0, abs=0.6) and p.timings[0] == 0.0 and 2.5 < p.timings[1] < 3.5
    assert (tmp_path / "out" / "captions.ass").exists()


def test_long_piece_builds_16_9_named_long(tmp_path):
    p = _piece("long")
    clips = [_clip(tmp_path / "p1.mp4", size="1280x720"), _clip(tmp_path / "p2.mp4", size="1280x720")]
    out = clipbuild.build(p, p.topic["pack"], clips, tmp_path / "out")
    assert _probe(out)[:2] == (1920, 1080) and out.name == "long.mp4"


def test_check_uses_qa_without_caption_rule(tmp_path):
    p = _piece()
    clips = [_clip(tmp_path / "p1.mp4"), _clip(tmp_path / "p2.mp4")]
    out = clipbuild.build(p, p.topic["pack"], clips, tmp_path / "out")
    problems = clipbuild.check(out, p)
    assert all(not r.startswith("captions") for r in problems)
    assert any(r.startswith("duration") for r in problems)                       # 6 s is under the 40 s Short floor


def test_thumbnail_from_first_clip(tmp_path):
    p = _piece()
    clip = _clip(tmp_path / "p1.mp4")
    out = clipbuild.thumbnail(p, clip, tmp_path / "thumb.jpg")
    assert out.exists() and out.stat().st_size > 1000


def test_short_or_long_by_duration():
    assert clipbuild.kind_for(55.0) == "short" and clipbuild.kind_for(61.0) == "long"
