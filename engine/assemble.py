"""ffmpeg assembly: Ken Burns on stills, overlays, caption cues burned per scene, voice over a music bed, loudness-normalised (spec §3 step 8).

Captions are transparent PNGs rendered by Chromium (engine.cards) and overlaid with a time window, so no libass build of ffmpeg is needed.
"""
import hashlib
import subprocess
import wave
from pathlib import Path

import numpy as np

from . import captions, cards
from .config import ASSETS_DIR, VIDEO
from .pieces import Piece

FPS = VIDEO["fps"]
PAD_S = 0.45                       # silence after each line
ZOOM_PER_FRAME = 0.0006
ZOOM_MAX = 1.08
VOICE_LUFS, MUSIC_LUFS, MIX_LUFS = -16, -30, -16
SHORT_MAX_S = 59.0
FIT_MAX = 1.18                     # at most 18 % faster speech to land a Short under 59 s
FONTS_DIR = ASSETS_DIR / "fonts"


def _run(args: list) -> None:
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


def scene_clip(image: Path, seconds: float, size: tuple, out: Path, zoom: float = ZOOM_MAX, overlays: list = ()) -> Path:
    """A silent H.264 clip of `image` with a slow push-in.

    overlays: (png, x, y) burned for the whole clip, or (png, x, y, start, end) shown only between those seconds."""
    w, h = size
    frames = max(1, int(round(seconds * FPS)))
    if str(image).lower().endswith((".mp4", ".mov", ".webm")):          # an already-animated scene (talking head, founder clip): no push-in
        chain = f"[0:v]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},fps={FPS},tpad=stop_mode=clone:stop_duration=5[base]"
        inputs = ["-i", str(image)]
    else:
        chain = (f"[0:v]scale={w * 2}:{h * 2}:force_original_aspect_ratio=increase,crop={w * 2}:{h * 2},"
                 f"zoompan=z='min(zoom+{ZOOM_PER_FRAME},{zoom})':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={w}x{h}:fps={FPS}[base]")
        inputs = ["-loop", "1", "-i", str(image)]
    last = "[base]"
    for i, ov in enumerate(overlays, start=1):
        png, x, y = ov[0], ov[1], ov[2]
        inputs += ["-loop", "1", "-i", str(png)]
        window = f":enable='between(t,{ov[3]:.3f},{ov[4]:.3f})'" if len(ov) == 5 else ""
        chain += f";{last}[{i}:v]overlay={x}:{y}:shortest=1{window}[o{i}]"
        last = f"[o{i}]"
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    _run([*inputs, "-filter_complex", chain, "-map", last, "-t", f"{frames / FPS:.3f}", "-r", str(FPS),
          "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-an", str(out)])
    return out


def _voice_track(lines: list, out_wav: Path, pad: float = PAD_S) -> list:
    """Concatenates the line WAVs with `pad` seconds of silence after each; returns the start time of every line."""
    starts, chunks, t, rate = [], [], 0.0, None
    for wav, _d in lines:
        with wave.open(str(wav)) as w:
            rate = rate or w.getframerate()
            assert w.getframerate() == rate and w.getnchannels() == 1 and w.getsampwidth() == 2, f"{wav}: expected mono 16-bit at {rate} Hz"
            data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
        starts.append(round(t, 3))
        chunks.append(data); chunks.append(np.zeros(int(pad * rate), dtype=np.int16))
        t += len(data) / rate + pad
    pcm = np.concatenate(chunks) if chunks else np.zeros(1, dtype=np.int16)
    with wave.open(str(out_wav), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate or 24000); w.writeframes(pcm.tobytes())
    return starts


def fit_short(lines: list, work_dir: Path, limit: float = SHORT_MAX_S, pad: float = PAD_S) -> tuple:
    """If voice + pads exceed the Short limit, speed every line by one factor (atempo, same pitch), up to FIT_MAX. Returns (lines, factor)."""
    total = sum(d for _w, d in lines) + pad * len(lines)
    if total <= limit:
        return lines, 1.0
    factor = min(FIT_MAX, (sum(d for _w, d in lines)) / max(0.1, limit - pad * len(lines)))
    factor = round(factor + 0.005, 2)
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    out = []
    for wav, _d in lines:
        fast = work_dir / Path(wav).name
        _run(["-i", str(wav), "-filter:a", f"atempo={factor}", str(fast)])
        with wave.open(str(fast)) as w:
            out.append((fast, w.getnframes() / w.getframerate()))
    return out, factor


def caption_band(size: tuple) -> tuple:
    """(height, y) of the caption band for this frame size."""
    w, h = size
    if h > w:
        band = 320
        return band, int(h * 0.72)
    band = 200
    return band, h - band - int(h * 0.06)


