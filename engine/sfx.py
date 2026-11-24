"""Sound design made in code, so there is no licence to track (founder, 24 Nov 2026: "yes, upgrade the sound"; famous songs can only be
added by hand inside the phone apps, and mixing one into our file gets the video muted or claimed).

Three things the plain pad lacked: a HIT on the first word, a WHOOSH on each change of picture and a RISER into the reveal; a rhythmic
GROOVE under the pad (upbeat for Learning with SG, suspense for SG-MYTH-WORLD); and the music DUCKS under the voice and comes up in the
gaps (the ducking itself is done in the ffmpeg mix, engine/storyframe.py). content/sound.json {"design": false} switches it all off.
"""
import json
import wave
from pathlib import Path

import numpy as np

from .config import ROOT

RATE = 48000
REVEAL_AT = 0.66            # the twist of a story sits about two thirds in: the riser leads into the scene that starts nearest this point
WHOOSH_MIN_GAP = 2.5        # a long video changes picture every few seconds; a whoosh on every one would be noise
MOODS = {"sglearning": "upbeat", "arthvan": "suspense"}


def on(root: Path = ROOT) -> bool:
    try:
        return bool(json.loads((Path(root) / "content" / "sound.json").read_text()).get("design", True))
    except (OSError, ValueError):
        return True


def _noise(n: int, seed: int) -> np.ndarray:
    return np.random.default_rng(seed).standard_normal(n)


def _smooth(x: np.ndarray, width: int) -> np.ndarray:
    """A cheap low-pass: a moving average `width` samples wide."""
    if width <= 1:
        return x
    return np.convolve(x, np.ones(width) / width, mode="same")


def hit(seconds: float = 0.9) -> np.ndarray:
    """A low boom with a short click on top: the first word lands."""
    n = int(seconds * RATE); t = np.arange(n) / RATE
    freq = 45 + 75 * np.exp(-t * 9)                                   # the pitch drops from 120 Hz to 45 Hz
    boom = np.sin(2 * np.pi * np.cumsum(freq) / RATE) * np.exp(-t * 4.5)
    click = _noise(n, 1) * np.exp(-t * 90) * 0.5
    return boom * 0.9 + click


def whoosh(seconds: float = 0.42) -> np.ndarray:
    """Air moving past: noise that opens up and closes, peaking just before the cut."""
    n = int(seconds * RATE); t = np.arange(n) / RATE
    raw = _noise(n, 2)
    bright = raw - _smooth(raw, 24)                                    # the high part of the noise
    dull = _smooth(raw, 60)
    mix = np.linspace(0, 1, n)                                         # dull at first, bright at the end
    env = np.sin(np.pi * np.clip(t / seconds, 0, 1)) ** 2
    return (dull * (1 - mix) * 2.2 + bright * mix) * env * 0.6


def riser(seconds: float = 1.8) -> np.ndarray:
    """Tension building into the reveal: a tone and noise that climb, then stop dead."""
    n = int(seconds * RATE); t = np.arange(n) / RATE
    freq = 180 * (2 ** (2.2 * t / seconds))                           # just over two octaves
    tone = np.sin(2 * np.pi * np.cumsum(freq) / RATE)
    air = _noise(n, 3); air = air - _smooth(air, 16)
    env = (t / seconds) ** 2
    return (tone * 0.45 + air * 0.5) * env


def _place(buf: np.ndarray, sound: np.ndarray, at: float, gain: float) -> None:
    start = int(max(0.0, at) * RATE)
    end = min(len(buf), start + len(sound))
    if end > start:
        buf[start:end] += sound[:end - start] * gain


def cue_points(starts: list, total: float) -> dict:
    """{"hit": [t], "whoosh": [t...], "riser": [t]}: where each effect goes, from the scene start times."""
    starts = [float(s) for s in starts]
    whooshes, last = [], -99.0
    for s in starts[1:]:
        if s - last >= WHOOSH_MIN_GAP:
            whooshes.append(s); last = s
    reveal = min(starts[1:], key=lambda s: abs(s - REVEAL_AT * total)) if len(starts) > 3 else None
    return {"hit": [starts[0] if starts else 0.0], "whoosh": whooshes, "riser": [reveal] if reveal else []}


def track(starts: list, total: float, out: Path, long: bool = False) -> Path:
    """The effects of one video as a stereo WAV `total` seconds long."""
    buf = np.zeros(int((total + 0.5) * RATE))
    cues = cue_points(starts, total)
    for t in cues["hit"]:
        _place(buf, hit(), t, 0.9)
    w = whoosh()
    for t in cues["whoosh"]:
        _place(buf, w, t - 0.30, 0.35 if long else 0.5)               # it peaks as the picture changes
    r = riser()
    for t in cues["riser"]:
        _place(buf, r, t - len(r) / RATE, 0.45)
    return _write(buf, out, peak=0.7)


