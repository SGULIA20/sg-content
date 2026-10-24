import shutil
import subprocess
from datetime import date
from pathlib import Path

import pytest

from engine import gitsync, pieces
from engine.config import ROOT


def _git(path, *args):
    r = subprocess.run(["git", "-C", str(path), *args], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


def _clone(remote: Path, where: Path) -> Path:
    subprocess.run(["git", "clone", "-q", str(remote), str(where)], check=True, capture_output=True)
    _git(where, "config", "user.name", "t")
    _git(where, "config", "user.email", "t@example.com")
    return where


@pytest.fixture
def repos(tmp_path):
    """A bare remote with one commit, and two clones: `a` is the cloud run, `b` is another workflow that pushes in between."""
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)
    seed = tmp_path / "seed"
    seed.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(seed)], check=True)
    _git(seed, "config", "user.name", "t")
    _git(seed, "config", "user.email", "t@example.com")
    shutil.copy(ROOT / ".gitattributes", seed / ".gitattributes")
    (seed / "logs").mkdir()
    (seed / "logs" / "remote-pause.json").write_text('{"paused": false, "at": "seed"}')
    (seed / "logs" / "write-batch.jsonl").write_text('{"n": 0}\n')
    (seed / "pieces").mkdir()
    pieces.save(pieces.Piece(id="2026-11-01-sglearning-short", channel="sglearning", kind="short", publish_day=date(2026, 11, 1)), seed)
    _git(seed, "add", "-A")
    _git(seed, "commit", "-q", "-m", "seed")
    _git(seed, "remote", "add", "origin", str(remote))
    _git(seed, "push", "-q", "origin", "main")
    return _clone(remote, tmp_path / "a"), _clone(remote, tmp_path / "b"), remote


def _push_from(b: Path, relpath: str, text: str, mode="w"):
    with open(b / relpath, mode) as f:
        f.write(text)
    _git(b, "add", "-A")
    _git(b, "commit", "-q", "-m", f"b: {relpath}")
    _git(b, "push", "-q", "origin", "HEAD:main")


def _stuck(path: Path) -> bool:
    return (path / ".git" / "rebase-merge").exists() or (path / ".git" / "rebase-apply").exists()


def test_a_clash_on_the_control_room_snapshot_is_settled_not_left_stuck(repos):
    a, b, remote = repos
    _push_from(b, "logs/remote-pause.json", '{"paused": true, "at": "b"}')                 # the publish workflow wrote it first
    (a / "logs" / "remote-pause.json").write_text('{"paused": false, "at": "a"}')           # this run wrote it too
    (a / "logs" / "claude-spend.json").write_text("{}")                                      # plus its own real work
    sha = gitsync.commit(a, "produce: piece")
    assert sha and not _stuck(a)
    assert _git(a, "rev-parse", "HEAD") == _git(remote, "rev-parse", "main")                 # pushed
    assert '"at": "a"' in (a / "logs" / "remote-pause.json").read_text()


def test_two_appends_to_the_same_ledger_keep_both_lines(repos):
    a, b, _remote = repos
    _push_from(b, "logs/write-batch.jsonl", '{"n": "from b"}\n', "a")
    with open(a / "logs" / "write-batch.jsonl", "a") as f:
        f.write('{"n": "from a"}\n')
    gitsync.commit(a, "produce: piece")
    text = (a / "logs" / "write-batch.jsonl").read_text()
    assert not _stuck(a) and '"from a"' in text and '"from b"' in text


def test_a_clash_on_a_real_piece_stops_cleanly_and_keeps_the_local_work(repos):
    a, b, remote = repos
    p = pieces.load("2026-11-01-sglearning-short", b)
    p.ids["yt_id"] = "from-b"
    pieces.save(p, b)
    _git(b, "add", "-A"); _git(b, "commit", "-q", "-m", "b piece"); _git(b, "push", "-q", "origin", "HEAD:main")
    p = pieces.load("2026-11-01-sglearning-short", a)
    p.ids["yt_id"] = "from-a"
    pieces.save(p, a)
    with pytest.raises(RuntimeError):
        gitsync.commit(a, "produce: piece")
    assert not _stuck(a)                                                                      # never left in the middle of a rebase
    assert "produce: piece" in _git(a, "log", "-1", "--format=%s")                            # the run's own commit is still there
    assert _git(remote, "log", "-1", "--format=%s") == "b piece"                              # and the other side was not overwritten
    assert gitsync.safe_commit(a, "again", env={"SG_COMMIT_EACH": "1"}) == ""                 # the safe wrapper reports and carries on


def test_a_commit_left_local_by_a_failed_sync_is_pushed_by_the_next_sync(repos):
    a, b, remote = repos
    (a / "logs" / "claude-spend.json").write_text('{"a": 1}')
    gitsync.commit(a, "produce: first piece", push=False)                                     # as if its push had failed mid-run
    _push_from(b, "logs/other.json", "{}")                                                    # the remote moved on meanwhile
    assert gitsync.commit(a, "produce: end of run") == ""                                     # nothing new to commit...
    assert _git(a, "rev-parse", "HEAD") == _git(remote, "rev-parse", "main")                  # ...but the earlier piece still got pushed
    assert "produce: first piece" in _git(remote, "log", "--format=%s", "-3")


def test_the_publish_step_can_leave_media_out(repos):
    a, _b, _remote = repos
    (a / "out").mkdir()
    (a / "out" / "reel.mp4").write_text("x")
    (a / "logs" / "claude-spend.json").write_text("{}")
    gitsync.commit(a, "publish: x", paths=["pieces", "logs"])
    assert "out/reel.mp4" not in _git(a, "ls-files")
    assert "logs/claude-spend.json" in _git(a, "ls-files")
