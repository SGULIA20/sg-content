"""The founder cut out of his intro clip, so the story's pictures can move behind him (founder, 10 Nov 2026: "in back of founder video
can we run video or running pictures"; the avatar tool also draws a floating blue screen beside him, which the cut-out removes).

A person-segmentation model finds him in every frame; a general model adds what he holds (the printed photo), but only inside his own
outline's width on each row, so the floating screen beside him stays out. Needs `pip install rembg onnxruntime` (the workflows that
compose intros install it); without it `available()` is False and the intro is shown full-screen as recorded.
"""
import subprocess
from pathlib import Path

import numpy as np


def available() -> bool:
    try:
        import rembg  # noqa: F401
        return True
    except Exception:
        return False


def _row_span(mask: np.ndarray) -> np.ndarray:
    """True between the leftmost and rightmost set pixel of each row."""
    any_row = mask.any(axis=1)
    first = mask.argmax(axis=1)
    last = mask.shape[1] - 1 - mask[:, ::-1].argmax(axis=1)
    xs = np.arange(mask.shape[1])[None, :]
    return any_row[:, None] & (xs >= first[:, None]) & (xs <= last[:, None])


def combine(person: np.ndarray, general: np.ndarray) -> np.ndarray:
    """Alpha (0-255): the person, plus what the general model sees inside the person's width on each row (the prop in his hands)."""
    span = _row_span(person > 127)
    alpha = np.maximum(person, np.where(span, general, 0))
    solid = alpha > 127                                         # a notch in his body where the see-through screen overlapped it: something
    above = np.maximum.accumulate(solid, axis=0)               # of him above and below in the same column, and the general model saw
    below = np.maximum.accumulate(solid[::-1], axis=0)[::-1]   # at least a faint object there
    notch = above & below & ~solid & (general > 30)
    return np.where(notch, 255, alpha).astype(np.uint8)


def mask_video(clip: Path, seconds: float, out: Path, fps: int = 30, size: tuple = (720, 1280), sessions=None) -> Path:
    """A grey video the size of `size`: white where the founder (and his prop) is. One frame per video frame."""
    from PIL import Image, ImageFilter
    from rembg import new_session, remove
    w, h = size
    person_s, general_s = sessions or (new_session("u2net_human_seg"), new_session("u2net"))
    src = subprocess.Popen(["ffmpeg", "-v", "error", "-t", f"{seconds:.3f}", "-i", str(clip), "-vf", f"fps={fps},scale={w}:{h}", "-f", "rawvideo",
                            "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    dst = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "gray", "-s", f"{w}x{h}", "-r", str(fps), "-i", "-",
                            "-c:v", "libx264", "-preset", "veryfast", "-crf", "12", "-pix_fmt", "yuv420p", str(out)], stdin=subprocess.PIPE)
    n = w * h * 3
    try:
        while True:
            buf = src.stdout.read(n)
            if len(buf) < n:
                break
            im = Image.frombuffer("RGB", (w, h), buf)
            person = np.array(remove(im, session=person_s, only_mask=True))
            general = np.array(remove(im, session=general_s, only_mask=True))
            alpha = Image.fromarray(combine(person, general)).filter(ImageFilter.GaussianBlur(1.2))
            dst.stdin.write(alpha.tobytes())
    finally:
        dst.stdin.close()
        dst.wait()
        src.wait()
    return out


def over(background: Path, clip: Path, mask: Path, seconds: float, size: tuple, out: Path, overlays: list = (), fps: int = 30,
         scale: float = 0.92) -> Path:
    """`clip` cut out by `mask`, standing at the bottom centre of `background` (looped to `seconds`); overlays are (png, x, y) or
    (png, x, y, start, end). Silent H.264."""
    w, h = size
    fw, fh = int(w * scale) // 2 * 2, int(h * scale) // 2 * 2
    inputs = ["-stream_loop", "-1", "-i", str(background), "-i", str(clip), "-i", str(mask)]
    chain = (f"[0:v]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},fps={fps},setsar=1[bg];"
             f"[1:v]fps={fps},scale={fw}:{fh},setsar=1[c];[2:v]fps={fps},scale={fw}:{fh},format=gray,setsar=1[m];[c][m]alphamerge[fg];"
             f"[bg][fg]overlay={(w - fw) // 2}:{h - fh}[b0]")
    last = "[b0]"
    for k, ov in enumerate(overlays, start=3):
        inputs += ["-loop", "1", "-i", str(ov[0])]
        window = f":enable='between(t,{ov[3]:.3f},{ov[4]:.3f})'" if len(ov) == 5 else ""
        chain += f";{last}[{k}:v]overlay={ov[1]}:{ov[2]}{window}[o{k}]"
        last = f"[o{k}]"
    out = Path(out)
    subprocess.run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", chain, "-map", last, "-t", f"{seconds:.3f}", "-r", str(fps),
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-an", str(out)], check=True)
    return out
