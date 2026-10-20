"""Checks on the rendered file before upload: duration, loudness, decode errors, frozen video, black start, caption coverage (spec §3 step 9)."""
import json
import re
import subprocess
from pathlib import Path

SHORT_RANGE = (40.0, 59.0)
STORY_RANGE = (40.0, 95.0)
LONG_TOLERANCE = 0.20
LUFS_TARGET, LUFS_TOL = -16.0, 1.5
FREEZE_MAX_S = 3.0
CAPTION_COVERAGE = 0.95
BLACK_WINDOW_S = 0.5


def _ffmpeg(args: list) -> str:
    return subprocess.run(["ffmpeg", "-hide_banner", "-nostats", *args], capture_output=True, text=True).stderr


def probe(path: Path) -> dict:
    """duration (s), lufs (integrated), decode_errors (count), width, height."""
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height:format=duration",
                          "-of", "json", str(path)], capture_output=True, text=True, check=True).stdout
    d = json.loads(out)
    info = {"duration": float(d["format"]["duration"]), "width": d["streams"][0]["width"], "height": d["streams"][0]["height"]}
    err = _ffmpeg(["-v", "error", "-i", str(path), "-f", "null", "-"])
    info["decode_errors"] = len([l for l in err.splitlines() if l.strip()])
    loud = _ffmpeg(["-i", str(path), "-vn", "-af", "ebur128=framelog=quiet", "-f", "null", "-"])
    m = re.search(r"I:\s+(-?[\d.]+) LUFS", loud)
    info["lufs"] = float(m.group(1)) if m else -70.0
    return info


def frozen_seconds(path: Path, duration: float | None = None) -> float:
    """Longest run of frozen frames (seconds). A freeze that lasts to the end of the file logs only its start."""
    out = _ffmpeg(["-i", str(path), "-vf", "freezedetect=n=0.001:d=1", "-an", "-f", "null", "-"])
    runs = [float(x) for x in re.findall(r"freeze_duration: ([\d.]+)", out)]
    starts = re.findall(r"freeze_start: ([\d.]+)", out)
    ends = re.findall(r"freeze_end: ([\d.]+)", out)
    if len(starts) > len(ends):
        total = duration if duration is not None else probe(path)["duration"]
        runs.append(total - float(starts[-1]))
    return max(runs) if runs else 0.0


def black_start(path: Path, window: float = BLACK_WINDOW_S) -> bool:
    out = _ffmpeg(["-t", str(window), "-i", str(path), "-vf", f"blackdetect=d={window * 0.8}:pic_th=0.98", "-an", "-f", "null", "-"])
    return "black_start" in out


def report(path: Path, kind: str, voiced_seconds: float, caption_cues: list, target_seconds: float | None = None,
           check_freeze: bool = True, story: bool = False) -> list:
    """Empty list = pass. Each reason starts with its gate name."""
    reasons = []
    info = probe(path)
    dur = info["duration"]
    if kind == "short":
        lo, hi = STORY_RANGE if story else SHORT_RANGE
    else:
        target = target_seconds or dur
        lo, hi = target * (1 - LONG_TOLERANCE), target * (1 + LONG_TOLERANCE)
    if not lo <= dur <= hi:
        reasons.append(f"duration: {dur:.1f}s, allowed {lo:.0f}-{hi:.0f}s")
    if abs(info["lufs"] - LUFS_TARGET) > LUFS_TOL:
        reasons.append(f"loudness: {info['lufs']:.1f} LUFS, target {LUFS_TARGET} ± {LUFS_TOL}")
    if info["decode_errors"]:
        reasons.append(f"decode: {info['decode_errors']} errors")
    if check_freeze:
        fz = frozen_seconds(path, dur)
        if fz > FREEZE_MAX_S:
            reasons.append(f"frozen: {fz:.1f}s without motion")
    if black_start(path):
        reasons.append("black: the first frame is black")
    covered = sum(max(0.0, e - s) for s, e, _t in caption_cues)
    if voiced_seconds > 0 and covered / voiced_seconds < CAPTION_COVERAGE:
        reasons.append(f"captions: cover {covered / voiced_seconds:.0%} of voiced time, need {CAPTION_COVERAGE:.0%}")
    return reasons
