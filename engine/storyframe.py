"""The illustrated-story frame: black title band on top (17 %), the drawn panel with a slow push-in (66 %), the handle, and the narration as a
serif caption on the black band below (17 %). One voice line per panel; music bed; loudness-normalised (story format, 20 Oct 2026)."""
import html
import re
import subprocess
from pathlib import Path

from . import assemble, captions, cards, lint, music
from .config import CHANNELS, STORY_MAX_S, VIDEO

FPS = VIDEO["fps"]
TOP, PANEL, BOTTOM = 0.17, 0.66, 0.17
HANDLE = "@sanjeev_gulia"
END_S = 3.0                                                  # branded end card: channel name, tagline, subscribe, the question
LOGO_PX = 150                                                # round channel badge in the panel's bottom-right corner, every frame
WATERMARK_ALPHA = 0.10                                       # the same badge, large and faint, in the centre of every panel: a crop cannot remove it
PUNCH_S, PUNCH_ZOOM = 1.3, 1.35                            # founder, 25 Oct 2026: the first 1.3 s are a close-up that moves, then a cut to
                                                             # the whole picture; a still first 3 seconds read as a slideshow and get swiped
LOGO_TEXT = {"sglearning": ("SG", "Learning"), "arthvan": ("SG", "Myth World")}
LOGO_DIR = Path(__file__).resolve().parent.parent / "assets" / "logo"


