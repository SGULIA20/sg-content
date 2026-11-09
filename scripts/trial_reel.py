"""A complete TRIAL Short with the new opening style (founder, 9 Nov 2026: "I want to see the complete reel trial first").

    python scripts/trial_reel.py content/trial/dwarka.json out/trial/dwarka.mp4 [--offline]

What it shows, in one hand-written Short that is never uploaded: the payoff picture and line first (no talking-head intro in the trial),
realistic AI pictures with a slow push, short data pills drawn by code (place, source, scripture vs archaeology), a mid-hook pivot line,
an "AI visualisation" tag, and a last line that is cut off and leads straight back into the first.

--offline uses plain pictures and a tone for the voice (no API calls): only to check the assembly.
"""
import json
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import art, assemble, cards, depthmove, voice  # noqa: E402

SIZE = (1080, 1920)
PILL_H = 90
TAG_TEXT = "AI visualisation"


def _tone(path: Path, seconds: float) -> float:
    rate = 24000
    t = np.linspace(0, seconds, int(rate * seconds), endpoint=False)
    pcm = (np.sin(2 * np.pi * 220 * t) * 3000).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate); w.writeframes(pcm.tobytes())
    return seconds


def _plain_picture(path: Path, n: int) -> Path:
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (1080, 1920), (20 + 25 * n % 200, 60, 110))
    ImageDraw.Draw(im).text((60, 60), f"picture {n}", fill="white")
    im.save(path)
    return path


def _cues(text: str, start: float, end: float) -> list:
    """Caption chunks of up to five words, spread over the line's time by letter count."""
    words, chunks, cur = text.split(), [], []
    for w in words:
        cur.append(w)
        if len(cur) >= 5 or w.endswith((",", ".", "?", "!", "…")):
            chunks.append(" ".join(cur)); cur = []
    if cur:
        chunks.append(" ".join(cur))
    total = sum(len(c) for c in chunks) or 1
    out, t = [], start
    for c in chunks:
        e = t + (end - start) * len(c) / total
        out.append((round(t, 3), round(e, 3), c))
        t = e
    return out


def build(spec: dict, out: Path, offline: bool = False, depth: bool = False) -> Path:
    work = out.parent / (out.stem + "-work")
    work.mkdir(parents=True, exist_ok=True)
    voice_id = spec.get("voice", "voice_7o0kddoq6q2z")
    lines, pics = [], []
    for i, sc in enumerate(spec["scenes"]):
        wav = work / f"line{i:02d}.wav"
        secs = _tone(wav, 2.4 + 0.12 * len(sc["say"].split())) if offline else voice.say(sc["say"], voice_id, wav, plain=True)
        lines.append((wav, secs))
        pic = work / f"pic{i:02d}.png"
        if offline:
            _plain_picture(pic, i)
        else:
            art.paint(art.hero_style_prompt(sc["picture"] + art.HERO_FRAME_NOTE), pic, aspect="9:16")
        pics.append(pic)
    depths = []
    if depth:
        depths = [depthmove.fake_depth((1080, 1920)) for _ in pics] if offline else depthmove.estimate(pics)
    lines, factor = assemble.fit_short(lines, work / "fast")
    starts = assemble._voice_track(lines, work / "voice.wav")
    band_h, band_y = assemble.caption_band(SIZE)
    tag = cards.render("pill", {"kind": "ai", "text": TAG_TEXT}, work / "tag.png", (460, 60))
    clips = []
    for i, ((wav, secs), sc) in enumerate(zip(lines, spec["scenes"])):
        dur = secs + assemble.PAD_S
        overlays = [(tag, SIZE[0] - 460 - 30, SIZE[1] - 140)]
        if sc.get("pill"):
            png = cards.render("pill", {"kind": sc.get("pill_kind", ""), "text": sc["pill"]}, work / f"pill{i:02d}.png", (SIZE[0] - 80, PILL_H))
            overlays.append((png, 40, 130, 0.15, min(dur, 3.6)))
        for png, s, e in assemble.cue_pngs(_cues(sc["say"], 0.0, secs), SIZE, work / "cues"):
            overlays.append((png, 0, band_y, s, e))
        source = pics[i]
        if depth:                                                      # 3D-film movement: near parts drift more than far ones
            source = depthmove.move(pics[i], depths[i], dur, SIZE, work / f"move{i:02d}.mp4", direction=1 if i % 2 == 0 else -1)
        clips.append(assemble.scene_clip(source, dur, SIZE, work / f"clip{i:02d}.mp4", overlays=overlays))
    listing = work / "clips.txt"
    listing.write_text("".join(f"file '{c.resolve()}'\n" for c in clips))
    silent = work / "silent.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy", str(silent)], check=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(silent), "-i", str(work / "voice.wav"), "-c:v", "copy", "-c:a", "aac",
                    "-af", f"loudnorm=I={assemble.MIX_LUFS}:TP=-1.5:LRA=11", "-shortest", str(out)], check=True)
    return out


def main(argv=None) -> int:
    args = [a for a in (argv or sys.argv[1:]) if not a.startswith("--")]
    spec = json.loads(Path(args[0]).read_text())
    out = Path(args[1])
    out.parent.mkdir(parents=True, exist_ok=True)
    flags = argv or sys.argv[1:]
    build(spec, out, offline="--offline" in flags, depth="--depth" in flags)
    print(f"made {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
