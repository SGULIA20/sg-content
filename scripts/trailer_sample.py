"""A SAMPLE of the suspense trailer Story for one long video, sent to the founder's Telegram; nothing is posted or saved to the piece
(founder, 16 Nov 2026: "Can I see sample then push").

    python scripts/trailer_sample.py 2026-11-22-arthvan-long out/trailer-sample

Paints five of the long's own scenes afresh (the long's pictures are not kept after upload), has the writer write the question lines,
voices them with the narrator and builds the 20-second Story exactly as the pipeline will.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import art, opening, pieces, pipeline, teaser, telegram  # noqa: E402
from engine.config import ROOT  # noqa: E402

PICTURES = 5


def main(argv=None) -> int:
    args = argv or sys.argv[1:]
    piece = pieces.load(args[0], ROOT)
    out = Path(args[1]) / piece.id
    out.mkdir(parents=True, exist_ok=True)
    scenes = [sc for sc in piece.script["scenes"] if (sc.get("visual") or {}).get("prompt")]
    picks = [scenes[int(len(scenes) * k / (PICTURES + 1))] for k in range(1, PICTURES + 1)]      # spread over the whole video
    panels = []
    for i, sc in enumerate(picks):
        full, aspect = pipeline.panel_request(piece, sc["visual"]["prompt"], opening.is_trial(piece))
        panels.append(art.paint(full, out / f"visual{i:02d}.png", aspect=aspect))
    lines = []
    ask = teaser.intro_ask()
    video = teaser.suspense_trailer(piece, panels, out, ask=lambda prompt: lines.append(ask(prompt)) or lines[-1])
    if video is None:
        print("no trailer: the writer gave no usable lines", lines[-1][:300] if lines else "")
        return 1
    print("lines:", lines[-1][:400])
    print(telegram.send_file(video, f"SAMPLE trailer Story for {piece.id} (suspense questions, 20 s at most). Not posted. "
                                    "Tell Claude 'yes push' or what to change."))
    return 0


if __name__ == "__main__":
    sys.exit(main())
