import json
from datetime import datetime, timezone

from engine import reeltip

NOW = datetime(2026, 10, 26, 6, 30, tzinfo=timezone.utc)
ENV = {"IG_ACCESS_TOKEN": "t", "IG_USER_ID": "me"}
MEDIA = {"data": [
    {"id": "R1", "media_product_type": "REELS", "permalink": "https://ig/r1", "caption": "Waypoint story", "timestamp": "2026-10-25T16:00:00+0000"},
    {"id": "R2", "media_product_type": "REELS", "permalink": "https://ig/r2", "caption": "", "timestamp": "2026-10-24T16:00:00+0000"},
    {"id": "R3", "media_product_type": "REELS", "permalink": "https://ig/r3", "caption": "", "timestamp": "2026-10-20T16:00:00+0000"},
    {"id": "P1", "media_product_type": "FEED", "caption": "", "timestamp": "2026-10-25T10:00:00+0000"}]}
VIEWS = {"R1": 4200, "R2": 900, "R3": 1000, "P1": 99999}


def _run(tmp_path, views=VIEWS, state=None):
    notes = []
    path = tmp_path / "tip.json"
    if state:
        path.write_text(json.dumps(state))
    out = reeltip.run(ENV, NOW, call=lambda m, p, t, params=None: MEDIA, numbers=lambda mid, tok: {"views": views[mid]},
                      notify=notes.append, root=tmp_path, state_path=path)
    return out, notes, json.loads(path.read_text())


def test_the_reel_taking_off_is_tipped_with_its_apps_link_once(tmp_path):
    out, notes, state = _run(tmp_path)
    assert out == "tipped R1" and len(notes) == 1
    assert "https://ig/r1" in notes[0] and "com.arthvananalytics.waypoint" in notes[0] and "utm_medium%3Dreel_link" in notes[0]
    assert "tip 1 of 8" in notes[0] and state["count"] == 1
    out, notes, _ = _run(tmp_path, state=state)
    assert out == "no Reel stands out today" and notes == []                      # the same Reel is never tipped twice


def test_no_tip_when_nothing_stands_out_or_the_month_is_used_up(tmp_path):
    out, notes, _ = _run(tmp_path, views={"R1": 950, "R2": 900, "R3": 1000, "P1": 5})
    assert out == "no Reel stands out today" and notes == []
    out, notes, _ = _run(tmp_path, state={"month": "2026-10", "tipped": [], "count": 8})
    assert out == "monthly tips used" and notes == []
