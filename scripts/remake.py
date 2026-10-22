"""Send finished-but-flawed pieces back through the pipeline with their scripts kept (22 Oct 2026: clipped endings, a line spoken
twice, a tone note read aloud). The old YouTube upload is removed (private first, then deleted when the API allows), the ids are
cleared, the status goes back to "written", and the next produce run re-voices (fresh cache key), re-paints from cache, re-assembles,
re-checks and re-uploads. Instagram/Threads/LinkedIn posts already made are left alone (they cannot be replaced).

    python3 scripts/remake.py 2026-10-22-arthvan-short 2026-10-23-sglearning-short ...
    python3 scripts/remake.py --from 2026-10-22          every uploaded (not yet posted) piece from that day on
"""
import json
import os
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import pieces, secrets, youtube  # noqa: E402
from engine.config import ROOT  # noqa: E402


def hide_or_delete(channel: str, vid: str) -> str:
    tok = youtube.access_token(channel, os.environ)
    body = json.dumps({"id": vid, "status": {"privacyStatus": "private", "selfDeclaredMadeForKids": False}}).encode()
    req = urllib.request.Request("https://www.googleapis.com/youtube/v3/videos?part=status", data=body, method="PUT",
                                 headers={"Authorization": "Bearer " + tok, "Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, context=secrets.ssl_context()).read()
    except urllib.error.HTTPError as e:
        return f"hide failed {e.code}"
    req = urllib.request.Request(f"https://www.googleapis.com/youtube/v3/videos?id={vid}", method="DELETE", headers={"Authorization": "Bearer " + tok})
    try:
        urllib.request.urlopen(req, context=secrets.ssl_context())
        return "deleted"
    except urllib.error.HTTPError as e:
        return f"private (delete refused {e.code})"


def main(argv) -> int:
    if argv[:1] == ["--from"]:
        ids = sorted(p.id for p in pieces.list_all(ROOT) if p.id >= argv[1] and p.status == "uploaded" and p.ids.get("yt_id"))
    else:
        ids = argv
    for pid in ids:
        p = pieces.load(pid, ROOT)
        if not p or not p.script:
            print(pid, "skipped: no script"); continue
        vid = p.ids.get("yt_id")
        note = hide_or_delete(p.channel, vid) if vid else "no upload"
        for k in ("yt_id", "captions", "out_sha", "unlisted", "voice_batch", "art_batch", "write_batch"):
            p.ids.pop(k, None)
        pieces.save(pieces.transition(p, "written", "remake: clipped ending / repeated line / tone note (22 Oct 2026)"), ROOT)
        print(f"{pid}: old video {vid or '-'} {note}; status -> written")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
