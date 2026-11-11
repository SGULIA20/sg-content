"""Write a TRIAL script for one piece with the current rules, and its intro words and avatar prompt; print them and send them to the founder's
Telegram. Nothing is saved, uploaded or changed (founder, 11 Nov 2026: "give me that script ... then we finalise").

    python scripts/trial_script.py 2026-11-17-sglearning-short

Uses the piece's own researched facts and topic. The script is checked by the same gates as production; up to three drafts.
"""
import copy
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SG_FORCE_NEW_STYLE", "1")

from engine import claims, intro, lint, pieces, telegram, writer  # noqa: E402
from engine.config import ROOT  # noqa: E402


def main(argv=None) -> int:
    pid = (argv or sys.argv[1:])[0]
    piece = copy.deepcopy(pieces.load(pid, ROOT))
    banned, hashtags = lint.load_lists()
    library = claims.load_library()
    piece.script = None
    piece.topic.pop("intro", None)
    piece.topic.pop("revise", None)
    sheet = {"facts": piece.facts, "summary": str(piece.topic.get("summary", ""))}
    reasons = []
    for attempt in range(3):
        if reasons:
            piece.topic["revise"] = "; ".join(reasons)
        written = writer.write(piece, sheet, library, hashtags)
        piece.script = written["script"]
        reasons = lint.check_script(piece, banned, []) + lint.check_captions(piece, hashtags)
        print(f"draft {attempt + 1} by {written['writer']}: {'passes the checks' if not reasons else '; '.join(reasons)[:300]}", flush=True)
        if not reasons:
            break
    plan = intro.plan(piece)
    scenes = piece.script["scenes"]
    words = sum(len(sc["vo"].split()) for sc in scenes)
    print("TRIAL_SCRIPT_JSON " + json.dumps({"script": piece.script, "intro": plan, "problems": reasons}, ensure_ascii=False), flush=True)
    body = "\n".join(f"{i + 1}. {sc['vo']}" for i, sc in enumerate(scenes))
    text = (f"📝 TRIAL script for {pid} (not saved, nothing changed)\n{piece.script.get('title', '')}\n{len(scenes)} scenes, {words} words\n\n{body}\n\n"
            f"🎬 Intro, say:\n{plan['text']}\n\nPrompt:\n{plan['prompt']}")
    try:
        telegram.send(text[:3900])
    except Exception as e:
        print(f"telegram: {type(e).__name__}: {str(e)[:120]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