def logo(channel: str, px: int = LOGO_PX, out_dir: Path | None = None) -> Path:
    """The channel's round monogram badge as a transparent PNG (drawn in code: the YouTube avatars are photos, not marks)."""
    top, bottom = LOGO_TEXT[channel]
    out = Path(out_dir or LOGO_DIR) / f"{channel}-{px}.png"
    if not out.exists():
        cards.render("logo", {"top": top, "bottom": bottom, "ring": max(3, px // 30), "shadow": max(2, px // 50),
                              "top_px": int(px * 0.40), "bottom_px": int(px * 0.11)}, out, (px, px))
    return out


def brand(channel: str) -> dict:
    """What every frame and the end card say about the channel (the founder: name the channel like the app Reels name the app)."""
    ch = CHANNELS[channel]
    return {"channel": ch.display_name, "tagline": ch.niche, "handle": HANDLE}


def end_card(piece, size: tuple, out_dir: Path) -> Path:
    """A still end card held for END_S seconds, same bands and colours as the story."""
    w, h = size
    png = cards.render("storyend", {**brand(piece.channel), "question": (piece.script or {}).get("end_question", ""), "logo_path": logo(piece.channel, 320)},
                       Path(out_dir) / "end.png", size)
    out = Path(out_dir) / "end.mp4"
    _run(["-loop", "1", "-framerate", str(FPS), "-i", str(png), "-t", f"{END_S:.2f}", "-vf", f"scale={w}:{h},format=yuv420p",
          "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-r", str(FPS), str(out)])
    return out


def title_html(title: str) -> str:
    """*word* becomes the yellow keyword span; everything else is escaped."""
    parts = re.split(r"\*(.+?)\*", title)
    out = []
    for i, part in enumerate(parts):
        out.append(f'<span class="k">{html.escape(part)}</span>' if i % 2 else html.escape(part))
    return "".join(out)


def _run(args: list) -> None:
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


def zoom_expr(seconds: float, punch: bool) -> str:
    """zoompan's zoom: the slow push-in; with `punch`, a moving close-up for PUNCH_S, then a cut to the full picture."""
    slow = f"min(1+{assemble.ZOOM_PER_FRAME}*on,{assemble.ZOOM_MAX})"
    n1 = int(round(PUNCH_S * FPS))
    if not punch or seconds < PUNCH_S + 0.8:
        return f"min(zoom+{assemble.ZOOM_PER_FRAME},{assemble.ZOOM_MAX})"
    return f"if(lt(on,{n1}),{PUNCH_ZOOM}+0.004*on,min(1+{assemble.ZOOM_PER_FRAME}*(on-{n1}),{assemble.ZOOM_MAX}))"


def scene(panel: Path, seconds: float, size: tuple, out: Path, title_png: Path, cue_overlays: list, chip: Path | None = None,
          logo_png: Path | None = None, watermark_png: Path | None = None, punch: bool = False) -> Path:
    """Panel with push-in in the middle band, black bands top and bottom, title band, optional evidence chip, caption cues overlaid."""
    w, h = size
    ph = int(h * PANEL)
    py = int(h * TOP)
    frames = max(1, int(round(seconds * FPS)))
    chain = (f"[0:v]scale={w * 2}:{ph * 2}:force_original_aspect_ratio=increase,crop={w * 2}:{ph * 2},"
             f"zoompan=z='{zoom_expr(seconds, punch)}':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={w}x{ph}:fps={FPS},"
             f"pad={w}:{h}:0:{py}:black[base];[base][1:v]overlay=0:0:shortest=1[t]")
    inputs = ["-loop", "1", "-i", str(panel), "-loop", "1", "-i", str(title_png)]
    last, k0 = "[t]", 2
    if watermark_png is not None:
        wm = int(min(w, ph) * 0.34)
        inputs += ["-loop", "1", "-i", str(watermark_png)]
        chain += (f";[{k0}:v]scale={wm}:{wm},format=rgba,colorchannelmixer=aa={WATERMARK_ALPHA}[wm];"
                  f"{last}[wm]overlay={(w - wm) // 2}:{py + (ph - wm) // 2}:shortest=1[x{k0}]")
        last, k0 = f"[x{k0}]", k0 + 1
    for extra, x, y in ((chip, w - 400 - 30, py + 30), (logo_png, w - LOGO_PX - 26, py + ph - LOGO_PX - 26)):
        if extra is None:
            continue
        inputs += ["-loop", "1", "-i", str(extra)]
        chain += f";{last}[{k0}:v]overlay={x}:{y}:shortest=1[x{k0}]"
        last, k0 = f"[x{k0}]", k0 + 1
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
    title_png = cards.render("storytitle", {"title_html": title_html(title), **brand(piece.channel)}, out_dir / "title.png", (w, band_h))
    # founder, 22 Oct 2026: the narration is never sped up or cut to fit; a story takes the time it takes (YouTube Shorts allow 3 minutes)
    voice_wav = out_dir / "voice.wav"
    starts = assemble._voice_track(lines, voice_wav)
    piece.timings = starts
    durations = [d + assemble.PAD_S for _w, d in lines]
    clips, all_cues = [], []
    bottom_y = h - band_h
    badge = logo(piece.channel)
    big_badge = logo(piece.channel, 600)
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
        clips.append(scene(panel, dur, size, out_dir / f"scene{i:02d}.mp4", title_png, overlays, chip=chip, logo_png=badge, watermark_png=big_badge,
                           punch=(i == 0 and piece.kind == "short")))
    (out_dir / "captions.ass").write_text(captions.ass(all_cues, size))
    clips.append(end_card(piece, size, out_dir))
    concat = out_dir / "scenes.txt"
    concat.write_text("".join(f"file '{c.resolve()}'\n" for c in clips))
    total = sum(durations) + END_S
    bed = music.bed("light", total + 5)
    out = out_dir / ("reel.mp4" if piece.kind == "short" else "long.mp4")
    _run(["-f", "concat", "-safe", "0", "-i", str(concat), "-i", str(voice_wav), "-stream_loop", "-1", "-i", str(bed),
          "-filter_complex", (f"[1:a]aresample=48000,apad=whole_dur={total:.3f},loudnorm=I={assemble.VOICE_LUFS}:TP=-1.5:LRA=11[v];"
                              f"[2:a]aresample=48000,atrim=0:{total:.3f},asetpts=PTS-STARTPTS,afade=t=out:st={max(0.0, total - 2):.2f}:d=2,"
                              f"loudnorm=I={assemble.MUSIC_LUFS}:TP=-6:LRA=7[m];[v][m]amix=inputs=2:duration=longest:normalize=0,apad=whole_dur={total:.3f},loudnorm=I={assemble.MIX_LUFS}:TP=-1.5:LRA=11[aout]"),
          "-map", "0:v", "-map", "[aout]", "-t", f"{total:.3f}", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-movflags", "+faststart", str(out)])
    return out
