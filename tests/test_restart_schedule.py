"""Founder, 27 Nov 2026: 'Remove all scheduled posts and let us go with what we decided'."""
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import restart_schedule as rs  # noqa: E402
from engine import pieces  # noqa: E402


def _piece(root, pid, status, yt, **ids):
    ch, kind = pid.split("-")[3], pid.split("-")[4]
    p = pieces.Piece(id=pid, channel=ch, kind=kind, publish_day=date.fromisoformat(pid[:10]))
    p.status, p.topic, p.script = status, {"title": "t"}, {"title": "t", "scenes": []}
    p.ids = {"yt_id": yt, **ids} if yt else dict(ids)
    pieces.save(p, root)
    return p


def test_old_scheduled_videos_go_off_the_schedule_new_style_and_published_ones_stay(tmp_path):
    _piece(tmp_path, "2026-11-27-arthvan-short", "posted", "PUB")
    _piece(tmp_path, "2026-11-28-arthvan-short", "uploaded", "OLD1")
    _piece(tmp_path, "2026-12-01-arthvan-short", "uploaded", "NEW1", sound="track")
    _piece(tmp_path, "2026-12-03-arthvan-short", "intro-wait", None, sound="track")
    for extra in ("out/2026-11-28-arthvan-short/reel.mp4", "inbox/intro/2026-11-28-arthvan-short.mp4", "inbox/thumb/2026-11-28-arthvan-short.jpg"):
        (tmp_path / extra).parent.mkdir(parents=True, exist_ok=True); (tmp_path / extra).write_bytes(b"x")
    rows = {"arthvan": [{"id": "PUB", "publishAt": "2026-11-27T13:30:00Z", "title": "", "piece": ""},
                        {"id": "OLD1", "publishAt": "2026-11-28T14:30:00Z", "title": "", "piece": ""},
                        {"id": "NEW1", "publishAt": "2026-12-01T14:30:00Z", "title": "", "piece": ""},
                        {"id": "ORPHAN", "publishAt": "2026-12-17T14:30:00Z", "title": "", "piece": ""},
                        {"id": "DRAFT", "publishAt": "", "title": "", "piece": ""}]}
    videos, aside = rs.plan(tmp_path, rows, datetime(2026, 11, 27, 16, 0, tzinfo=timezone.utc))
    assert [r["id"] for _c, r in videos] == ["OLD1", "ORPHAN"] and [p.id for p in aside] == ["2026-11-28-arthvan-short"]
    rs.set_aside(tmp_path, aside[0])
    assert [p.id for p in pieces.list_all(tmp_path)] == ["2026-11-27-arthvan-short", "2026-12-01-arthvan-short", "2026-12-03-arthvan-short"]
    kept = json.loads((tmp_path / "pieces" / "replaced" / "2026-11-28-arthvan-short.json").read_text())
    assert kept["ids"]["yt_id"] == "OLD1" and "replaced" in kept["topic"]                     # the record is kept, the slot is empty
    assert not (tmp_path / "out" / "2026-11-28-arthvan-short").exists() and not (tmp_path / "inbox" / "intro" / "2026-11-28-arthvan-short.mp4").exists()
    seen = []
    def call(method, url, token, body=None):
        seen.append((method, body)); return 200, {}, {"status": {"privacyStatus": "private"}}
    assert rs.unschedule("arthvan", "OLD1", call, lambda ch: "tok") == "off the schedule"
    assert seen == [("PUT", {"id": "OLD1", "status": {"privacyStatus": "private", "selfDeclaredMadeForKids": False}})]      # private, no publish time, never a delete
    assert rs.unschedule("arthvan", "X", lambda *a: (403, {}, {}), lambda ch: "t").startswith("FAILED")
