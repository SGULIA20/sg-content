import sys
from datetime import date
from pathlib import Path

from engine import pieces

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import take_down  # noqa: E402


def test_take_down_tries_every_platform_and_keeps_the_ids(tmp_path, monkeypatch):
    (tmp_path / "pieces").mkdir()
    p = pieces.Piece(id="2026-10-29-sglearning-x1", channel="sglearning", kind="short", publish_day=date(2026, 10, 29))
    p.ids = {"yt_id": "v", "ig_reel_id": "1", "ig_story_id": "2", "threads_id": "3", "threads_poll_id": "4"}
    pieces.save(p, tmp_path)
    monkeypatch.setattr(take_down, "ROOT", tmp_path)
    monkeypatch.setattr(take_down, "hide_or_delete", lambda ch, vid: "deleted")
    monkeypatch.setattr(take_down.secrets, "get", lambda k, env=None: "tok")
    calls = []
    monkeypatch.setattr(take_down.instagram, "call", lambda m, path, tok, params=None: calls.append(("ig", m, path)) or {"success": True})

    def refuse(m, path, tok, params=None):
        raise RuntimeError("HTTP 403: missing threads_delete")
    monkeypatch.setattr(take_down.threads, "call", refuse)
    assert take_down.main([p.id]) == 0
    assert calls == [("ig", "DELETE", "/1"), ("ig", "DELETE", "/2")]
    got = pieces.load(p.id, tmp_path)
    done = got.topic["taken_down"]
    assert done["youtube"] == "deleted" and done["instagram reel"] == "deleted" and done["instagram story"] == "deleted"
    assert done["threads post"].startswith("refused: HTTP 403")
    assert got.ids["ig_reel_id"] == "1"                     # kept, so the publish job never posts it again


def test_an_unposted_piece_is_taken_out_of_the_publish_queue(tmp_path, monkeypatch):
    (tmp_path / "pieces").mkdir()
    p = pieces.Piece(id="2026-10-30-sglearning-x2", channel="sglearning", kind="short", publish_day=date(2026, 10, 30), status="uploaded")
    p.ids = {"yt_id": "v"}
    pieces.save(p, tmp_path)
    monkeypatch.setattr(take_down, "ROOT", tmp_path)
    monkeypatch.setattr(take_down, "hide_or_delete", lambda ch, vid: "deleted")
    monkeypatch.setattr(take_down.secrets, "get", lambda k, env=None: "tok")
    assert take_down.main([p.id]) == 0
    assert pieces.load(p.id, tmp_path).status == "rejected"
