"""Clear the schedule and start again (founder, 27 Nov 2026: "Remove all scheduled posts and let us go with what we decided means all
new changes in both channels for both short and long videos").

Every video still waiting on YouTube with a future publish time is taken OFF the schedule: made private with no publish time. It is
kept, never deleted, so a wrong removal can be put back by hand in YouTube Studio. Videos made the new way (real music under the
voice, the December build) are left on the schedule. Each removed piece's record is moved to pieces/replaced/, and its pictures, old
clip and old thumbnail are removed from the working folders, so the slot is empty and the next produce run makes a new video for it:
planner topic, scored hooks, music, review. Nothing already published is touched.

    python scripts/restart_schedule.py            list only
    python scripts/restart_schedule.py --apply    do it
"""
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import intro, pieces, youtube  # noqa: E402
from engine.config import ROOT  # noqa: E402

DATA = "https://www.googleapis.com/youtube/v3"


def new_style(p) -> bool:
    return (p.ids or {}).get("sound") == "track"


def unschedule(channel: str, vid: str, call=None, token_for=None) -> str:
    call = call or youtube.call
    token = (token_for or youtube.access_token)(channel)
    status, _h, body = call("PUT", f"{DATA}/videos?part=status", token,
                            {"id": vid, "status": {"privacyStatus": "private", "selfDeclaredMadeForKids": False}})
    return "off the schedule" if status == 200 and not ((body or {}).get("status") or {}).get("publishAt") else f"FAILED ({status})"


def plan(root: Path, rows: dict, now: datetime) -> tuple:
    """(videos to take off the schedule [(channel, row)], pieces to set aside [piece]). Rows are intro.audit_channels' rows."""
    all_pieces = pieces.list_all(root)
    keep = {p.ids["yt_id"] for p in all_pieces if p.ids.get("yt_id") and new_style(p)}
    stamp = now.strftime("%Y-%m-%dT%H:%M")
    videos = [(ch, r) for ch, rs in rows.items() for r in rs if r.get("publishAt") and r["publishAt"][:16] > stamp and r["id"] not in keep]
    going = {r["id"] for _ch, r in videos}
    aside = [p for p in all_pieces if p.status == "uploaded" and p.ids.get("yt_id") in going]
    return videos, aside


def set_aside(root: Path, p) -> None:
    src = root / "pieces" / f"{p.id}.json"
    dst = root / "pieces" / "replaced" / f"{p.id}.json"
    dst.parent.mkdir(parents=True, exist_ok=True)
    data = json.loads(src.read_text())
    data.setdefault("topic", {})["replaced"] = "27 Nov 2026: taken off the schedule, the slot is re-made the new way"
    dst.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")
    src.unlink()
    shutil.rmtree(root / "out" / p.id, ignore_errors=True)
    for old in (root / "inbox" / "intro" / f"{p.id}.mp4", root / "inbox" / "thumb" / f"{p.id}.jpg"):
        old.unlink(missing_ok=True)                           # his old clip and thumbnail belong to the old video


def main(argv) -> int:
    apply = "--apply" in argv
    now = datetime.now(timezone.utc)
    rows = intro.audit_channels(ROOT, out=lambda *_a: None)
    videos, aside = plan(ROOT, rows, now)
    print(f"{len(videos)} scheduled video(s) to take off the schedule, {len(aside)} piece record(s) to set aside" + ("" if apply else " (list only)"), flush=True)
    failed = []
    for ch, r in videos:
        result = unschedule(ch, r["id"]) if apply else "would be taken off"
        if result.startswith("FAILED"):
            failed.append(r["id"])
        print(f"{ch:10} {r['publishAt'][:16]}  {r['id']}  {r['title'][:50]:50}  {r.get('piece') or 'NOT IN REPO':32} {result}", flush=True)
    for p in aside:
        if p.ids.get("yt_id") in failed:
            print(f"{p.id}: kept, its video could not be taken off the schedule", flush=True)
            continue
        if apply:
            set_aside(ROOT, p)
        print(f"{p.id}: {'set aside' if apply else 'would be set aside'}", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
