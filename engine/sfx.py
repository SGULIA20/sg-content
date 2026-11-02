"""Sound effects synthesised in code for the Reels drawn by Claude (founder, 2 Nov 2026, from the Reel X-ray: "every voiceover point
triggers an instant animation and sound cue"). No licence to track: a pop when the icon lands, a tick when a number finishes counting,
a soft whoosh when the progress bar moves. Mixed quietly under the voice; the Gemini-painted Shorts get none."""
import wave
from pathlib import Path

import numpy as np

RATE = 44100
POP_AT, TICK_AT, WHOOSH_AT = 0.45, 1.15, 0.05       # seconds into a scene: the tile lands, the number stops counting, the bar moves
GAIN = {"pop": 0.55, "tick": 0.40, "whoosh": 0.22}


def _env(n: int, attack: float, decay: float) -> np.ndarray:
    t = np.arange(n) / RATE
    return np.minimum(1.0, t / max(attack, 1e-4)) * np.exp(-t / max(decay, 1e-4))


def pop(seconds: float = 0.18) -> np.ndarray:
    """A short bubble pop: a sine sweeping down with a fast decay."""
    n = int(seconds * RATE)
    t = np.arange(n) / RATE
    freq = 520 * np.exp(-t * 18) + 140
    return np.sin(2 * np.pi * np.cumsum(freq) / RATE) * _env(n, 0.003, 0.05)


def tick(seconds: float = 0.12) -> np.ndarray:
    """A crisp tick: two high partials with a very fast decay."""
    n = int(seconds * RATE)
    t = np.arange(n) / RATE
    return (np.sin(2 * np.pi * 2600 * t) + 0.5 * np.sin(2 * np.pi * 4100 * t)) * _env(n, 0.001, 0.025)


def whoosh(seconds: float = 0.35) -> np.ndarray:
    """A soft whoosh: filtered noise rising then falling."""
    n = int(seconds * RATE)
    rng = np.random.default_rng(7)
    noise = rng.standard_normal(n)
    kernel = np.ones(24) / 24
    smooth = np.convolve(noise, kernel, mode="same")
    t = np.arange(n) / RATE
    return smooth * np.sin(np.pi * t / seconds) ** 2


def _norm(fn):
    def inner(*a, **k):
        s = fn(*a, **k)
        return s / (np.max(np.abs(s)) or 1.0)
    return inner


SOUNDS = {"pop": _norm(pop), "tick": _norm(tick), "whoosh": _norm(whoosh)}


def track(events: list, total: float, out: Path) -> Path:
    """A mono WAV of `total` seconds with each (time, name) sound placed at its time."""
    n = int((total + 1.0) * RATE)
    mix = np.zeros(n)
    for at, name in events:
        s = SOUNDS[name]() * GAIN[name]
        i = int(max(0.0, at) * RATE)
        if i >= n:
            continue
        s = s[: n - i]
        mix[i:i + len(s)] += s
    peak = np.max(np.abs(mix)) or 1.0
    pcm = (np.clip(mix / max(peak, 1.0), -1, 1) * 32767).astype(np.int16)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(RATE); w.writeframes(pcm.tobytes())
    return out


def events_for(starts: list, has_number: list) -> list:
    """The cue list for a Reel of news cards: a whoosh and a pop in every scene, a tick where the scene counts a number up."""
    out = []
    for start, numbered in zip(starts, has_number):
        out.append((start + WHOOSH_AT, "whoosh"))
        out.append((start + POP_AT, "pop"))
        if numbered:
            out.append((start + TICK_AT, "tick"))
    return out
