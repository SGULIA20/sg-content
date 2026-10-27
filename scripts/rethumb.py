"""Give pieces already made the new thumbnail (founder, 27 Oct 2026: "fix for present, drafts, scheduled and future"). For each piece:
the writer's thumbnail block is rewritten to the new rules (topic name in Roman and Devanagari, a number and one shock word, one dramatic
sight) by one cheap Gemini text call; for pieces already on YouTube one picture is painted (about ₹3), thumb/thumb_b/cover are
rendered into out/<id>/, and the YouTube thumbnail is replaced. Shorts not yet on Instagram get the new cover there when they post. Instagram cannot change a posted Reel's cover.

    python3 scripts/rethumb.py --yes                       every written piece still on the old thumbnail, newest publish day first
    python3 scripts/rethumb.py --yes 2026-11-05-arthvan-long ...
"""
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import gemini, pieces, secrets, thumbs, youtube, writer  # noqa: E402
from engine.config import CONTENT_DIR, ROOT  # noqa: E402

FIELDS = ("name", "name_hi", "words", "words_hi", "scene")


def rules(root: Path = CONTENT_DIR) -> str:
    """The writer's own thumbnail rules, so old pieces follow exactly what new ones are written to."""
    text = (Path(root) / "prompts" / "writer-system.txt").read_text()
    a = text.index("- thumbnail (")
    b = text.index("- carousel:", a)
    return text[a:b].strip()


def new_block(piece, ask=gemini.generate) -> dict:
    s = piece.script or {}
    story = {"channel": piece.channel, "kind": piece.kind, "title": s.get("title"), "youtube_title": (s.get("captions") or {}).get("youtube", {}).get("title"),
             "hook": s.get("hook"), "topic": {k: piece.topic.get(k) for k in ("title", "title_hi", "place") if piece.topic.get(k)},
             "story": " ".join(sc.get("vo", "") for sc in s.get("scenes", []))[:2500], "facts": [f.get("text") for f in (piece.facts or [])][:8]}
    prompt = ("Write ONLY the thumbnail block for this finished video, following these rules exactly. Use only numbers that appear in the "
              "story or facts.\n\n" + rules() + "\n\nReturn JSON: {\"name\": str, \"name_hi\": str, \"words\": [str, str], \"words_hi\": [str, str], "
              "\"scene\": str}\n\nVIDEO:\n" + json.dumps(story, ensure_ascii=False))
    body = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0.6, "responseMimeType": "application/json"}}
    raw = gemini.text(ask(writer.GEMINI_MODEL, body))
    block = json.loads(re.sub(r"^```(json)?|```$", "", raw.strip()).strip())
    if not all(block.get(k) for k in FIELDS):
        raise ValueError(f"thumbnail block incomplete: {raw[:200]}")
    return {k: block[k] for k in FIELDS}


def redo(piece, root: Path = ROOT, env=None, ask=gemini.generate, make=thumbs.make, set_thumb=youtube.set_thumbnail, token_for=youtube.access_token) -> str:
    """A draft (written, not yet on YouTube) only gets the new block: its picture is painted when it is made."""
    piece.script["thumbnail"] = new_block(piece, ask)
    if not piece.ids.get("yt_id"):
        pieces.save(piece, root)
        return f"{piece.id}: draft, new words {thumbs.name_for(piece)} / {' '.join(thumbs.words_for(piece))}"
    out = make(piece, Path(root) / "out" / piece.id)
    piece.topic.pop("thumb_test", None)                   # a new pair of pictures starts a fresh click test
    pieces.save(piece, root)
    ok = set_thumb(token_for(piece.channel, env), piece.ids["yt_id"], out["thumb"])
    return f"{piece.id}: {thumbs.name_for(piece)} / {' '.join(thumbs.words_for(piece))}, YouTube {'set' if ok else 'NOT set'}"


def main(argv: list) -> int:
    if "--yes" not in argv:
        print(__doc__)
        return 2
    ids = [a for a in argv if not a.startswith("--")]
    todo = [p for p in pieces.list_all(ROOT) if p.script and p.status != "rejected" and not p.id.startswith("preview")
            and not (p.script.get("thumbnail") or {}).get("name") and (not ids or p.id in ids)]
    failed = 0
    for p in sorted(todo, key=lambda p: (p.publish_day, p.id), reverse=True):
        try:
            print(redo(p, env=os.environ), flush=True)
        except Exception as e:
            failed += 1
            print(f"{p.id}: FAILED {secrets.scrub(str(e))[:200]}", flush=True)
    print(f"done: {len(todo) - failed} of {len(todo)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
