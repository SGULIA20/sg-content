"""Small 3D-film camera movement on a still picture (founder, 9 Nov 2026: "can't these pictures become video with small movements, like a 3D film?").

A depth model (Depth Anything V2 Small) says how far each part of the picture is; the camera then drifts and zooms a little, and near parts move more
than far parts (parallax). Free to run (CPU), but only a trial: busy edges can stretch. Used by scripts/trial_reel.py --depth.
"""
import subprocess
from pathlib import Path

import numpy as np

MODEL = "depth-anything/Depth-Anything-V2-Small-hf"
# founder, 10 Nov 2026: the first setting (34 px, zoom 1.05-1.13) "did not move"; free stronger camera movement, a different path per scene
MARGIN = 1.30            # the picture is drawn this much larger than the frame, so the moving camera never shows an edge
PARALLAX = 1.15          # near parts move this much more than the average (1.6 stretched the edges of people and rocks, 10 Nov 2026)
PATHS = ("glide", "push", "rise", "pull")
SHIFT_PX, LIFT_PX = 115, 105       # founder, 10 Nov 2026: 90/80 was too little ("more"), 140/130 stretched edges ("B"): the middle
ZOOM_TOP = MARGIN + 0.25            # the furthest push: a little closer than the picture's own size


def camera(path: str, e: float, direction: int = 1) -> tuple:
    """(zoom, shift x, shift y) at eased time e (0..1) for a camera path. The zoom at each moment leaves enough picture outside the
    frame for that moment's shift, so no edge shows (tests/test_depthmove.py checks every path)."""
    if path == "push":                                         # straight in, strongly
        return 1.12 + 0.28 * e, direction * (e - 0.5) * 2 * 24, (0.5 - e) * 2 * 13
    if path == "pull":                                         # starting close, drawing back to show the place
        return 1.40 - 0.26 * e, direction * (e - 0.5) * 2 * 26, (e - 0.5) * 2 * 13
    if path == "rise":                                         # the camera lifts: near ground slides down, the far scene opens
        return 1.20 + 0.08 * e, direction * (e - 0.5) * 2 * 24, (0.5 - e) * 2 * LIFT_PX
    return 1.18 + 0.08 * e, direction * (e - 0.5) * 2 * SHIFT_PX, (0.5 - e) * 2 * 14      # glide: a sideways track


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


def move(image: Path, depth: np.ndarray, seconds: float, size: tuple, out: Path, fps: int = 30, direction: int = 1, path: str = "glide") -> Path:
    """Writes a silent H.264 clip of `image` with parallax movement along a camera path (see camera())."""
    import cv2
    w, h = size
    img = cv2.imread(str(image))
    ih, iw = img.shape[:2]
    scale = max(w / iw, h / ih) * MARGIN                    # margin so the shifted edges never show
    img = cv2.resize(img, (int(iw * scale), int(ih * scale)), interpolation=cv2.INTER_CUBIC)
    dep = cv2.resize(depth, (img.shape[1], img.shape[0]), interpolation=cv2.INTER_LINEAR)
    dep = cv2.GaussianBlur(dep, (0, 0), 11)                    # soft depth: less tearing at edges
    dep = dep - float(dep.mean())
    ph, pw = img.shape[:2]
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
    frames = max(2, int(round(seconds * fps)))
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{w}x{h}", "-r", str(fps), "-i", "-",
                             "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", str(out)], stdin=subprocess.PIPE)
    k1080 = w / 1080
    try:
        for f in range(frames):
            t = f / (frames - 1)
            e = t * t * (3 - 2 * t)                              # ease in and out
            zoom, sx, sy = camera(path, e, direction)
            zoom += PUNCH * float(np.exp(-(f / fps) / PUNCH_TAU))
            sx, sy = sx * k1080, sy * k1080
            cx, cy = pw / 2, ph / 2
            k = MARGIN / zoom
            mx = cx + (xs - w / 2) * k
            my = cy + (ys - h / 2) * k
            dsample = cv2.remap(dep, mx.astype(np.float32), my.astype(np.float32), cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
            frame = cv2.remap(img, (mx + sx * (1 + PARALLAX * dsample)).astype(np.float32), (my + sy * (1 + PARALLAX * dsample)).astype(np.float32),
                              cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT)
            proc.stdin.write(frame.tobytes())
    finally:
        proc.stdin.close()
        proc.wait()
    return out
