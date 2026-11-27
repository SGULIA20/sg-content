"""A trial Short whose whole body is the founder's own moving film (founder, 27 Nov 2026: "don't wait for tomorrow, let us finish today
to see the trial. Use slow motion filter"). His clips inbox/scenes/<piece id>/clip1.mp4, clip2.mp4 ... are joined into one film; the
film is slowed with motion-smoothed slow motion until it lasts as long as the narration, cut into one stretch per scene, and built by
the normal engine: narrator, captions, pills, music, end card, and his opening clip when inbox/intro/<piece id>.mp4 exists. Sent to
Telegram; never uploaded; nothing committed.

    python scripts/film_trial.py preview-abhimanyu out/film-trial
"""
import copy
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SG_FORCE_NEW_STYLE", "1")     # the full-screen frame, whatever the piece's date

from engine import intro, opening, pieces, storyframe, telegram, voice  # noqa: E402
from engine.config import ROOT, VIDEO  # noqa: E402

SLOWEST = 0.5          # never slower than half speed: beyond that the film is repeated instead


def _run(args: list) -> None:
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


def stretches(durations: list, film_seconds: float) -> tuple:
    """(speed, [(start in the film, length in the film)]) so that scene i shows its own stretch of the film, in order, for exactly its
    narration. speed below 1 is slow motion; it never goes under SLOWEST or over 1 (a film longer than the narration loses its tail)."""
    total = sum(durations)
    speed = max(SLOWEST, min(1.0, film_seconds / total)) if total else 1.0
    out, t = [], 0.0
    for d in durations:
        out.append((round(t, 3), round(d * speed, 3)))
        t += d * speed
    return speed, out


def main(argv=None) -> int:
    args = argv or sys.argv[1:]
    piece = copy.deepcopy(pieces.load(args[0], ROOT))
    out = Path(args[1]) / piece.id
    out.mkdir(parents=True, exist_ok=True)
    src = ROOT / "inbox" / "scenes" / piece.id
    clips = sorted(src.glob("clip*.mp4"))
    if not clips:
        print(f"no clips in {src}"); return 2
    w, h = VIDEO[piece.kind]
    film = out / "film.mp4"
    fw, fh = w * 2 // 3, h * 2 // 3                          # his clips come at 720x1280; the slow motion is worked out at that size (twice as fast), then enlarged
    graph = "".join(f"[{i}:v]scale={fw}:{fh}:force_original_aspect_ratio=increase:flags=lanczos,crop={fw}:{fh},fps=30,setsar=1[v{i}];" for i in range(len(clips)))
    graph += "".join(f"[v{i}]" for i in range(len(clips))) + f"concat=n={len(clips)}:v=1:a=0[v]"
    _run([*sum((["-i", str(c)] for c in clips), []), "-filter_complex", graph, "-map", "[v]", "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", str(film)])
    voice_id = (piece.topic or {}).get("voice") or "voice_7o0kddoq6q2z"
    lines = []
    for i, sc in enumerate(piece.script["scenes"]):
        wav = out / "vo" / f"line{i:02d}.wav"
        wav.parent.mkdir(parents=True, exist_ok=True)
        lines.append((wav, voice.say(sc["vo"], voice_id, wav, plain=True)))
    rate = opening.speed(piece)
    durations = [d / rate for _w, d in lines]
    speed, parts = stretches(durations, intro.duration(film))
    print(f"film {intro.duration(film):.1f} s, narration {sum(durations):.1f} s, played at {speed:.2f}x", flush=True)
    panels = []
    for i, (start, length) in enumerate(parts):
        seg = src / f"{i:02d}.mp4"                               # where storyframe.scene_clips looks for a scene's own film
        slow = (f"setpts=PTS/{speed:.4f},minterpolate=fps=30:mi_mode=mci:mc_mode=aobmc:vsbmc=1:scd=fdiff," if speed < 0.97 else "")
        _run(["-ss", f"{start:.3f}", "-t", f"{length:.3f}", "-i", str(film), "-an", "-vf", f"{slow}scale={w}:{h}:flags=lanczos,fps=30,format=yuv420p",
              "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", str(seg)])
        panels.append(seg)
    video = storyframe.build(piece, lines, panels, (w, h), out)
    clip = ROOT / "inbox" / "intro" / f"{piece.id}.mp4"
    if clip.exists():
        video = intro.compose(piece, clip, out, (w, h))
    print(f"made {video} ({intro.duration(video):.1f} s)", flush=True)
    if os.environ.get("TELEGRAM_BOT_TOKEN"):
        print(telegram.send_file(video, f"TRIAL {piece.id}: the whole body is your moving film, slowed to {speed:.2f}x to fit the narration. "
                                        "Not uploaded. The script is a trial text, not yet fact-checked."))
    return 0


if __name__ == "__main__":
    sys.exit(main())