def groove(mood: str, seconds: float, out: Path) -> Path:
    """A rhythm to sit under the pad. upbeat: a soft kick on every beat, a tick between, a bass note per bar (100 bpm).
    suspense: a slow heartbeat (two thuds), a low drone that swells, a distant tick (60 bpm)."""
    n = int(seconds * RATE); t = np.arange(n) / RATE; buf = np.zeros(n)
    bpm = 100 if mood == "upbeat" else 60
    beat = 60.0 / bpm
    k = np.arange(int(0.22 * RATE)) / RATE
    kick = np.sin(2 * np.pi * np.cumsum(50 + 70 * np.exp(-k * 30)) / RATE) * np.exp(-k * 16)
    tk = np.arange(int(0.05 * RATE)) / RATE
    tick = (_noise(len(tk), 4) - _smooth(_noise(len(tk), 4), 8)) * np.exp(-tk * 80)
    for i in range(int(seconds / beat) + 1):
        at = i * beat
        if mood == "upbeat":
            _place(buf, kick, at, 0.7)
            _place(buf, tick, at + beat / 2, 0.25)
            if i % 4 == 0:
                b = np.arange(int(beat * 2 * RATE)) / RATE
                _place(buf, np.sin(2 * np.pi * 55 * b) * np.exp(-b * 2.2), at, 0.35)
        else:
            _place(buf, kick, at, 0.6)                                 # lub
            _place(buf, kick, at + 0.28, 0.35)                         # dub
            if i % 2 == 1:
                _place(buf, tick, at + beat / 2, 0.12)
    if mood != "upbeat":
        buf += 0.22 * np.sin(2 * np.pi * 41.2 * t) * (0.6 + 0.4 * np.sin(2 * np.pi * t / 11.0))
    fade = int(1.5 * RATE)
    buf[:fade] *= np.linspace(0, 1, fade); buf[-fade:] *= np.linspace(1, 0, fade)
    return _write(buf, out, peak=0.6)


def impact(seconds: float = 1.6) -> np.ndarray:
    """A bigger, film-trailer hit: a sub drop, a metallic ring and a long tail."""
    n = int(seconds * RATE); t = np.arange(n) / RATE
    sub = np.sin(2 * np.pi * np.cumsum(38 + 110 * np.exp(-t * 6)) / RATE) * np.exp(-t * 2.2)
    ring = sum(np.sin(2 * np.pi * f * t) * np.exp(-t * d) for f, d in ((311, 5), (466, 6), (622, 8))) * 0.12
    crack = _noise(n, 5) * np.exp(-t * 40) * 0.7
    tail = _smooth(_noise(n, 6), 40) * np.exp(-t * 2.5) * 1.5
    return sub + ring + crack + tail


def drums(seconds: float, out: Path, bpm: int = 90) -> Path:
    """War drums: big low hits in a galloping pattern, for a myth or history story."""
    n = int(seconds * RATE); buf = np.zeros(n); beat = 60.0 / bpm
    k = np.arange(int(0.5 * RATE)) / RATE
    tom = np.sin(2 * np.pi * np.cumsum(55 + 60 * np.exp(-k * 14)) / RATE) * np.exp(-k * 7) + _smooth(_noise(len(k), 7), 30) * np.exp(-k * 25) * 0.8
    pattern = [(0, 1.0), (0.75, 0.5), (1.0, 0.8), (1.5, 0.45), (2.0, 1.0), (2.5, 0.5), (3.0, 0.8), (3.5, 0.6), (3.75, 0.45)]
    for bar in range(int(seconds / (beat * 4)) + 1):
        for pos, gain in pattern:
            _place(buf, tom, (bar * 4 + pos) * beat, gain)
    fade = int(1.0 * RATE); buf[:fade] *= np.linspace(0, 1, fade); buf[-fade:] *= np.linspace(1, 0, fade)
    return _write(buf, out, peak=0.7)


def drive(seconds: float, out: Path, bpm: int = 110) -> Path:
    """A driving beat: kick on every beat, a clap on two and four, fast ticks and a moving bass line, for an energetic explainer."""
    n = int(seconds * RATE); buf = np.zeros(n); beat = 60.0 / bpm
    k = np.arange(int(0.22 * RATE)) / RATE
    kick = np.sin(2 * np.pi * np.cumsum(48 + 90 * np.exp(-k * 32)) / RATE) * np.exp(-k * 15)
    c = np.arange(int(0.16 * RATE)) / RATE
    clap = (_noise(len(c), 8) - _smooth(_noise(len(c), 8), 10)) * np.exp(-c * 28)
    tk = np.arange(int(0.04 * RATE)) / RATE
    tick = (_noise(len(tk), 9) - _smooth(_noise(len(tk), 9), 6)) * np.exp(-tk * 90)
    notes = [55.0, 55.0, 65.4, 49.0]                                   # one bass note a bar: A, A, C, G
    for i in range(int(seconds / beat) + 1):
        at = i * beat
        _place(buf, kick, at, 0.8)
        if i % 2 == 1:
            _place(buf, clap, at, 0.5)
        for j in range(4):
            _place(buf, tick, at + j * beat / 4, 0.18 if j else 0.28)
        b = np.arange(int(beat * 0.9 * RATE)) / RATE
        _place(buf, np.sin(2 * np.pi * notes[(i // 4) % 4] * b) * np.exp(-b * 4), at, 0.4)
    fade = int(1.0 * RATE); buf[:fade] *= np.linspace(0, 1, fade); buf[-fade:] *= np.linspace(1, 0, fade)
    return _write(buf, out, peak=0.7)


def _write(mono: np.ndarray, out: Path, peak: float) -> Path:
    top = float(np.max(np.abs(mono))) or 1.0
    mono = mono / top * peak
    pcm = (np.clip(np.stack([mono, mono], axis=1), -1, 1) * 32767).astype(np.int16)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(RATE); w.writeframes(pcm.tobytes())
    return Path(out)
