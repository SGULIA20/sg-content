"""Commit piece records, published Short files and logs right after each piece, so a crash or timeout never loses an id (review C1/C2).

commit(root, message): stages pieces/, out/ (forced past .gitignore; the ignore rules keep intermediates out), logs/ and content/voice.json,
commits, records that commit's sha as `out_sha` on every uploaded Short that now has its reel in that commit, commits that too, and pushes
(pull --rebase first). Returns the sha holding the media, or "" when there was nothing to commit.
"""
import json
import os
import subprocess
from pathlib import Path

from . import pieces
from .config import ROOT

PATHS = ["pieces", "out", "logs"]
SNAPSHOTS = {"logs/remote-pause.json"}      # the control room's last answer: every workflow rewrites it, so a clash is settled in favour of the newest copy


def _git(root: Path, *args, check: bool = True) -> str:
    r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {r.stderr.strip()[:300]}")
    return r.stdout.strip()


def _stage(root: Path, paths=None) -> None:
    for p in paths or PATHS:
        if (Path(root) / p).exists():
            _git(root, "add", "-f", "-A", p)
    if paths is None and (Path(root) / "content" / "voice.json").exists():
        _git(root, "add", "content/voice.json")


def _rebasing(root: Path) -> bool:
    return any((Path(root) / ".git" / d).exists() for d in ("rebase-merge", "rebase-apply"))


def _pull_rebase(root: Path) -> None:
    """pull --rebase that never leaves git stuck mid-rebase (24 Oct 2026: a clash on logs/remote-pause.json did, every later save failed and a run
    lost 40 minutes of paid work). A clash only on snapshot files is settled by keeping the commit being replayed; any other clash aborts the
    rebase and raises, so the run's own commits stay safe locally for the next sync."""
    r = subprocess.run(["git", "-C", str(root), "pull", "--rebase", "-q", "origin", "main"], capture_output=True, text=True)
    for _ in range(20):
        if r.returncode == 0 or not _rebasing(root):
            break
        clash = [f for f in _git(root, "diff", "--name-only", "--diff-filter=U", check=False).splitlines() if f]
        if not clash or any(f not in SNAPSHOTS for f in clash):
            break
        for f in clash:
            _git(root, "checkout", "--theirs", "--", f)            # in a rebase, "theirs" is the commit being replayed
            _git(root, "add", f)
        r = subprocess.run(["git", "-C", str(root), "-c", "core.editor=true", "rebase", "--continue"], capture_output=True, text=True)
        if r.returncode != 0 and _rebasing(root) and not _git(root, "diff", "--name-only", "--diff-filter=U", check=False):
            r = subprocess.run(["git", "-C", str(root), "rebase", "--skip"], capture_output=True, text=True)    # the commit became empty
    if r.returncode != 0 or _rebasing(root):
        why = r.stderr.strip()[:300]
        subprocess.run(["git", "-C", str(root), "rebase", "--abort"], capture_output=True)
        raise RuntimeError(f"git pull --rebase failed: {why}")


def _dirty(root: Path) -> bool:
    return subprocess.run(["git", "-C", str(root), "diff", "--cached", "--quiet"]).returncode != 0


def record_out_sha(root: Path, sha: str) -> list:
    done = []
    for p in pieces.list_all(root):
        if p.kind == "short" and p.status in ("uploaded", "posted") and not p.ids.get("out_sha") and (Path(root) / "out" / p.id / "reel.mp4").exists():
            p.ids["out_sha"] = sha
            pieces.save(p, root)
            done.append(p.id)
    return done


def enabled(env=None) -> bool:
    env = os.environ if env is None else env
    return env.get("SG_COMMIT_EACH") == "1" or env.get("SG_PUSH_FROM_MAC") == "1" or env.get("GITHUB_ACTIONS") == "true"


def commit(root: Path = ROOT, message: str = "sg-content: progress", push: bool = True, paths=None) -> str:
    _stage(root, paths)
    if not _dirty(root):
        if push and _git(root, "rev-list", "--count", "origin/main..HEAD", check=False) not in ("", "0"):
            _pull_rebase(root)                                  # an earlier piece's push failed: send it now, with the end-of-run sync
            _git(root, "push", "-q", "origin", "HEAD:main")
        return ""
    _git(root, "commit", "-q", "-m", f"{message} [skip ci]")
    if push:
        _pull_rebase(root)
        _git(root, "push", "-q", "origin", "HEAD:main")
    sha = _git(root, "rev-parse", "HEAD")                      # after the push: a rebase rewrites commits, so only the pushed HEAD is a sha GitHub serves
    if record_out_sha(root, sha):
        _git(root, "add", "-A", "pieces")
        _git(root, "commit", "-q", "-m", "record media sha [skip ci]")
        if push:
            _pull_rebase(root)
            _git(root, "push", "-q", "origin", "HEAD:main")
    return sha


def main(argv=None) -> int:
    """python -m engine.gitsync "message" [path ...]: the end-of-run sync of the workflows (default paths: pieces out logs and the voice list)."""
    import sys
    argv = sys.argv[1:] if argv is None else argv
    commit(ROOT, argv[0] if argv else "sg-content: progress", paths=argv[1:] or None)
    return 0


def safe_commit(root: Path = ROOT, message: str = "sg-content: progress", env=None) -> str:
    """commit() when running in the cloud; never raises (a push failure is printed, the next step retries)."""
    if not enabled(env):
        return ""
    try:
        return commit(root, message)
    except Exception as e:
        print(f"git sync failed: {e}", flush=True)
        return ""


if __name__ == "__main__":
    raise SystemExit(main())
