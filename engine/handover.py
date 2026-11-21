"""Clips the founder sends to the Arthvan bot are saved in the arthvan-media repo (inbox/intro/<piece id>.mp4). Until 21 Nov 2026 a
person had to copy each one across before the studio job could join it: on 20 Nov two clips sat there from 08:29 to 16:05 Lagos
because nobody was told. This collects them itself, every studio run.

Only a clip for a piece that is still waiting for one is taken, and only when it differs from the copy already here, so a clip already
joined is never fetched again and an old file never replaces a newer one. arthvan-media is a public repository: the run's own
GitHub token is used only for the higher request allowance.
"""
import hashlib
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from . import gitsync, intro, pieces, secrets
from .config import ROOT

SOURCE = "SGULIA20/arthvan-media"
SOURCE_DIR = "inbox/intro"
API = "https://api.github.com/repos/{repo}/contents/{path}?ref=main"
MAX_BYTES = 60_000_000


def _get(url: str, token: str = "", raw: bool = False) -> bytes:
    headers = {"Accept": "application/vnd.github.raw+json" if raw else "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
               "User-Agent": "sg-content-handover"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=120, context=secrets.ssl_context()) as r:
        return r.read()


def blob_sha(path: Path) -> str:
    """The id git gives a file's contents: what GitHub's listing reports, so equal files are spotted without downloading."""
    data = Path(path).read_bytes()
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def wanted(root: Path) -> dict:
    """{piece id: piece} for every piece still waiting for its clip."""
    return {p.id: p for p in list(intro.waiting(root)) + list(intro.scheduled(root))}


def collect(root: Path = ROOT, token: str = "", get=_get) -> list:
    """Fetches every waiting piece's new clip into inbox/intro/; returns the piece ids taken."""
    need = wanted(root)
    if not need:
        return []
    listing = json.loads(get(API.format(repo=SOURCE, path=SOURCE_DIR), token))
    taken = []
    for entry in listing:
        name = str(entry.get("name", ""))
        pid = name[:-4] if name.endswith(".mp4") else ""
        if pid not in need or not 0 < int(entry.get("size") or 0) <= MAX_BYTES:
            continue
        local = intro.clip_path(root, need[pid])
        if local.exists() and blob_sha(local) == entry.get("sha"):
            continue                                               # the same clip is already here (joined, waiting, or turned down)
        data = get(API.format(repo=SOURCE, path=urllib.parse.quote(f"{SOURCE_DIR}/{name}")), token, raw=True)
        if hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest() != entry.get("sha"):
            print(f"{pid}: the download does not match the listing, left for the next run", flush=True)
            continue
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_bytes(data)
        taken.append(pid)
    return taken


def main(argv=None) -> int:
    import os
    try:
        taken = collect(ROOT, os.environ.get("GITHUB_TOKEN", ""))
    except (urllib.error.URLError, OSError, ValueError, KeyError) as e:       # never stops the studio run: the next one tries again
        print(f"clip hand-over skipped: {type(e).__name__}: {secrets.scrub(str(e))[:160]}", flush=True)
        return 0
    if taken:
        print(f"collected from the Arthvan bot: {', '.join(taken)}", flush=True)
        gitsync.commit(ROOT, f"handover: clip(s) from the Arthvan bot for {', '.join(taken)}", paths=[f"{intro.INBOX}/{t}.mp4" for t in taken])
    return 0


if __name__ == "__main__":
    sys.exit(main())
