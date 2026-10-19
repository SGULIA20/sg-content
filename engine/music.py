"""Original ambient music beds synthesised in code (no third-party licence to track). Cached in assets/music/."""
import wave
from pathlib import Path

import numpy as np

from .config import ASSETS_DIR

RATE = 44100
BEDS = {
    "calm":  {"root": 110.0, "chords": [(1, 1.25, 1.5), (1.125, 1.333, 1.667), (0.889, 1.111, 1.333), (1, 1.2, 1.5)], "bpm": 72},   # finance
    "epic":  {"root": 82.4, "chords": [(1, 1.2, 1.5), (0.8, 1, 1.2), (0.667, 0.8, 1), (0.75, 0.9, 1.125)], "bpm": 60},           # mythology
    "light": {"root": 146.8, "chords": [(1, 1.25, 1.5), (1.333, 1.667, 2), (1.125, 1.5, 1.875), (1, 1.25, 1.5)], "bpm": 84},     # end cards
}


def _pad(freq: float, seconds: float, t: np.ndarray) -> np.ndarray:
    tone = np.zeros_like(t)
    for k, amp in ((1, 1.0), (2, 0.35), (3, 0.12), (4, 0.05)):
        tone += amp * np.sin(2 * np.pi * freq * k * t + 0.3 * k)
    vib = 1 + 0.004 * np.sin(2 * np.pi * 0.21 * t)
    return tone * vib


def render(name: str, seconds: float) -> np.ndarray:
    spec = BEDS[name]
    sr = RATE
    bar = 60.0 / spec["bpm"] * 4
    n = int(seconds * sr)
    t = np.arange(n) / sr
    out = np.zeros(n)
    for i, chord in enumerate(spec["chords"] * int(seconds // (bar * 4) + 2)):
        start, end = int(i * bar * sr), int(min((i + 1) * bar * sr + 0.8 * sr, n))
        if start >= n:
            break
        seg = t[start:end] - t[start]
        env = np.minimum(1.0, seg / 0.8) * np.minimum(1.0, (end - start) / sr - seg + 0.01) / 1.0
        env = np.clip(env, 0, 1)
        for ratio in chord:
            out[start:end] += 0.18 * env * _pad(spec["root"] * ratio, seconds, seg)
    swell = 0.85 + 0.15 * np.sin(2 * np.pi * t / 23.0)
    out = out * swell
    fade = int(1.5 * sr)
    out[:fade] *= np.linspace(0, 1, fade)
    out[-fade:] *= np.linspace(1, 0, fade)
    peak = np.max(np.abs(out)) or 1.0
    return (out / peak * 0.6).astype(np.float32)


def bed(name: str, seconds: float, assets: Path = ASSETS_DIR) -> Path:
    """A stereo WAV of the bed, at least `seconds` long, cached by name and length bucket (30 s steps)."""
    length = int(((seconds + 2) // 30 + 1) * 30)
    out = Path(assets) / "music" / f"{name}-{length}s.wav"
    if out.exists():
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    mono = render(name, length)
    stereo = np.stack([mono, np.roll(mono, 441)], axis=1)              # 10 ms offset for width
    pcm = (np.clip(stereo, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(out), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(RATE); w.writeframes(pcm.tobytes())
    return out
