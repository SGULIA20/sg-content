"""Remove a posted piece everywhere (founder, 29 Oct 2026: "delete the old one and story also", the basic Innodata layoff Reel once its
deeper remake was live). Tries YouTube (delete, else private), Instagram Reel and Story, Threads post and its poll reply, and records
what each platform said on the piece (topic["taken_down"]). The platform ids stay on the record so the publish job never posts it again.
Whatever a platform refuses through the API is named so the founder can delete it by hand.

    python3 scripts/take_down.py 2026-10-29-sglearning-x1
"""
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import instagram, pieces, secrets, threads  # noqa: E402
from engine.config import ROOT  # noqa: E402
from remake import hide_or_delete  # noqa: E402


def _try(fn) -> str:
    try:
        fn()
        return "deleted"
    except Exception as e:
        return "refused: " + secrets.scrub(str(e))[:160]


def main(argv) -> int:
    p = pieces.load(argv[0], ROOT)
    if p is None:
        print("no such piece"); return 2
    env, ids, out = os.environ, p.ids, {}
    if ids.get("yt_id"):
        out["youtube"] = hide_or_delete(p.channel, ids["yt_id"])
    ig_token = secrets.get("IG_ACCESS_TOKEN", env)
    for key, label in (("ig_reel_id", "instagram reel"), ("ig_story_id", "instagram story")):
        if ids.get(key) and str(ids[key]).isdigit():
            out[label] = _try(lambda k=key: instagram.call("DELETE", f"/{ids[k]}", ig_token))
    th_token = secrets.get("THREADS_ACCESS_TOKEN", env)
    for key, label in (("threads_poll_id", "threads poll"), ("threads_id", "threads post")):
        if ids.get(key) and str(ids[key]).isdigit():
            out[label] = _try(lambda k=key: threads.call("DELETE", f"/{ids[k]}", th_token))
    p.topic["taken_down"] = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), **out}
    if p.status == "uploaded":                              # not posted yet: the publish job must never pick it up (30 Oct 2026)
        p = pieces.transition(p, "rejected", "taken down: replaced by a remake")
    pieces.save(p, ROOT)
    for k, v in out.items():
        print(f"{p.id} {k}: {v}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
