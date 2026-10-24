"""Style samples for the founder: the same two scenes drawn in several picture styles, to choose a look (22 Oct 2026).

python scripts/style_samples.py [--out out/style-samples]
About ₹3 a picture (18 pictures); spend is counted in its own file so the day's video budget is untouched.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import art  # noqa: E402
from engine.config import ASSETS_DIR, CONTENT_DIR  # noqa: E402

STYLES = {
    "doodle": (CONTENT_DIR / "prompts" / "style-sglearning.txt").read_text().strip(),
    "3d-film": "3D animated feature-film look, soft global illumination, rounded stylised characters with big expressive eyes, "
               "detailed fabric and skin textures, cinematic depth of field, warm golden-hour sunlight",
    "flat-vector": "clean flat vector illustration, simple geometric shapes, bold limited colour palette, no outlines, subtle gradients, "
                   "modern explainer-video look",
    "watercolour": "hand-painted watercolour storybook illustration, soft colour washes, visible paper grain, gentle pencil lines",
    "painted-anime": "soft hand-painted 2D animation style, lush painted backgrounds, gentle expressive faces, warm nostalgic light",
    "indian-comic": "classic Indian comic book illustration, bold ink outlines, flat vivid colours, halftone shading, 1980s printed-comic feel",
    "clay": "claymation stop-motion look, characters sculpted from plasticine with visible fingerprints and soft clay texture, "
            "miniature handmade set, soft studio light",
    "papercut": "layered paper cut-out collage, textured coloured paper, visible cut edges and soft shadows between the layers",
    "madhubani": "Indian Madhubani folk-art painting, intricate fine line patterns, bold natural colours, decorative borders filling every space",
}

SCENES = {
    "shop": ("Papa, an Indian kirana shop owner in his late sixties with a grey moustache, white kurta and reading glasses, stands behind his "
             "shop counter with glass jars of sweets, a steel weighing scale and stacked biscuit packets; his granddaughter Beti, about ten, "
             "leans over the counter showing him something on her phone; Papa's eyebrows shoot up in surprise; busy Indian street, warm evening light",
             ["papa.png", "beti.png"]),
    "myth": ("SG, an Indian man in his early forties with short wavy black hair and a short dark beard, sits under a huge banyan tree at dusk "
             "telling an ancient story to three village children sitting cross-legged on the ground; behind them the ruins of an old carved "
             "stone temple; a small oil lamp glowing; sense of wonder on the children's faces",
             ["sg.png"]),
}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="out/style-samples")
    a = ap.parse_args(argv)
    out = Path(a.out)
    spend = out / "spend.json"
    failed = []
    for scene, (text, refs) in SCENES.items():
        ref_paths = [ASSETS_DIR / "cast" / r for r in refs if (ASSETS_DIR / "cast" / r).exists()]
        for name, style in STYLES.items():
            prompt = (f"{text}. Keep the characters recognisable from the reference pictures (same face, hair and clothes) but draw them "
                      f"entirely in this style: {style}. No text, no letters, no numbers, no logos.")
            try:
                art.paint(prompt, out / f"{scene}-{name}.png", refs=ref_paths, aspect="4:5", spend=spend)
                print(f"drew {scene}-{name}", flush=True)
            except Exception as e:                        # one refused picture never stops the rest
                failed.append(f"{scene}-{name}: {type(e).__name__}: {str(e)[:160]}")
                print(f"FAILED {failed[-1]}", flush=True)
    print(f"done: {len(SCENES) * len(STYLES) - len(failed)} drawn, {len(failed)} failed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
