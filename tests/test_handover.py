"""Clips saved by the Arthvan bot are collected without anyone copying them (founder, 21 Nov 2026: 'yes, automatic clip hand-over')."""
import hashlib
import json
from datetime import date

from engine import handover, intro, pieces
from engine.pieces import Piece


def _sha(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def _piece(root, pid, status):
    kind = "long" if pid.endswith("long") else "short"
    ch = "arthvan" if "arthvan" in pid else "sglearning"
    pieces.save(Piece(id=pid, channel=ch, kind=kind, publish_day=date(2026, 11, 27), status=status, topic={}, script={}, ids={}), root)


def test_only_a_waiting_pieces_new_clip_is_fetched_and_never_twice(tmp_path, monkeypatch):
    monkeypatch.setattr(intro, "scheduled", lambda root, now=None: [])
    _piece(tmp_path, "2026-11-27-arthvan-short", "intro-wait")
    _piece(tmp_path, "2026-11-27-sglearning-short", "uploaded")                     # already joined: its clip is not fetched again
    new, old = b"new clip bytes" * 1000, b"old clip" * 1000
    listing = [{"name": "2026-11-27-arthvan-short.mp4", "sha": _sha(new), "size": len(new)},
               {"name": "2026-11-27-sglearning-short.mp4", "sha": _sha(old), "size": len(old)},
               {"name": "2026-11-01-arthvan-short.mp4", "sha": "x", "size": 10}, {"name": "notes.txt", "sha": "y", "size": 5}]
    calls = []
    def get(url, token="", raw=False):
        calls.append((url, raw))
        return new if raw else json.dumps(listing).encode()
    assert handover.collect(tmp_path, "tok", get) == ["2026-11-27-arthvan-short"]
    saved = tmp_path / "inbox" / "intro" / "2026-11-27-arthvan-short.mp4"
    assert saved.read_bytes() == new and sum(1 for _u, raw in calls if raw) == 1
    calls.clear()
    assert handover.collect(tmp_path, "tok", get) == [] and not any(raw for _u, raw in calls)   # the same clip: listed, not downloaded
    newer = b"a re-recorded clip" * 1000
    listing[0] = {"name": "2026-11-27-arthvan-short.mp4", "sha": _sha(newer), "size": len(newer)}
    assert handover.collect(tmp_path, "tok", lambda url, token="", raw=False: newer if raw else json.dumps(listing).encode()) == ["2026-11-27-arthvan-short"]
    assert saved.read_bytes() == newer                                                # he sent it again: the new one replaces it


def test_nothing_waiting_means_no_request_and_a_bad_download_is_left_alone(tmp_path, monkeypatch):
    monkeypatch.setattr(intro, "scheduled", lambda root, now=None: [])
    assert handover.collect(tmp_path, "", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no request expected"))) == []
    _piece(tmp_path, "2026-11-27-arthvan-long", "intro-wait")
    listing = [{"name": "2026-11-27-arthvan-long.mp4", "sha": _sha(b"what was listed"), "size": 15}]
    got = handover.collect(tmp_path, "", lambda url, token="", raw=False: b"something else" if raw else json.dumps(listing).encode())
    assert got == [] and not (tmp_path / "inbox" / "intro" / "2026-11-27-arthvan-long.mp4").exists()


def test_a_thumbnail_sent_to_the_bot_is_taken_once_and_a_later_chat_one_is_not_put_back(tmp_path):
    """22 Nov 2026: the founder sent 'thumb 2026-11-29-arthvan-long' to the Arthvan bot."""
    _piece(tmp_path, "2026-11-27-arthvan-long", "uploaded")
    _piece(tmp_path, "2026-11-27-arthvan-short", "intro-wait")
    bot = b"the bot's thumbnail" * 500
    listing = [{"name": "2026-11-27-arthvan-long.jpg", "sha": _sha(bot), "size": len(bot)}, {"name": "2026-11-27-arthvan-short.jpg", "sha": "s", "size": 9}]
    def get(url, token="", raw=False):
        return bot if raw else json.dumps(listing).encode()
    day = date(2026, 11, 22)
    assert handover.collect_thumbs(tmp_path, "", get, today=day) == ["2026-11-27-arthvan-long"]
    local = tmp_path / "inbox" / "thumb" / "2026-11-27-arthvan-long.jpg"
    assert local.read_bytes() == bot
    local.write_bytes(b"a newer one saved from the chat")
    assert handover.collect_thumbs(tmp_path, "", get, today=day) == [] and local.read_bytes() == b"a newer one saved from the chat"
    newer = b"he sent the bot another" * 500
    listing[0] = {"name": "2026-11-27-arthvan-long.jpg", "sha": _sha(newer), "size": len(newer)}
    assert handover.collect_thumbs(tmp_path, "", lambda url, token="", raw=False: newer if raw else json.dumps(listing).encode(), today=day) == ["2026-11-27-arthvan-long"]
    assert handover.collect_thumbs(tmp_path, "", get, today=date(2026, 11, 28)) == []          # past its day: left alone



def test_moving_clips_sent_to_the_arthvan_bot_are_collected_once(tmp_path):
    """28 Nov 2026: the founder sends his clips to whichever bot is open; both paths must end in inbox/scenes/."""
    import hashlib, json
    from engine import handover
    data = b"clip-bytes"
    sha = hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()
    asked = []
    def get(url, token="", raw=False):
        asked.append(url)
        if raw:
            return data
        if url.split("?")[0].endswith("inbox/scenes"):
            return json.dumps([{"name": "2026-11-28-arthvan-short", "type": "dir"}, {"name": "README", "type": "file"}]).encode()
        return json.dumps([{"name": "clip1.mp4", "size": len(data), "sha": sha}, {"name": "map.json", "size": 5, "sha": "x"}]).encode()
    assert handover.collect_scenes(tmp_path, get=get) == ["2026-11-28-arthvan-short/clip1.mp4"]
    assert (tmp_path / "inbox" / "scenes" / "2026-11-28-arthvan-short" / "clip1.mp4").read_bytes() == data
    assert handover.collect_scenes(tmp_path, get=get) == []                                 # the same clip is not fetched twice
