"""Small 3D-film camera movement on a still picture (founder, 9 Nov 2026: "can't these pictures become video with small movements, like a 3D film?").

A depth model (Depth Anything V2 Small) says how far each part of the picture is; the camera then drifts and zooms a little, and near parts move more
than far parts (parallax). Free to run (CPU), but only a trial: busy edges can stretch. Used by scripts/trial_reel.py --depth.
"""
import subprocess
from pathlib import Path

import numpy as np

MODEL = "depth-anything/Depth-Anything-V2-Small-hf"
SHIFT_PX = 34            # how far the nearest parts move across the clip, at 1080 px wide
LIFT_PX = 14
MARGIN = 1.18
ZOOM = (1.05, 1.13)      # slow push-in, as the plain Ken Burns does


PUNCH, PUNCH_TAU = 0.10, 0.14   # every cut lands a little closer and settles in about a third of a second


def available() -> bool:
    try:
        import cv2  # noqa: F401
        import torch  # noqa: F401
        import transformers  # noqa: F401
        return True
    except Exception:
        return False


def estimate(paths: list, model: str = MODEL) -> list:
    """Depth maps (float 0 far .. 1 near, same size as each picture) for a list of picture paths."""
    from PIL import Image
    from transformers import pipeline
    pipe = pipeline("depth-estimation", model=model, device=-1)
    out = []
    for p in paths:
        im = Image.open(p).convert("RGB")
        d = np.array(pipe(im)["depth"].resize(im.size), dtype=np.float32)
        d = (d - d.min()) / max(1e-6, float(d.max() - d.min()))
        out.append(d)
    return out


def fake_depth(size: tuple) -> np.ndarray:
    """A plain far-to-near gradient (bottom of the picture nearest): only for checking the assembly without the model."""
    w, h = size
    return np.tile(np.linspace(0.0, 1.0, h, dtype=np.float32)[:, None], (1, w))


def move(image: Path, depth: np.ndarray, seconds: float, size: tuple, out: Path, fps: int = 30, direction: int = 1) -> Path:
    """Writes a silent H.264 clip of `image` with parallax movement."""
    import cv2
    w, h = size
    img = cv2.imread(str(image))
    ih, iw = img.shape[:2]
    scale = max(w / iw, h / ih) * MARGIN                       # margin so the shifted edges never show
    img = cv2.resize(img, (int(iw * scale), int(ih * scale)), interpolation=cv2.INTER_CUBIC)
    dep = cv2.resize(depth, (img.shape[1], img.shape[0]), interpolation=cv2.INTER_LINEAR)
    dep = cv2.GaussianBlur(dep, (0, 0), 6)                    # soft depth: less tearing at edges
    dep = dep - float(dep.mean())
    ph, pw = img.shape[:2]
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
    frames = max(2, int(round(seconds * fps)))
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{w}x{h}", "-r", str(fps), "-i", "-",
                             "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", str(out)], stdin=subprocess.PIPE)
    try:
        for f in range(frames):
            t = f / (frames - 1)
            e = t * t * (3 - 2 * t)                              # ease in and out
            zoom = ZOOM[0] + (ZOOM[1] - ZOOM[0]) * e + PUNCH * float(np.exp(-(f / fps) / PUNCH_TAU))
            sx = direction * (e - 0.5) * 2 * SHIFT_PX * (w / 1080)
            sy = (0.5 - e) * 2 * LIFT_PX * (w / 1080)
            cx, cy = pw / 2, ph / 2
            # the sampling position of each output pixel: centred crop at this zoom, plus a depth-weighted shift (near parts move more)
            k = MARGIN / zoom
            mx = cx + (xs - w / 2) * k
            my = cy + (ys - h / 2) * k
            dsample = cv2.remap(dep, mx.astype(np.float32), my.astype(np.float32), cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
            frame = cv2.remap(img, (mx + sx * dsample * 1.6).astype(np.float32), (my + sy * dsample * 1.6).astype(np.float32),
                              cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT)
            proc.stdin.write(frame.tobytes())
    finally:
        proc.stdin.close()
        proc.wait()
    return out