def cue_pngs(cues: list, size: tuple, out_dir: Path) -> list:
    """One transparent PNG per cue, cached by text: [(png, start, end)]."""
    band, _y = caption_band(size)
    out_dir = Path(out_dir)
    out = []
    for start, end, text in cues:
        png = out_dir / (hashlib.sha1(f"{size[0]}|{text}".encode()).hexdigest()[:16] + ".png")
        if not png.exists():
            cards.render("caption", {"text": text}, png, (size[0], band))
        out.append((png, start, end))
    return out


def _overlays_for(piece: Piece, i: int, size: tuple, source_strips, label_chips: dict, credits: dict | None = None) -> list:
    w, h = size
    scene = piece.script["scenes"][i]
    out = []
    strip_y = 40                                               # top edge: never collides with card text or the caption band
    if (scene.get("visual") or {}).get("type") == "avatar":
        source_strips, credits = None, None                    # presenter cards carry their own layout
    if piece.channel == "sglearning" and source_strips and scene.get("facts_used"):
        if isinstance(source_strips, dict):
            strip = next((source_strips[j] for j in scene["facts_used"] if j in source_strips), None)
        else:
            strip = source_strips
        if strip:
            out.append((strip, 0, strip_y))
    if credits and i in credits:
        out.append((credits[i], 0, strip_y))
    if piece.channel == "arthvan" and scene.get("label") in label_chips:
        out.append((label_chips[scene["label"]], w - 400 - 40, 40))
    return out


def build(piece: Piece, lines: list, visuals: list, size: tuple, out_dir: Path, music: Path | None = None,
          source_strip: Path | None = None, label_chips: dict | None = None, source_strips: dict | None = None, credits: dict | None = None) -> Path:
    """lines: [(wav, seconds)] and visuals: [png] in scene order. Writes reel.mp4 (short) or long.mp4 into out_dir, sets piece.timings."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    label_chips = label_chips or {}
    assert len(lines) == len(visuals) == len(piece.script["scenes"]), "one voice line and one visual per scene"
    if piece.kind == "short":
        lines, factor = fit_short(lines, out_dir / "vo-fit")
        if factor > 1.0:
            print(f"voice sped up {factor}x to fit the Short", flush=True)
    voice_wav = out_dir / "voice.wav"
    starts = _voice_track(lines, voice_wav)
    piece.timings = starts
    durations = [d + PAD_S for _w, d in lines]
    band, band_y = caption_band(size)
    all_cues, clips = [], []
    for i, (img, dur, (wav, d), start, scene) in enumerate(zip(visuals, durations, lines, starts, piece.script["scenes"])):
        cues = captions.split(scene["vo"], d)
        all_cues += captions.offset(cues, start)
        overlays = _overlays_for(piece, i, size, source_strips if source_strips is not None else source_strip, label_chips, credits)
        overlays += [(png, 0, band_y, s, e) for png, s, e in cue_pngs(cues, size, out_dir / "cues")]
        clips.append(scene_clip(img, dur, size, out_dir / f"scene{i:02d}.mp4", overlays=overlays))
    (out_dir / "captions.ass").write_text(captions.ass(all_cues, size))            # sidecar for upload or review
    concat_list = out_dir / "scenes.txt"
    concat_list.write_text("".join(f"file '{c.resolve()}'\n" for c in clips))
    total = sum(durations)
    out = out_dir / ("reel.mp4" if piece.kind == "short" else "long.mp4")
    inputs = ["-f", "concat", "-safe", "0", "-i", str(concat_list), "-i", str(voice_wav)]
    afilter = f"[1:a]aresample=48000,loudnorm=I={VOICE_LUFS}:TP=-1.5:LRA=11[v]"
    if music:
        inputs += ["-stream_loop", "-1", "-i", str(music)]
        afilter += (f";[2:a]aresample=48000,atrim=0:{total:.3f},asetpts=PTS-STARTPTS,afade=t=out:st={max(0.0, total - 2):.2f}:d=2,"
                    f"loudnorm=I={MUSIC_LUFS}:TP=-6:LRA=7[m];[v][m]amix=inputs=2:duration=first:normalize=0[mix]")
        amap = "[mix]"
    else:
        amap = "[v]"
    _run([*inputs, "-filter_complex", f"{afilter};{amap}loudnorm=I={MIX_LUFS}:TP=-1.5:LRA=11[aout]",
          "-map", "0:v", "-map", "[aout]", "-t", f"{total:.3f}", "-c:v", "copy",
          "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-movflags", "+faststart", str(out)])
    return out


def _mmss(sec: float) -> str:
    sec = int(round(sec))
    return f"{sec // 60:02d}:{sec % 60:02d}"


def chapters(piece: Piece) -> list:
    """Chapter lines with real timestamps: the writer's chapter titles spread evenly over the scenes."""
    titles = [c.split(" ", 1)[1] if " " in c else c for c in ((piece.script or {}).get("captions", {}).get("youtube", {}).get("chapters") or [])]
    n = len(piece.timings)
    if not titles or not n:
        return []
    out = []
    for k, title in enumerate(titles):
        idx = min(n - 1, (k * n) // len(titles))
        out.append(f"{_mmss(piece.timings[idx])} {title}")
    return out
