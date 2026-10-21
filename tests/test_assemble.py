import json
import subprocess
from pathlib import Path
import wave
from datetime import date

import pytest

from engine import assemble, pieces

pytestmark = pytest.mark.slow


def _probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height,r_frame_rate:format=duration",
                          "-of", "json", str(path)], capture_output=True, text=True, check=True).stdout
    d = json.loads(out)
    return d["streams"][0]["width"], d["streams"][0]["height"], d["streams"][0]["r_frame_rate"], float(d["format"]["duration"])


def _png(path, w, h, colour):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c={colour}:s={w}x{h}", "-frames:v", "1", str(path)], check=True)
    return path


def _tone(path, seconds, rate=24000):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"sine=frequency=440:sample_rate={rate}", "-t", str(seconds),
                    "-ac", "1", "-sample_fmt", "s16", str(path)], check=True)
    return path


def _music(path, seconds=30):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=220:sample_rate=44100", "-t", str(seconds),
                    "-ac", "2", "-c:a", "aac", str(path)], check=True)
    return path


def test_scene_clip_has_requested_length_and_size(tmp_path):
    img = _png(tmp_path / "a.png", 1080, 1920, "red")
    clip = assemble.scene_clip(img, 2.0, (1080, 1920), tmp_path / "a.mp4")
    w, h, fps, dur = _probe(clip)
    assert (w, h, fps) == (1080, 1920, "30/1") and dur == pytest.approx(2.0, abs=0.1)


def test_two_scene_short_builds_1080x1920_30fps(tmp_path):
    p = pieces.Piece(id="2026-10-20-sglearning-short", channel="sglearning", kind="short", publish_day=date(2026, 10, 20))
    p.script = {"hook": "h", "scenes": [{"vo": "ek do teen", "visual": {"type": "art"}, "facts_used": [0], "label": "reported"},
                                        {"vo": "chaar paanch", "visual": {"type": "card"}, "facts_used": [], "label": "reported"}],
                "end_question": "q", "cards": [], "captions": {}, "carousel": False}
    p.facts = [{"source_name": "ET", "source_date": "2026-10-19"}]
    lines = [(_tone(tmp_path / "v0.wav", 1.8), 1.8), (_tone(tmp_path / "v1.wav", 1.6), 1.6)]
    visuals = [_png(tmp_path / "s0.png", 1080, 1920, "blue"), _png(tmp_path / "s1.png", 1080, 1920, "green")]
    out = assemble.build(p, lines, visuals, (1080, 1920), tmp_path / "out", music=_music(tmp_path / "m.m4a"),
                         source_strip=_png(tmp_path / "strip.png", 1080, 120, "yellow"))
    w, h, fps, dur = _probe(out)
    assert (w, h, fps) == (1080, 1920, "30/1")
    assert dur == pytest.approx(1.8 + 1.6 + 2 * assemble.PAD_S, abs=0.3)
    assert out.name == "reel.mp4" and (tmp_path / "out" / "captions.ass").exists()
    assert p.timings == [pytest.approx(0.0), pytest.approx(1.8 + assemble.PAD_S)]


def test_chapters_from_timings():
    p = pieces.Piece(id="x", channel="arthvan", kind="long", publish_day=date(2026, 10, 24))
    p.script = {"captions": {"youtube": {"chapters": ["00:00 Hook", "00:00 Sabut", "00:00 Vivaad"]}}, "scenes": [{"vo": "a"}] * 6}
    p.timings = [0.0, 30.0, 61.0, 95.0, 130.0, 170.0]
    assert assemble.chapters(p) == ["00:00 Hook", "01:01 Sabut", "02:10 Vivaad"]


def test_fit_speeds_voice_when_short_runs_long(tmp_path):
    lines = [(_tone(tmp_path / f"v{i}.wav", 8.0), 8.0) for i in range(8)]          # 64 s of voice + pads: over 59 s
    fitted, factor = assemble.fit_short(lines, tmp_path / "fit", limit=59.0)
    assert 1.0 < factor <= assemble.FIT_MAX
    total = sum(d for _w, d in fitted) + len(fitted) * assemble.PAD_S
    assert total <= 59.0 + 0.5
    lines2 = [(_tone(tmp_path / f"s{i}.wav", 4.0), 4.0) for i in range(5)]
    assert assemble.fit_short(lines2, tmp_path / "fit2", limit=59.0)[1] == 1.0


def test_source_strip_sits_at_top_and_skips_avatar_scenes():
    p = pieces.Piece(id="x", channel="sglearning", kind="short", publish_day=date(2026, 10, 20))
    p.script = {"scenes": [{"vo": "a", "visual": {"type": "avatar"}, "facts_used": [0]}, {"vo": "b", "visual": {"type": "card"}, "facts_used": [0]}]}
    strips = {0: Path("/tmp/strip.png")}
    assert assemble._overlays_for(p, 0, (1080, 1920), strips, {}) == []
    assert assemble._overlays_for(p, 1, (1080, 1920), strips, {}) == [(Path("/tmp/strip.png"), 0, 40)]


def test_story_cut_keeps_short_videos_and_trims_long_ones(tmp_path):
    src = tmp_path / "v.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=blue:s=64x64:d=3", "-f", "lavfi", "-i", "sine=d=3",
                    "-shortest", "-pix_fmt", "yuv420p", str(src)], check=True)
    same = assemble.story_cut(src, tmp_path / "s1.mp4", max_s=5)
    assert same.read_bytes() == src.read_bytes()
    cut = assemble.story_cut(src, tmp_path / "s2.mp4", max_s=2)
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(cut)],
                               capture_output=True, text=True).stdout)
    assert 1.8 <= dur <= 2.2
