import subprocess

import pytest

from engine import qa

pytestmark = pytest.mark.slow


def _clip(path, seconds, colour="blue", tone=True, lufs=-16, black_start=False, size="1080x1920"):
    vsrc = f"color=c={colour}:s={size}:r=30"
    if black_start:
        vsrc = f"color=c=black:s={size}:r=30"
    args = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", vsrc]
    if tone:
        args += ["-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000", "-af", f"volume=0.3,loudnorm=I={lufs}:TP=-1.5:LRA=11"]
    else:
        args += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono"]
    args += ["-t", str(seconds), "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", str(path)]
    subprocess.run(args, check=True)
    return path


def test_silent_black_clip_fails_three_ways(tmp_path):
    clip = _clip(tmp_path / "bad.mp4", 20, tone=False, black_start=True)
    reasons = qa.report(clip, "short", voiced_seconds=18.0, caption_cues=[(0.0, 18.0, "x")])
    kinds = {r.split(":")[0] for r in reasons}
    assert {"duration", "loudness", "black", "frozen"} <= kinds


def test_good_synthetic_clip_passes(tmp_path):
    clip = _clip(tmp_path / "good.mp4", 45)
    assert qa.report(clip, "short", voiced_seconds=43.0, caption_cues=[(0.0, 43.0, "x")], check_freeze=False) == []


def test_caption_coverage_below_95_fails(tmp_path):
    clip = _clip(tmp_path / "good.mp4", 45)
    reasons = qa.report(clip, "short", voiced_seconds=43.0, caption_cues=[(0.0, 20.0, "x")], check_freeze=False)
    assert any(r.startswith("captions") for r in reasons)


def test_long_duration_window_uses_target(tmp_path):
    clip = _clip(tmp_path / "l.mp4", 60, size="1920x1080")
    assert not any(r.startswith("duration") for r in qa.report(clip, "long", voiced_seconds=58, caption_cues=[(0, 58, "x")], target_seconds=60, check_freeze=False))
    assert any(r.startswith("duration") for r in qa.report(clip, "long", voiced_seconds=58, caption_cues=[(0, 58, "x")], target_seconds=120, check_freeze=False))


def test_probe_reads_duration_and_loudness(tmp_path):
    clip = _clip(tmp_path / "p.mp4", 10)
    info = qa.probe(clip)
    assert info["duration"] == pytest.approx(10.0, abs=0.2) and -18.5 <= info["lufs"] <= -13.5 and info["decode_errors"] == 0


def test_story_shorts_may_run_to_three_minutes(tmp_path):
    clip = _clip(tmp_path / "s.mp4", 80)
    assert not any(r.startswith("duration") for r in qa.report(clip, "short", voiced_seconds=78, caption_cues=[(0, 78, "x")], check_freeze=False, story=True))
    assert any(r.startswith("duration") for r in qa.report(clip, "short", voiced_seconds=78, caption_cues=[(0, 78, "x")], check_freeze=False))
