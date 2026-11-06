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

PATHS = ["pieces", "out", "logs", "inbox"]
SNAPSHOTS = {"logs/remote-pause.json"}      # the control room's last answer: every workflow rewrites it, so a clash is settled in favour of the newest copy


def _git(root: Path, *args, check: bool = True) -> str:
    r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {r.stderr.strip()[:300]}")
    return r.stdout.strip()


MAX_FILE_MB = 95                 # GitHub refuses files over 100 MB (4 Nov 2026: a parked long's 112 MB video sank a whole run's push)


def _stage(root: Path, paths=None) -> None:
    for p in paths or PATHS:
        if (Path(root) / p).exists():
            _git(root, "add", "-f", "-A", p)
    if paths is None and (Path(root) / "content" / "voice.json").exists():
        _git(root, "add", "content/voice.json")
    big = [f for f in _git(root, "diff", "--cached", "--name-only").splitlines()
           if (Path(root) / f).is_file() and (Path(root) / f).stat().st_size > MAX_FILE_MB * 1024 * 1024]
    for f in big:                                                # never staged: too large for GitHub; the file stays on disk
        _git(root, "reset", "-q", "--", f)
        print(f"gitsync: {f} left out of the commit (over {MAX_FILE_MB} MB)", flush=True)


def _settleable(f: str) -> bool:
    """A clash this sync can settle on its own: the control-room snapshot, a money meter under logs/, or a media file under out/.
    A clash on a piece record or the engine is real and stops the sync (the run's commits stay local for the next one)."""
    return f in SNAPSHOTS or (f.startswith("logs/") and f.endswith(".json")) or f.startswith("out/")


def _side(root: Path, f: str, n: int) -> str | None:
    """The file at rebase stage n (1 base, 2 upstream, 3 the commit being replayed), or None when that side has no file."""
    r = subprocess.run(["git", "-C", str(root), "show", f":{n}:{f}"], capture_output=True)       # bytes: a media file is not UTF-8
    return r.stdout.decode("utf-8", errors="replace") if r.returncode == 0 else None


def _merge_meters(base: str | None, ours: str | None, theirs: str | None) -> str | None:
    """Two runs each added to the same money meter (4 Nov 2026: logs/image-spend.json sank a 30-minute long rebuild): numbers at the
    same key become ours + (theirs - base), other values take the replayed commit's side. None when the files are not plain JSON."""
    try:
        b, o, t = (json.loads(x) if x else {} for x in (base, ours, theirs))
    except ValueError:
        return None
    def merge(b, o, t):
        if isinstance(o, dict) and isinstance(t, dict):
            b = b if isinstance(b, dict) else {}
            out = dict(o)
            for k, tv in t.items():
                out[k] = merge(b.get(k), o.get(k), tv) if k in o else tv
            return out
        if isinstance(o, (int, float)) and isinstance(t, (int, float)) and not isinstance(o, bool) and not isinstance(t, bool):
            bb = b if isinstance(b, (int, float)) and not isinstance(b, bool) else 0
            return round(o + (t - bb), 6)
        return t
    return json.dumps(merge(b, o, t), ensure_ascii=False, indent=1)


def _settle(root: Path, f: str) -> None:
    """One settleable clash: the snapshot and out/ media keep the commit being replayed ("theirs" in a rebase: this run's own work);
    a deleted-on-both side is dropped; a meter is merged three ways."""
    if f.startswith("out/"):                                          # media: never read, this run's copy or nothing (6 Nov 2026 crash)
        base, ours, theirs = None, None, (_side(root, f, 3) is not None)
        if not theirs:
            _git(root, "rm", "-q", "--cached", "--", f, check=False)
            (Path(root) / f).unlink(missing_ok=True)
        else:
            _git(root, "checkout", "--theirs", "--", f)
            _git(root, "add", f)
        return
    base, ours, theirs = (_side(root, f, n) for n in (1, 2, 3))
    if theirs is None:                                                # this run deleted it (or never had it): keep it gone
        _git(root, "rm", "-q", "--cached", "--", f, check=False)
        (Path(root) / f).unlink(missing_ok=True)
        return
    merged = _merge_meters(base, ours, theirs) if f.startswith("logs/") and f not in SNAPSHOTS and ours is not None else None
    if merged is not None:
        (Path(root) / f).write_text(merged)
    else:
        _git(root, "checkout", "--theirs", "--", f)
    _git(root, "add", f)


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
        if not clash or any(not _settleable(f) for f in clash):
            break
        for f in clash:
            _settle(root, f)
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
    """Remembers the commit that holds each Short's reel, because Instagram and Threads fetch the video at that commit. A Short that has
    the founder's intro (ids["intro"]) must point at the commit with the intro version: until 6 Nov 2026 the sha recorded for the plain
    reel stayed, so Instagram posted the old video (no intro) under the new cover. `out_sha_intro` marks that it was re-recorded."""
    done = []
    for p in pieces.list_all(root):
        if p.kind != "short" or p.status not in ("uploaded", "posted") or not (Path(root) / "out" / p.id / "reel.mp4").exists():
            continue
        stale_for_intro = bool(p.ids.get("intro")) and not p.ids.get("out_sha_intro") and not p.ids.get("ig_reel_id")
        if p.ids.get("out_sha") and not stale_for_intro:
            continue
        p.ids["out_sha"] = sha
        if p.ids.get("intro"):
            p.ids["out_sha_intro"] = True
        pieces.save(p, root)
        done.append(p.id)
    return done


def enabled(env=None) -> bool:
    env = os.environ if env is None else env
    return env.get("SG_COMMIT_EACH") == "1" or env.get("SG_PUSH_FROM_MAC") == "1" or env.get("GITHUB_ACTIONS") == "true"


def _push(root: Path, tries: int = 4) -> None:
    """A push GitHub refuses with a server error (4 Nov 2026: "fatal error in commit_refs") is tried again after a pause."""
    import time
    last = ""
    for attempt in range(tries):
        r = subprocess.run(["git", "-C", str(root), "push", "-q", "origin", "HEAD:main"], capture_output=True, text=True)
        if r.returncode == 0:
            return
        last = r.stderr.strip()[:300]
        if "rejected" in last and "fetch first" in last:
            _pull_rebase(root)
        if attempt < tries - 1:
            time.sleep(5 * (2 ** attempt))
    raise RuntimeError(f"git push failed after {tries} tries: {last}")


def commit(root: Path = ROOT, message: str = "sg-content: progress", push: bool = True, paths=None) -> str:
    _stage(root, paths)
    if not _dirty(root):
        if push and _git(root, "rev-list", "--count", "origin/main..HEAD", check=False) not in ("", "0"):
            _pull_rebase(root)                                  # an earlier piece's push failed: send it now, with the end-of-run sync
            _push(root)
        return ""
    _git(root, "commit", "-q", "-m", f"{message} [skip ci]")
    if push:
        _pull_rebase(root)
        _push(root)
    sha = _git(root, "rev-parse", "HEAD")                      # after the push: a rebase rewrites commits, so only the pushed HEAD is a sha GitHub serves
    if record_out_sha(root, sha):
        _git(root, "add", "-A", "pieces")
        _git(root, "commit", "-q", "-m", "record media sha [skip ci]")
        if push:
            _pull_rebase(root)
            _push(root)
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
