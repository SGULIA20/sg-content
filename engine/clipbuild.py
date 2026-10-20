"""Build a video from the founder's Gemini presenter clips: normalise, overlay cards and strips, caption from the pack narration, music bed, concat,
then QA, thumbnail and upload (docs/spec-gemini-clips.md §5-6)."""
import json
import subprocess
from pathlib import Path

import numpy as np

from . import assemble, captions, cards, lint, music, qa, slots, youtube
from .config import VIDEO
from .pieces import Piece

FPS = VIDEO["fps"]
SHORT_MAX_S = 60.0
SILENCE_DB = -40


def _run(args: list) -> None:
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


def _duration(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)], capture_output=True, text=True, check=True).stdout
    return float(json.loads(out)["format"]["duration"])


def kind_for(seconds: float) -> str:
    return "short" if seconds <= SHORT_MAX_S else "long"


def normalise(clip: Path, size: tuple, out: Path) -> Path:
    """1080×1920 (or 1920×1080), 30 fps, stereo 48 kHz AAC, voice at −16 LUFS; leading/trailing silence trimmed."""
    w, h = size
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    vf = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},fps={FPS},format=yuv420p"
    af = (f"silenceremove=start_periods=1:start_threshold={SILENCE_DB}dB:start_silence=0.2,areverse,"
          f"silenceremove=start_periods=1:start_threshold={SILENCE_DB}dB:start_silence=0.2,areverse,aresample=48000,loudnorm=I=-16:TP=-1.5:LRA=11")
    _run(["-i", str(clip), "-vf", vf, "-af", af, "-shortest", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2", str(out)])
    return out


def _overlays(piece: Piece, scene: dict, size: tuple, out_dir: Path, i: int, strips: dict, chips: dict) -> list:
    w, h = size
    out = []
    v = scene.get("visual") or {}
    if v.get("card"):
        chip = cards.render("number", v["card"], out_dir / f"chip{i:02d}.png", (w, h))         # full card rendered, then shown small top-left
        small = out_dir / f"chip{i:02d}-small.png"
        _run(["-i", str(chip), "-vf", f"scale={int(w * 0.46)}:-1", str(small)])
        out.append((small, 40, 40 + 120))
    if piece.channel == "sglearning" and scene.get("facts_used"):
        j = scene["facts_used"][0]
        if j in strips:
            out.append((strips[j], 0, 40))
    if piece.channel == "arthvan" and scene.get("label") in chips:
        out.append((chips[scene["label"]], w - 440, 40))
    return out


def build(piece: Piece, parts: list, clips: list, out_dir: Path) -> Path:
    """Returns reel.mp4 (short) or long.mp4 and sets piece.timings to each part's start time."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    size = VIDEO["short"] if piece.kind == "short" else VIDEO["long"]
    w, h = size
    scenes = piece.script["scenes"]
    # strips and chips once
    strips, by_name = {}, {}
    for sc in scenes:
        for j in sc.get("facts_used", []):
            if j < len(piece.facts) and j not in strips:
                f = piece.facts[j]
                name = f.get("source_name", "Source")
                if name not in by_name:
                    by_name[name] = cards.render("source", {"name": name, "date": f.get("source_date", "")}, out_dir / f"source-{len(by_name)}.png", (w, 120))
                strips[j] = by_name[name]
    chips = {}
    if piece.channel == "arthvan":
        chips = {lab: cards.render("label", {"label": lab}, out_dir / f"label-{lab}.png", (400, 90)) for lab in lint.MYTH_LABELS}
    band, band_y = assemble.caption_band(size)
    # per part: normalise, caption cues, overlays
    segs, starts, t, all_cues = [], [], 0.0, []
    for part, clip in zip(parts, clips):
        i = int(part["scene"])
        scene = scenes[i] if i < len(scenes) else {}
        norm = normalise(clip, size, out_dir / f"norm{part['part']:02d}.mp4")
        dur = _duration(norm)
        cues = captions.split(part["narration"], dur)
        all_cues += captions.offset(cues, t)
        overlays = _overlays(piece, scene, size, out_dir, i, strips, chips)
        overlays += [(png, 0, band_y, s, e) for png, s, e in assemble.cue_pngs(cues, size, out_dir / "cues")]
        seg = out_dir / f"seg{part['part']:02d}.mp4"
        chain, inputs, last = "[0:v]null[base]", ["-i", str(norm)], "[base]"
        for k, ov in enumerate(overlays, start=1):
            inputs += ["-loop", "1", "-i", str(ov[0])]
            window = f":enable='between(t,{ov[3]:.3f},{ov[4]:.3f})'" if len(ov) == 5 else ""
            chain += f";{last}[{k}:v]overlay={ov[1]}:{ov[2]}:shortest=1{window}[o{k}]"
            last = f"[o{k}]"
        _run([*inputs, "-filter_complex", chain, "-map", last, "-map", "0:a", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "copy", str(seg)])
        segs.append(seg); starts.append(round(t, 3)); t += dur
    piece.timings = starts
    (out_dir / "captions.ass").write_text(captions.ass(all_cues, size))
    concat = out_dir / "segs.txt"
    concat.write_text("".join(f"file '{s.resolve()}'\n" for s in segs))
    total = t
    bed = music.bed("calm" if piece.channel == "sglearning" else "epic", total + 5)
    out = out_dir / ("reel.mp4" if piece.kind == "short" else "long.mp4")
    _run(["-f", "concat", "-safe", "0", "-i", str(concat), "-stream_loop", "-1", "-i", str(bed),
          "-filter_complex", (f"[1:a]aresample=48000,atrim=0:{total:.3f},asetpts=PTS-STARTPTS,afade=t=out:st={max(0.0, total - 2):.2f}:d=2,"
                              f"loudnorm=I={assemble.MUSIC_LUFS}:TP=-6:LRA=7[m];[0:a][m]amix=inputs=2:duration=first:normalize=0,loudnorm=I=-16:TP=-1.5:LRA=11[aout]"),
          "-map", "0:v", "-map", "[aout]", "-t", f"{total:.3f}", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-movflags", "+faststart", str(out)])
    return out


def check(video: Path, piece: Piece) -> list:
    """QA for clip builds: everything except caption coverage (captions are generated from the narration itself)."""
    dur = _duration(video)
    target = (piece.topic.get("target_minutes") or 0) * 60 or None
    return [r for r in qa.report(video, piece.kind, voiced_seconds=dur, caption_cues=[(0.0, dur, "x")], target_seconds=target or dur) if not r.startswith("captions")]


def thumbnail(piece: Piece, first_clip: Path, out: Path) -> Path:
    frame = Path(out).with_suffix(".frame.png")
    _run(["-ss", "1", "-i", str(first_clip), "-frames:v", "1", str(frame)])
    title = piece.script["captions"]["youtube"].get("title", "")
    words = [w for w in title.replace("?", "? ").split() if w][:3]
    number = next((c["big_number"] for c in piece.script.get("cards", []) if c.get("big_number")), "")
    size = (1280, 720) if piece.kind == "long" else (1080, 1920)
    return cards.render("thumb", {"words": words, "number": number, "avatar_path": frame}, out, size)


def upload(piece: Piece, video: Path, thumb: Path) -> str:
    import os
    token = youtube.access_token(piece.channel)
    meta = youtube.metadata(piece, slots.publish_at(piece.channel, piece.kind, piece.publish_day), os.environ)
    vid = youtube.upload(token, video, meta)
    youtube.set_thumbnail(token, vid, thumb)
    if os.environ.get("UNLISTED_DAY1") == "1":
        piece.ids["unlisted"] = True
    return vid
