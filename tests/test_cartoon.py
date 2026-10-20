import json
import subprocess
import wave
from pathlib import Path

import numpy as np
import pytest

from engine import cartoon


def _wav(path, pattern, rate=24000):
    """pattern: list of (seconds, loud: bool)."""
    chunks = []
    for secs, loud in pattern:
        n = int(secs * rate)
        t = np.arange(n) / rate
        chunks.append((0.5 * np.sin(2 * np.pi * 220 * t) if loud else np.zeros(n)))
    pcm = (np.concatenate(chunks) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate); w.writeframes(pcm.tobytes())
    return path


def test_mouth_envelope_opens_on_sound_and_closes_in_silence(tmp_path):
    wav = _wav(tmp_path / "v.wav", [(0.5, False), (1.0, True), (0.5, False), (0.6, True), (0.4, False)])
    states = cartoon.mouth_envelope(wav, fps=30)
    assert len(states) == 90
    assert all(s == "closed" for s in states[:12])                       # silence at the start
    assert sum(s != "closed" for s in states[18:42]) > 18                 # open through the first burst
    assert all(s == "closed" for s in states[48:58])
    assert {"a", "b"} & set(states)                                        # both open frames are used


def test_poses_known_and_default():
    assert cartoon.pose_for("explaining_front") == "explaining_right" and cartoon.pose_for("unknown_pose") == "front_neutral"
    assert cartoon.head_frames("suit")["closed"].exists() and cartoon.head_frames("suit")["a"].exists()


@pytest.mark.slow
def test_talking_head_clip_matches_voice_length(tmp_path):
    wav = _wav(tmp_path / "v.wav", [(0.3, False), (1.2, True), (0.3, False)])
    out = cartoon.talking_head_clip(wav, 1.8 + 0.45, (1080, 1920), tmp_path / "th.mp4", mood="explaining_front")
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height,r_frame_rate:format=duration", "-of", "json", str(out)],
                           capture_output=True, text=True, check=True).stdout
    d = json.loads(probe)
    assert (d["streams"][0]["width"], d["streams"][0]["height"], d["streams"][0]["r_frame_rate"]) == (1080, 1920, "30/1")
    assert abs(float(d["format"]["duration"]) - 2.25) < 0.15


@pytest.mark.slow
def test_scene_clip_accepts_a_video_scene(tmp_path):
    from engine import assemble
    src = tmp_path / "src.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=red:s=1080x1920:r=30", "-t", "2", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(src)], check=True)
    out = assemble.scene_clip(src, 2.0, (1080, 1920), tmp_path / "scene.mp4")
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(out)], capture_output=True, text=True, check=True).stdout
    assert abs(float(json.loads(probe)["format"]["duration"]) - 2.0) < 0.15
