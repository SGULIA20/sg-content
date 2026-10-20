"""The illustrated-story frame: black title band on top (17 %), the drawn panel with a slow push-in (66 %), the handle, and the narration as a
serif caption on the black band below (17 %). One voice line per panel; music bed; loudness-normalised (story format, 20 Oct 2026)."""
import html
import re
import subprocess
from pathlib import Path

from . import assemble, captions, cards, lint, music
from .config import STORY_MAX_S, VIDEO

FPS = VIDEO["fps"]
TOP, PANEL, BOTTOM = 0.17, 0.66, 0.17
HANDLE = "@sanjeev_gulia"


def title_html(title: str) -> str:
    """*word* becomes the yellow keyword span; everything else is escaped."""
    parts = re.split(r"\*(.+?)\*", title)
    out = []
    for i, part in enumerate(parts):
        out.append(f'<span class="k">{html.escape(part)}</span>' if i % 2 else html.escape(part))
    return "".join(out)


def _run(args: list) -> None:
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


def scene(panel: Path, seconds: float, size: tuple, out: Path, title_png: Path, cue_overlays: list, chip: Path | None = None) -> Path:
    """Panel with push-in in the middle band, black bands top and bottom, title band, optional evidence chip, caption cues overlaid."""
    w, h = size
    ph = int(h * PANEL)
    py = int(h * TOP)
    frames = max(1, int(round(seconds * FPS)))
    chain = (f"[0:v]scale={w * 2}:{ph * 2}:force_original_aspect_ratio=increase,crop={w * 2}:{ph * 2},"
             f"zoompan=z='min(zoom+{assemble.ZOOM_PER_FRAME},{assemble.ZOOM_MAX})':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={w}x{ph}:fps={FPS},"
             f"pad={w}:{h}:0:{py}:black[base];[base][1:v]overlay=0:0:shortest=1[t]")
    inputs = ["-loop", "1", "-i", str(panel), "-loop", "1", "-i", str(title_png)]
    last = "[t]"
    k0 = 2
    if chip is not None:
        inputs += ["-loop", "1", "-i", str(chip)]
        chain += f";[t][2:v]overlay={w - 400 - 30}:{py + 30}:shortest=1[c]"
        last, k0 = "[c]", 3
    for k, (png, x, y, s, e) in enumerate(cue_overlays, start=k0):
        inputs += ["-loop", "1", "-i", str(png)]
        chain += f";{last}[{k}:v]overlay={x}:{y}:shortest=1:enable='between(t,{s:.3f},{e:.3f})'[o{k}]"
        last = f"[o{k}]"
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    _run([*inputs, "-filter_complex", chain, "-map", last, "-t", f"{frames / FPS:.3f}", "-r", str(FPS),
          "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-an", str(out)])
    return out


def build(piece, lines: list, panels: list, size: tuple, out_dir: Path) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    w, h = size
    band_h = int(h * TOP)
    title = (piece.script or {}).get("title") or (piece.script or {}).get("hook", "")
    title_png = cards.render("storytitle", {"title_html": title_html(title), "handle": HANDLE}, out_dir / "title.png", (w, band_h))
    if piece.kind == "short":
        lines, factor = assemble.fit_short(lines, out_dir / "vo-fit", limit=STORY_MAX_S)
        if factor > 1.0:
            print(f"voice sped up {factor}x to fit the story under {STORY_MAX_S:.0f} s", flush=True)
    voice_wav = out_dir / "voice.wav"
    starts = assemble._voice_track(lines, voice_wav)
    piece.timings = starts
    durations = [d + assemble.PAD_S for _w, d in lines]
    clips, all_cues = [], []
    bottom_y = h - band_h
    for i, (panel, dur, (wav, d), start, scene_d) in enumerate(zip(panels, durations, lines, starts, piece.script["scenes"])):
        cues = captions.split(scene_d["vo"], d)
        all_cues += captions.offset(cues, start)
        overlays = []
        for s, e, text in cues:
            png = out_dir / "cues" / f"cap{i:02d}-{int(s * 100):05d}.png"
            if not png.exists():
                cards.render("storycap", {"text": text}, png, (w, band_h))
            overlays.append((png, 0, bottom_y, s, e))
        chip = None
        if piece.channel == "arthvan" and scene_d.get("label") in lint.MYTH_LABELS:
            chip = out_dir / f"label-{scene_d['label']}.png"
            if not chip.exists():
                cards.render("label", {"label": scene_d["label"]}, chip, (400, 90))
        clips.append(scene(panel, dur, size, out_dir / f"scene{i:02d}.mp4", title_png, overlays, chip=chip))
    (out_dir / "captions.ass").write_text(captions.ass(all_cues, size))
    concat = out_dir / "scenes.txt"
    concat.write_text("".join(f"file '{c.resolve()}'\n" for c in clips))
    total = sum(durations)
    bed = music.bed("light", total + 5)
    out = out_dir / ("reel.mp4" if piece.kind == "short" else "long.mp4")
    _run(["-f", "concat", "-safe", "0", "-i", str(concat), "-i", str(voice_wav), "-stream_loop", "-1", "-i", str(bed),
          "-filter_complex", (f"[1:a]aresample=48000,loudnorm=I={assemble.VOICE_LUFS}:TP=-1.5:LRA=11[v];"
                              f"[2:a]aresample=48000,atrim=0:{total:.3f},asetpts=PTS-STARTPTS,afade=t=out:st={max(0.0, total - 2):.2f}:d=2,"
                              f"loudnorm=I={assemble.MUSIC_LUFS}:TP=-6:LRA=7[m];[v][m]amix=inputs=2:duration=first:normalize=0,loudnorm=I={assemble.MIX_LUFS}:TP=-1.5:LRA=11[aout]"),
          "-map", "0:v", "-map", "[aout]", "-t", f"{total:.3f}", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-movflags", "+faststart", str(out)])
    return out
