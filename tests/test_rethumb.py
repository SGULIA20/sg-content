import json
import sys
from datetime import date
from pathlib import Path

from engine import pieces

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import rethumb  # noqa: E402

BLOCK = {"name": "SARASWATI", "name_hi": "सरस्वती", "words": ["8,000 SAAL", "GAYAB?"], "words_hi": ["8,000 साल", "गायब?"],
         "scene": "LEFT: a blue river; RIGHT: the same valley dry"}


def _ask(model, body, key=None):
    assert "thumbnail.name_hi" in body["contents"][0]["parts"][0]["text"]          # the writer's own rules go along
    return {"candidates": [{"content": {"parts": [{"text": json.dumps(BLOCK, ensure_ascii=False)}]}}]}


def test_redo_rewrites_the_block_renders_and_replaces_the_youtube_thumbnail(tmp_path):
    p = pieces.Piece(id="2026-10-25-arthvan-long", channel="arthvan", kind="long", publish_day=date(2026, 10, 25), status="posted")
    p.script = {"title": "t", "hook": "h", "scenes": [{"vo": "8,000 saal pehle"}], "thumbnail": {"words": ["8,000", "GAYAB"], "scene": "a face"}}
    p.topic = {"thumb_test": {"phase": "done", "kept": "a"}}
    p.ids = {"yt_id": "vid1"}
    pieces.save(p, tmp_path)
    made, set_to = [], []
    def make(piece, out_dir):
        made.append(piece.script["thumbnail"]); return {"thumb": Path(out_dir) / "thumb.jpg"}
    msg = rethumb.redo(p, root=tmp_path, ask=_ask, make=make, set_thumb=lambda tok, vid, jpg: set_to.append((vid, jpg.name)) or True,
                       token_for=lambda ch, env: "tok")
    assert made == [BLOCK] and set_to == [("vid1", "thumb.jpg")] and "सरस्वती" in msg and "set" in msg
    saved = pieces.load(p.id, tmp_path)
    assert saved.script["thumbnail"] == BLOCK and "thumb_test" not in saved.topic


def test_needs_yes():
    assert rethumb.main([]) == 2


def test_a_draft_only_gets_the_new_block(tmp_path):
    p = pieces.Piece(id="2026-11-02-arthvan-short", channel="arthvan", kind="short", publish_day=date(2026, 11, 2), status="written")
    p.script = {"title": "t", "hook": "h", "scenes": [], "thumbnail": {"words": ["X"], "scene": "s"}}
    pieces.save(p, tmp_path)
    msg = rethumb.redo(p, root=tmp_path, ask=_ask, make=lambda *a: 1 / 0, set_thumb=lambda *a: 1 / 0, token_for=lambda *a: 1 / 0)
    assert "draft" in msg and pieces.load(p.id, tmp_path).script["thumbnail"] == BLOCK
