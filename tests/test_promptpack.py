import json
from datetime import date
from types import SimpleNamespace

from engine import pieces, promptpack
from tests.test_writer import good_script

PARTS = [
    {"part": 1, "scene": 0, "narration": "India ka sabse bada IPO aa gaya, 30,213 crore. Tumhara paisa pehle se andar.",
     "prompt": "Night Mumbai skyline behind SG [locked], tablet shows ₹30,213 CRORE, leans into camera."},
    {"part": 2, "scene": 1, "narration": "Anchor investors ne 8,110 crore daale, unme LIC bhi hai.",
     "prompt": "SG [locked] in a bright office, tablet shows coins flowing into a vault labelled BIMA."},
]


def _piece():
    p = pieces.Piece(id="2026-10-21-sglearning-short", channel="sglearning", kind="short", publish_day=date(2026, 10, 21))
    p.script = good_script(); p.status = "written"
    return p


class FakeMessages:
    def __init__(self, parts):
        self.parts, self.calls = parts, []

    def create(self, **kw):
        self.calls.append(kw)
        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=json.dumps({"parts": self.parts}))],
                               usage=SimpleNamespace(input_tokens=1000, output_tokens=500))


def test_write_returns_one_part_per_scene_with_short_narration(tmp_path):
    fm = FakeMessages(PARTS + [{"part": 3, "scene": 2, "narration": " ".join(["word"] * 25), "prompt": "x"}])
    parts = promptpack.write(_piece(), client=SimpleNamespace(beta=SimpleNamespace(messages=fm)), spend=tmp_path / "s.json")
    assert [p["part"] for p in parts] == [1, 2, 3]
    assert all(len(p["narration"].split()) <= promptpack.MAX_WORDS for p in parts)      # over-long narration is trimmed at a sentence or word boundary
    assert "9:16" in fm.calls[0]["messages"][0]["content"] and "SG [locked]" in fm.calls[0]["system"][0]["text"]


def test_render_has_locked_line_once_and_watermark_per_part():
    text = promptpack.render(_piece(), PARTS)
    assert text.count("LOCKED CHARACTER LINE") == 1 and text.count("@SGLearning watermark top right, white, bold, 80% opacity") == 2
    assert "Part 1 — " in text and "Narration: \"India ka sabse bada IPO" in text and "9:16 vertical" in text


def test_render_strips_logo_words_from_prompts():
    bad = [{"part": 1, "scene": 0, "narration": "x", "prompt": "a large LIC emblem and a Jio logo on screen"}]
    text = promptpack.render(_piece(), bad)
    assert "emblem" not in text.lower() and "logo on screen" not in text.lower() and "no logos" in text.lower()


def test_long_piece_uses_16_9():
    p = _piece(); p.kind = "long"
    assert "16:9 cinematic" in promptpack.render(p, PARTS)


def test_send_writes_pack_file_and_sets_status(tmp_path):
    p = _piece()
    sent = []
    path = promptpack.send(p, "PACK TEXT", packs_dir=tmp_path / "Packs", root=tmp_path, notify=lambda t: sent.append(t) or True)
    assert path.read_text() == "PACK TEXT" and sent[0].startswith("Prompt pack") and pieces.load(p.id, tmp_path).status == "awaiting-clips"
    assert pieces.load(p.id, tmp_path).topic["pack_sent"]
