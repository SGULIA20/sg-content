import json
import subprocess
from datetime import date, datetime, timezone
from pathlib import Path

from engine import inbox, pieces
from tests.test_promptpack import PARTS


def _clip(path, seconds=2.0):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=blue:s=720x1280:r=24", "-f", "lavfi", "-i", "sine=frequency=300:sample_rate=48000",
                    "-t", str(seconds), "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", str(path)], check=True)
    return path


def _awaiting(root, pid="2026-10-21-sglearning-short", parts=PARTS):
    p = pieces.Piece(id=pid, channel="sglearning", kind="short", publish_day=date(2026, 10, 21))
    p.script = {"hook": "h", "scenes": [{"vo": "a"}, {"vo": "b"}], "cards": [], "captions": {"youtube": {"title": "t"}}}
    p.topic = {"pack": parts, "pack_sent": "2026-10-21T02:00:00+00:00"}
    p.status = "awaiting-clips"
    pieces.save(p, root)
    return p


def test_new_downloads_returns_unseen_gemini_clips_in_order(tmp_path):
    dl = tmp_path / "Downloads"; dl.mkdir()
    a = dl / "gemini_generated_video_aaa.mp4"; a.write_bytes(b"1")
    b = dl / "gemini_generated_video_bbb.mp4"; b.write_bytes(b"2")
    import os, time
    os.utime(a, (1_800_000_000, 1_800_000_000)); os.utime(b, (1_800_000_100, 1_800_000_100))
    (dl / "other.mp4").write_bytes(b"3")
    state = tmp_path / "state.json"
    got = inbox.new_downloads(dl, state)
    assert [p.name for p in got] == ["gemini_generated_video_aaa.mp4", "gemini_generated_video_bbb.mp4"]
    inbox.mark_seen(got, state)
    assert inbox.new_downloads(dl, state) == []


def test_file_clips_moves_in_order_and_counts(tmp_path):
    p = _awaiting(tmp_path)
    clips = [tmp_path / "x1.mp4", tmp_path / "x2.mp4"]
    for c in clips: c.write_bytes(b"v")
    n = inbox.file_clips(p, clips, inbox_dir=tmp_path / "Inbox")
    assert n == 2 and (tmp_path / "Inbox" / p.id / "part01.mp4").exists() and (tmp_path / "Inbox" / p.id / "part02.mp4").exists()
    assert inbox.have_parts(p, tmp_path / "Inbox") == [1, 2] and not clips[0].exists()


def test_check_clip_flags_missing_and_repeated_words():
    ok = inbox.check_clip(None, "India ka sabse bada IPO aa gaya, 30,213 crore. Tumhara paisa pehle se andar.",
                          transcribe=lambda c: "India ka sabse bada IPO aa gaya hai poore 30,213 crore ka tumhara paisa pehle se andar")
    assert ok == []
    missing = inbox.check_clip(None, "Anchor investors ne 8,110 crore daale, unme LIC bhi hai.", transcribe=lambda c: "Anchor investors")
    assert any("missing" in r for r in missing)
    rep = inbox.check_clip(None, "paisa pehle se laga hai kaise dekho", transcribe=lambda c: "paisa pehle se laga hai pehle se laga hai")
    assert any("repeat" in r for r in rep)


def test_tick_files_checks_and_asks_for_confirmation(tmp_path):
    p = _awaiting(tmp_path)
    dl = tmp_path / "Downloads"; dl.mkdir()
    _clip(dl / "gemini_generated_video_1.mp4"); _clip(dl / "gemini_generated_video_2.mp4")
    sent = []
    inbox.tick(root=tmp_path, downloads=dl, inbox_dir=tmp_path / "Inbox", state=tmp_path / "state.json",
               transcribe=lambda c: "exact narration", similarity=lambda a, b: 1.0, notify=lambda t: sent.append(t) or True, send_file=lambda f, c: sent.append(("file", Path(f).name)) or True)
    q = pieces.load(p.id, tmp_path)
    assert q.status == "awaiting-confirm" and ("file", "contact-sheet.jpg") in sent and any("ok " + p.id in s for s in sent if isinstance(s, str))


def test_tick_flags_bad_part_and_keeps_waiting(tmp_path):
    p = _awaiting(tmp_path)
    dl = tmp_path / "Downloads"; dl.mkdir()
    _clip(dl / "gemini_generated_video_1.mp4"); _clip(dl / "gemini_generated_video_2.mp4")
    sent = []
    inbox.tick(root=tmp_path, downloads=dl, inbox_dir=tmp_path / "Inbox", state=tmp_path / "state.json",
               transcribe=lambda c: "wrong words entirely", notify=lambda t: sent.append(t) or True, send_file=lambda f, c: True)
    q = pieces.load(p.id, tmp_path)
    assert q.status == "awaiting-clips" and any("redo" in s for s in sent)
    assert not (tmp_path / "Inbox" / p.id / "part01.mp4").exists()                    # a bad part is removed so the next clip replaces it


def test_commands_swap_and_redo(tmp_path):
    p = _awaiting(tmp_path); p.status = "awaiting-confirm"; pieces.save(p, tmp_path)
    d = tmp_path / "Inbox" / p.id; d.mkdir(parents=True)
    (d / "part01.mp4").write_bytes(b"one"); (d / "part02.mp4").write_bytes(b"two")
    assert inbox.command(f"swap {p.id} 1 2", root=tmp_path, inbox_dir=tmp_path / "Inbox") .startswith("swapped")
    assert (d / "part01.mp4").read_bytes() == b"two"
    assert inbox.command(f"redo {p.id} 2", root=tmp_path, inbox_dir=tmp_path / "Inbox").startswith("waiting")
    assert not (d / "part02.mp4").exists() and pieces.load(p.id, tmp_path).status == "awaiting-clips"


def test_command_ok_builds_and_uploads(tmp_path):
    p = _awaiting(tmp_path); p.status = "awaiting-confirm"; pieces.save(p, tmp_path)
    d = tmp_path / "Inbox" / p.id; d.mkdir(parents=True)
    _clip(d / "part01.mp4"); _clip(d / "part02.mp4")
    built = []
    def build(piece, parts, clips, out_dir):
        built.append(len(clips)); out = Path(out_dir) / "reel.mp4"; out.write_bytes(b"mp4"); piece.timings = [0.0, 2.0]; return out
    reply = inbox.command(f"ok {p.id}", root=tmp_path, inbox_dir=tmp_path / "Inbox", build=build, qa=lambda *a, **k: [],
                          upload=lambda piece, video, thumb: "yt9", thumbnail=lambda piece, clip, out: Path(out).write_bytes(b"j") or Path(out))
    assert built == [2] and reply.startswith("uploaded") and pieces.load(p.id, tmp_path).ids["yt_id"] == "yt9"
    assert (tmp_path / "out" / p.id / "reel.mp4").exists() and (tmp_path / "out" / p.id / "story.mp4").exists()
