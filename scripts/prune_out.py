"""Keep the repo light: drop out/<id>/ folders older than N days (longs are never committed; Shorts are needed by Instagram for a day or two),
and record the commit sha that holds each Short so Instagram can fetch it from raw.githubusercontent.com.

python scripts/prune_out.py --days 14
python scripts/prune_out.py --record-sha <sha>     after the commit that added out/<id>/: writes ids.out_sha into every uploaded piece lacking one
"""
import argparse
import json
import shutil
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KEEP_IN_OUT = {"reel.mp4", "story.mp4", "thumb.jpg", "captions.ass", "cover.jpg", "thumb_b.jpg", "teaser.jpg"}   # 27 Oct 2026: the Instagram cover and
# the click test's second thumbnail were pruned before use, so Reels showed a video frame and the test never ran


def prune(days: int, today: date | None = None) -> list:
    today = today or date.today()
    removed = []
    out = ROOT / "out"
    if not out.exists():
        return removed
    for folder in sorted(out.iterdir()):
        if not folder.is_dir():
            continue
        try:
            day = date.fromisoformat(folder.name[:10])
        except ValueError:
            continue
        if today - day > timedelta(days=days):
            shutil.rmtree(folder); removed.append(folder.name); continue
        for f in folder.iterdir():                       # inside a kept folder, only the files the publish step needs stay in git
            if f.is_dir() or (f.name not in KEEP_IN_OUT and not f.name.startswith("slide")):
                shutil.rmtree(f) if f.is_dir() else f.unlink()
    return removed


def record_sha(sha: str) -> list:
    done = []
    for path in sorted((ROOT / "pieces").glob("*.json")) if (ROOT / "pieces").exists() else []:
        d = json.loads(path.read_text())
        if d.get("kind") == "short" and d.get("status") in ("uploaded", "posted") and not d.get("ids", {}).get("out_sha") \
                and (ROOT / "out" / d["id"] / "reel.mp4").exists():
            d.setdefault("ids", {})["out_sha"] = sha
            path.write_text(json.dumps(d, ensure_ascii=False, sort_keys=True, indent=1) + "\n")
            done.append(d["id"])
    return done


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--days", type=int)
    ap.add_argument("--record-sha")
    a = ap.parse_args(argv)
    if a.days is not None:
        print("pruned:", prune(a.days))
    if a.record_sha:
        print("recorded sha for:", record_sha(a.record_sha))
    return 0


if __name__ == "__main__":
    sys.exit(main())
