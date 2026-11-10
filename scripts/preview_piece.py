"""A PREVIEW of one existing Short in the new opening style, sent to the founder's Telegram and never uploaded (founder, 10 Nov 2026:
"do all 6 recommendations"; he approves the look before the scheduled video is replaced).

    python scripts/preview_piece.py 2026-11-16-arthvan-short out/preview

Uses the piece's own script and the founder's clip in inbox/intro/, paints every picture in the realistic style, builds the full-screen
frame (pills, AI tag) and puts the founder, cut out, over the moving pictures. Nothing in pieces/ or out/<id>/ is touched.
"""
import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import art, intro, opening, pieces, pipeline, storyframe, voice  # noqa: E402
from engine.config import ROOT, VIDEO  # noqa: E402


def main(argv=None) -> int:
    args = argv or sys.argv[1:]
    piece = copy.deepcopy(pieces.load(args[0], ROOT))
    out = Path(args[1]) / piece.id
    out.mkdir(parents=True, exist_ok=True)
    if not opening.is_trial(piece):
        print(f"{piece.id} is outside the new-opening test window (content/hero-test.json)")
        return 2
    size = VIDEO["short"]
    voice_id = (piece.topic or {}).get("voice") or "voice_7o0kddoq6q2z"
    lines, panels = [], []
    for i, sc in enumerate(piece.script["scenes"]):
        wav = out / "vo" / f"line{i:02d}.wav"
        wav.parent.mkdir(parents=True, exist_ok=True)
        lines.append((wav, voice.say(sc["vo"], voice_id, wav, plain=True)))
        prompt = (sc.get("visual") or {}).get("prompt") or piece.script["hook"]
        full, aspect = pipeline.panel_request(piece, prompt, True)
        panels.append(art.paint(full, out / f"visual{i:02d}.png", aspect=aspect))
    video = storyframe.build(piece, lines, panels, size, out)
    clip = ROOT / "inbox" / "intro" / f"{piece.id}.mp4"
    if clip.exists():
        video = intro.compose(piece, clip, out, size)
    print(f"made {video} ({intro.duration(video):.1f} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
