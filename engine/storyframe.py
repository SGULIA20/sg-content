"""The illustrated-story frame: black title band on top (17 %), the drawn panel with a slow push-in (66 %), the handle, and the narration as a
serif caption on the black band below (17 %). One voice line per panel; music bed; loudness-normalised (story format, 20 Oct 2026)."""
import html
import re
import subprocess
from pathlib import Path

from . import assemble, captions, cards, layers, lint, music, opening
from .config import CHANNELS, STORY_MAX_S, VIDEO

FPS = VIDEO["fps"]
TOP, PANEL, BOTTOM = 0.17, 0.66, 0.17                        # long videos (16:9)
SHADE_H, CAP_H = 560, 420                                    # Shorts (founder, 25 Oct 2026, C): the picture runs to the bottom of the screen,
                                                             # a soft shadow at the foot, big bold captions on it, key words in yellow
# Instagram and YouTube draw their own buttons over a Short (founder, 2 Nov 2026: the label and badge were cut at the screen edges and the
# captions sat under Instagram's name and caption text): keep our text inside the safe zone
SAFE_SIDE = 120                                              # px kept clear on the left and right (phones crop the sides; the like column)
LIFT = 300                                                   # captions sit this far above the bottom (Instagram's name, caption and audio line)
TITLE_PAD_SHORT = 150                                        # the title clears Instagram's back arrow and camera button
HANDLE = "@sanjeev_gulia"
FULL_TOP = 170                                               # full-screen Shorts: the badge and the tag start here, clear of the apps' top buttons
LONG_CAP_H, LONG_SHADE_H, LONG_TOP, LONG_SIDE = 230, 380, 50, 70   # full-screen long videos (16:9): captions on a soft shade at the foot
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
    from .config import VOICE_CREDIT
    png = cards.render("storyend", {**brand(piece.channel), "question": (piece.script or {}).get("end_question", ""), "logo_path": logo(piece.channel, 320),
                                    "credit": VOICE_CREDIT.get(piece.channel, "")},
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


def caption_html(text: str, keyword: str = "") -> str:
    """Numbers (and the title's keyword) in yellow; everything else escaped."""
    kw = keyword.lower().strip()
    out = []
    for tok in re.split(r"(\s+)", text):
        bare = re.sub(r"[^\w₹%.,]", "", tok).lower()
        hit = bool(re.search(r"\d|₹|%", tok)) or (kw and bare.strip(".,") == kw)
        out.append(f"<b>{html.escape(tok)}</b>" if hit and tok.strip() else html.escape(tok))
    return "".join(out)


def scene(panel: Path, seconds: float, size: tuple, out: Path, title_png: Path, cue_overlays: list, chip: Path | None = None,
          logo_png: Path | None = None, watermark_png: Path | None = None, punch: bool = False, shade_png: Path | None = None,
          full: bool = False, camera: tuple | None = None, shade_y: int | None = None, top: int | None = None, side: int | None = None) -> Path:
    """Panel with push-in below the title band; long videos keep a black caption band below, Shorts (shade_png given) run the
    picture to the bottom with a shadow under the captions. Optional evidence chip, caption cues overlaid."""
    w, h = size
    py = 0 if full else int(h * TOP)                         # full: the picture fills the screen, no title band (the new-opening test, 10 Nov 2026)
    ph = h - py if shade_png is not None else int(h * PANEL)
    if full and shade_png is None:
        ph = h                                               # a full-screen frame with no shade (never the banded layout)
    top = top if top is not None else (FULL_TOP if full else py + 30)       # where the chip and the badge sit
    side = side if side is not None else SAFE_SIDE
    frames = max(1, int(round(seconds * FPS)))
    if Path(panel).suffix == ".mp4":                          # a moving news card (2 Nov 2026): already animated, no push-in
        chain = (f"[0:v]scale={w}:{ph}:force_original_aspect_ratio=increase,crop={w}:{ph},fps={FPS},setsar=1,"
                 f"pad={w}:{h}:0:{py}:black[base];[base][1:v]overlay=0:0:shortest=1[t]")
        inputs = ["-stream_loop", "-1", "-i", str(panel), "-loop", "1", "-i", str(title_png)]
    else:
        zx, xx, yx = camera if camera else (zoom_expr(seconds, punch), "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)")
        chain = (f"[0:v]scale={w * 2}:{ph * 2}:force_original_aspect_ratio=increase,crop={w * 2}:{ph * 2},"
                 f"zoompan=z='{zx}':d={frames}:x='{xx}':y='{yx}':s={w}x{ph}:fps={FPS},"
                 f"pad={w}:{h}:0:{py}:black[base];[base][1:v]overlay=0:0:shortest=1[t]")
        inputs = ["-loop", "1", "-i", str(panel), "-loop", "1", "-i", str(title_png)]
    last, k0 = "[t]", 2
    if watermark_png is not None:
        wm = int(min(w, ph) * 0.34)
        inputs += ["-loop", "1", "-i", str(watermark_png)]
        chain += (f";[{k0}:v]scale={wm}:{wm},format=rgba,colorchannelmixer=aa={WATERMARK_ALPHA}[wm];"
                  f"{last}[wm]overlay={(w - wm) // 2}:{py + (ph - wm) // 2}:shortest=1[x{k0}]")
        last, k0 = f"[x{k0}]", k0 + 1
    if shade_png is not None:
        inputs += ["-loop", "1", "-i", str(shade_png)]
        chain += f";{last}[{k0}:v]overlay=0:{shade_y if shade_y is not None else h - SHADE_H - LIFT}:shortest=1[x{k0}]"
        last, k0 = f"[x{k0}]", k0 + 1
        spots = ((chip, side, top), (logo_png, w - LOGO_PX - side, top))   # inside the safe zone, never under the captions
    else:
        spots = ((chip, w - 400 - 30, py + 30), (logo_png, w - LOGO_PX - 26, py + ph - LOGO_PX - 26))
    for extra, x, y in spots:
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


def geometry(size: tuple, short: bool, full: bool) -> dict:
    """Where things sit: the caption card's size and top edge, the shade's size and top edge (None: no shade), and the top/side of the
    badge row. Old long videos keep the black caption band; Shorts and full-screen longs put captions on a shade over the picture."""
    w, h = size
    band_h = int(h * TOP)
    if short:
        return {"cap": (w, CAP_H), "cap_y": h - CAP_H - LIFT, "shade": (w, SHADE_H + LIFT), "shade_y": h - SHADE_H - LIFT,
                "top": FULL_TOP if full else band_h + 30, "side": SAFE_SIDE}
    if full:
        return {"cap": (w, LONG_CAP_H), "cap_y": h - LONG_CAP_H - 24, "shade": (w, LONG_SHADE_H), "shade_y": h - LONG_SHADE_H,
                "top": LONG_TOP, "side": LONG_SIDE}
    return {"cap": (w, band_h), "cap_y": h - band_h, "shade": None, "shade_y": 0, "top": band_h + 30, "side": 30}


CAMERA_PATHS = ("push", "glide", "pull", "rise")             # full-screen long videos: a strong pan or zoom per scene, done by ffmpeg (fast)


def camera_expr(path: str, frames: int, direction: int = 1) -> tuple:
    """zoompan's (z, x, y) for a camera path over `frames` frames."""
    n = max(1, frames)
    centre_x, centre_y = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    if path == "push":
        return f"min(1.02+{0.26 / n:.6f}*on,1.28)", centre_x, centre_y
    if path == "pull":
        return f"max(1.28-{0.24 / n:.6f}*on,1.04)", centre_x, centre_y
    if path == "rise":
        return "1.18", centre_x, f"(ih-ih/zoom)*(1-on/{n})"
    go = f"on/{n}" if direction >= 0 else f"(1-on/{n})"
    return "1.18", f"(iw-iw/zoom)*{go}", centre_y


def blank_png(out: Path, w: int) -> Path:
    from PIL import Image
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", (w, 8), (0, 0, 0, 0)).save(out)
    return out


INTRO_BG = "intro-bg.mp4"
INTRO_BG_S = 6.5                                             # each of the first two pictures, so the pair outlasts a 12-second clip


def moving_depths(panels: list):
    """A depth map per still picture (None for a clip), or None when the depth tool is not installed (the slow zoom is used then)."""
    from . import depthmove
    if not depthmove.available():
        return None
    stills = [i for i, p in enumerate(panels) if Path(p).suffix.lower() != ".mp4"]
    try:
        found = depthmove.estimate([panels[i] for i in stills])
    except Exception as e:                                          # the model could not be fetched: a plain zoom is better than no Reel
        print(f"depth movement off ({type(e).__name__}: {str(e)[:120]})", flush=True)
        return None
    out = [None] * len(panels)
    for i, d in zip(stills, found):
        out[i] = d
    return out


def intro_background(piece, panels: list, size: tuple, out_dir: Path, title_png: Path, shade, badge, pills: dict, depths=None) -> Path | None:
    """The first two pictures, full-screen and moving, with the badge and the AI tag but no captions: the founder's cut-out stands on it."""
    idx = [i for i, p in enumerate(panels[:2]) if Path(p).suffix.lower() != ".mp4"]
    if not idx:
        return None
    clips = []
    for k, i in enumerate(idx):
        panel = panels[i]
        if depths and depths[i] is not None:
            from . import depthmove
            panel = depthmove.move(panel, depths[i], INTRO_BG_S, size, out_dir / f"introbgmove{k}.mp4", fps=FPS, direction=1 if k % 2 == 0 else -1,
                                   path=depthmove.PATHS[k % len(depthmove.PATHS)])
        extra = [(pills["tag"], SAFE_SIDE, FULL_TOP, 0.0, INTRO_BG_S)] if "tag" in pills else []
        clips.append(scene(panel, INTRO_BG_S, size, out_dir / f"introbg{k}.mp4", title_png, extra, logo_png=badge, punch=(k == 0),
                           shade_png=shade, full=True))
    listing = out_dir / "introbg.txt"
    listing.write_text("".join(f"file '{c.resolve()}'\n" for c in clips))
    out = out_dir / INTRO_BG
    _run(["-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy", str(out)])
    for c in [*clips, *out_dir.glob("introbgmove*.mp4")]:
        c.unlink(missing_ok=True)
    listing.unlink(missing_ok=True)
    return out


def build(piece, lines: list, panels: list, size: tuple, out_dir: Path) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    w, h = size
    band_h = int(h * TOP)
    title = (piece.script or {}).get("title") or (piece.script or {}).get("hook", "")
    short = piece.kind == "short"
    title_png = cards.render("storytitle", {"title_html": title_html(title), **brand(piece.channel), "pad": TITLE_PAD_SHORT if short else 60,
                                            "strip": "none" if short else "flex"}, out_dir / "title.png", (w, band_h))
    full = opening.is_trial(piece)                                   # the new style (Shorts and longs): full-screen picture, pills, no band, no centre watermark
    geo = geometry(size, short, full)
    pills = opening.render_pills(piece, out_dir / "pills", size, cards.render) if full else {}
    if full:
        title_png = blank_png(out_dir / "blank.png", w)
    # founder, 22 Oct 2026: the narration is never sped up or cut to fit; a story takes the time it takes (YouTube Shorts allow 3 minutes)
    voice_wav = out_dir / "voice.wav"
    starts = assemble._voice_track(lines, voice_wav)
    piece.timings = starts
    durations = [d + assemble.PAD_S for _w, d in lines]
    clips, all_cues = [], []
    bottom_y = geo["cap_y"]
    shade = cards.render("storyshade", {}, out_dir / "shade.png", geo["shade"]) if geo["shade"] else None
    keyword = (re.search(r"\*(.+?)\*", title) or [None, ""])[1]
    badge = logo(piece.channel)
    big_badge = logo(piece.channel, 600)
    layers_on = short and not full and layers.apply(piece)               # the painted Shorts' layer test (engine/layers.py); the full-screen frame has pills
    n_scenes = len(panels)
    depths = moving_depths(panels) if (full and short) else None # 3D-film movement on every Short picture when the depth tool is installed
    for i, (panel, dur, (wav, d), start, scene_d) in enumerate(zip(panels, durations, lines, starts, piece.script["scenes"])):
        if depths and depths[i] is not None:
            from . import depthmove
            panel = depthmove.move(panel, depths[i], dur, size, out_dir / f"move{i:02d}.mp4", fps=FPS, direction=1 if i % 2 == 0 else -1,
                                   path=depthmove.PATHS[i % len(depthmove.PATHS)])
        cues = captions.split(scene_d["vo"], d)
        all_cues += captions.offset(cues, start)
        overlays = []
        if layers_on:
            overlays += layers.scene_overlays(scene_d["vo"], i, n_scenes, size, out_dir / "layers", top=band_h, side=SAFE_SIDE,
                                              chart_y=band_h + 230, dur=dur)
        for s, e, text in cues:
            png = out_dir / "cues" / f"cap{i:02d}-{int(s * 100):05d}.png"
            if not png.exists():
                if short or full:
                    cards.render("storycap2", {"text_html": caption_html(text, keyword)}, png, geo["cap"])
                else:
                    cards.render("storycap", {"text": text}, png, (w, band_h))
            overlays.append((png, 0, bottom_y, s, e))
        overlays += opening.frame_overlays(piece, i, dur, size, pills, geo["top"], geo["side"], LOGO_PX) if full else []
        chip = None
        if piece.channel == "arthvan" and scene_d.get("label") in lint.MYTH_LABELS and i not in pills:
            chip = out_dir / f"label-{scene_d['label']}.png"
            if not chip.exists():
                cards.render("label", {"label": scene_d["label"]}, chip, (400, 90))
        if full and chip is not None:                                # on the pill's row, under the badge
            overlays.append((chip, geo["side"], geo["top"] + LOGO_PX + 18, 0.0, dur)); chip = None
        cam = None
        if full and not short and Path(panel).suffix.lower() != ".mp4":      # a long: a strong pan or zoom, a different path each scene
            cam = camera_expr(CAMERA_PATHS[i % len(CAMERA_PATHS)], max(1, int(round(dur * FPS))), 1 if (i // len(CAMERA_PATHS)) % 2 == 0 else -1)
        clips.append(scene(panel, dur, size, out_dir / f"scene{i:02d}.mp4", title_png, overlays, chip=chip, logo_png=badge,
                           watermark_png=None if full else big_badge, punch=(i == 0 and short), shade_png=shade, full=full, camera=cam,
                           shade_y=geo["shade_y"] if shade else None, top=geo["top"], side=geo["side"]))
    if full and short:                                               # the pictures that move behind the founder in his intro (engine/intro.py)
        intro_background(piece, panels, size, out_dir, title_png, shade, badge, pills, depths)
        for f in out_dir.glob("move*.mp4"):
            f.unlink(missing_ok=True)
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
                              f"loudnorm=I={assemble.MUSIC_LUFS}:TP=-6:LRA=7[m];[v][m]amix=inputs=2:duration=longest:normalize=0,"
                              f"apad=whole_dur={total:.3f},loudnorm=I={assemble.MIX_LUFS}:TP=-1.5:LRA=11[aout]"),
          "-map", "0:v", "-map", "[aout]", "-t", f"{total:.3f}", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-movflags", "+faststart", str(out)])
    return out
