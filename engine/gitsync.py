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


def _git(root: Path, *args, check: bool = True) -> str:
    r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {r.stderr.strip()[:300]}")
    return r.stdout.strip()


def _stage(root: Path) -> None:
    for p in PATHS:
        if (Path(root) / p).exists():
            _git(root, "add", "-f", "-A", p)
    if (Path(root) / "content" / "voice.json").exists():
        _git(root, "add", "content/voice.json")


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
    return env.get("SG_COMMIT_EACH") == "1" or env.get("GITHUB_ACTIONS") == "true"


def commit(root: Path = ROOT, message: str = "sg-content: progress", push: bool = True) -> str:
    _stage(root)
    if not _dirty(root):
        return ""
    _git(root, "commit", "-q", "-m", f"{message} [skip ci]")
    sha = _git(root, "rev-parse", "HEAD")
    if record_out_sha(root, sha):
        _git(root, "add", "-A", "pieces")
        _git(root, "commit", "-q", "-m", "record media sha [skip ci]")
    if push:
        _git(root, "pull", "--rebase", "-q", "origin", "main")
        _git(root, "push", "-q", "origin", "HEAD:main")
    return sha


def safe_commit(root: Path = ROOT, message: str = "sg-content: progress", env=None) -> str:
    """commit() when running in the cloud; never raises (a push failure is printed, the next step retries)."""
    if not enabled(env):
        return ""
    try:
        return commit(root, message)
    except Exception as e:
        print(f"git sync failed: {e}", flush=True)
        return ""
