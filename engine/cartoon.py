"""Code-animated cartoon presenter: the founder's drawn character talks with mouth frames driven by the cloned voice (path A, 20 Oct 2026).

talking_head_clip(wav, seconds, size, out, mood) -> an H.264 clip: head frame switches closed / open-a / open-b on syllables, gentle bob,
a body pose cut-in for the mood on a dark gradient background. Frames are composited with numpy and piped to ffmpeg.
"""
import subprocess
import wave
from pathlib import Path

import numpy as np
from PIL import Image

from .config import ASSETS_DIR, VIDEO

CARTOON_DIR = ASSETS_DIR / "cartoon"
FPS = VIDEO["fps"]
CHARACTER = "founder_suit"
POSES = {"explaining_front": "explaining_right", "explaining_right": "explaining_right", "explaining_left": "explaining_left",
         "pointing_up": "pointing_up", "pointing_right": "explaining_right", "thinking": "thinking", "worried": "worried", "wave": "wave",
         "waving": "wave", "end_smile": "wave", "surprised": "pointing_up", "shocked_big": "pointing_up", "phone": "phone",
         "holding_phone": "phone", "sitting_laptop": "sitting_laptop", "chapter_turn": "explaining_left", "serious_front": "front_neutral"}
OPEN_ON, CLOSE_UNDER, MIN_HOLD = 0.22, 0.12, 4
BG_TOP, BG_BOTTOM = (21, 33, 59), (11, 15, 26)


def pose_for(mood: str, character: str = CHARACTER) -> str:
    pose = POSES.get(mood, "front_neutral")
    return pose if (CARTOON_DIR / f"{character}_{pose}.png").exists() else "front_neutral"


def head_frames(outfit: str = "suit") -> dict:
    base = CARTOON_DIR / f"founder_{outfit}"
    return {"closed": Path(f"{base}_head_neutral.png"), "a": Path(f"{base}_head_talk_a_al.png"), "b": Path(f"{base}_head_talk_b_al.png")}


def mouth_envelope(wav: Path, fps: int = FPS) -> list:
    """One state per frame: 'closed', 'a' or 'b'. Opens on syllable energy with hysteresis and a minimum hold, alternating the two open frames."""
    with wave.open(str(wav)) as w:
        rate, n = w.getframerate(), w.getnframes()
        pcm = np.frombuffer(w.readframes(n), dtype=np.int16).astype(np.float32) / 32768
        if w.getnchannels() == 2:
            pcm = pcm.reshape(-1, 2)[:, 0]
    hop = rate // fps
    frames = int(np.ceil(len(pcm) / hop))
    raw = np.array([float(np.sqrt(np.mean(pcm[i * hop:(i + 1) * hop] ** 2))) if len(pcm[i * hop:(i + 1) * hop]) else 0.0 for i in range(frames)])
    raw = raw / (raw.max() or 1.0)
    sm = np.convolve(raw, np.ones(3) / 3, mode="same")
    states, opened, hold, which = [], False, 0, "a"
    for v in sm:
        if opened:
            hold += 1
            if v < CLOSE_UNDER and hold >= MIN_HOLD:
                opened = False
            elif hold % 5 == 0:
                which = "b" if which == "a" else "a"
        elif v > OPEN_ON:
            opened, hold = True, 0
        states.append(which if opened else "closed")
    return states


def _gradient(size: tuple) -> np.ndarray:
    w, h = size
    t = np.linspace(0, 1, h)[:, None, None]
    top, bottom = np.array(BG_TOP, dtype=np.float32), np.array(BG_BOTTOM, dtype=np.float32)
    return np.repeat((top * (1 - t) + bottom * t), w, axis=1).astype(np.uint8)


def _load_rgba(path: Path, height: int) -> np.ndarray:
    im = Image.open(path).convert("RGBA")
    scale = height / im.height
    im = im.resize((max(1, int(im.width * scale)), height), Image.LANCZOS)
    return np.asarray(im).astype(np.float32)


def _paste(frame: np.ndarray, layer: np.ndarray, x: int, y: int) -> None:
    """Alpha-composite `layer` (float RGBA) onto `frame` (uint8 RGB) at x, y, clipped to the frame."""
    h, w = layer.shape[:2]
    fh, fw = frame.shape[:2]
    x0, y0, x1, y1 = max(0, x), max(0, y), min(fw, x + w), min(fh, y + h)
    if x1 <= x0 or y1 <= y0:
        return
    lay = layer[y0 - y:y1 - y, x0 - x:x1 - x]
    a = lay[:, :, 3:4] / 255.0
    region = frame[y0:y1, x0:x1].astype(np.float32)
    frame[y0:y1, x0:x1] = (lay[:, :, :3] * a + region * (1 - a)).astype(np.uint8)


def talking_head_clip(wav: Path, seconds: float, size: tuple, out: Path, mood: str = "explaining_front", outfit: str = "suit") -> Path:
    w, h = size
    portrait = h > w
    states = mouth_envelope(wav)
    total = max(1, int(round(seconds * FPS)))
    states += ["closed"] * max(0, total - len(states))
    heads = {k: _load_rgba(p, int(h * (0.46 if portrait else 0.62))) for k, p in head_frames(outfit).items()}
    pose_png = CARTOON_DIR / f"founder_{outfit}_{pose_for(mood, f'founder_{outfit}')}.png"
    body = _load_rgba(pose_png, int(h * 0.5)) if (pose_png.exists() and not portrait) else None   # landscape only: on a phone the head alone reads better
    bg = _gradient(size)
    hw, hh = heads["closed"].shape[1], heads["closed"].shape[0]
    head_x, head_y = (w - hw) // 2, int(h * (0.12 if portrait else 0.04))
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", str(FPS), "-i", "-",
                             "-t", f"{total / FPS:.3f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-an", str(out)],
                            stdin=subprocess.PIPE)
    try:
        for i in range(total):
            frame = bg.copy()
            t = i / FPS
            bob = int(6 * np.sin(2 * np.pi * 0.7 * t))
            if body is not None:
                bx = w - body.shape[1] - int(w * 0.04) if portrait else w - body.shape[1] - int(w * 0.06)
                by = h - body.shape[0] - int(h * (0.27 if portrait else 0.08))
                _paste(frame, body, bx, by + int(3 * np.sin(2 * np.pi * 0.5 * t + 1)))
            _paste(frame, heads[states[i]], head_x, head_y + bob)
            proc.stdin.write(frame.tobytes())
    finally:
        proc.stdin.close()
        proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed writing {out}")
    return out
