"""Changes the titles of existing YouTube videos from content/retitle-plan.json (founder, 7 Nov 2026: seven near-identical Unakoti Shorts get
distinct angles). `check` prints old and new and changes nothing. `apply` reads each video's whole snippet and writes it back with only the title
changed, because videos.update clears any snippet field it is not sent. Privacy and the scheduled time are untouched.

python -m engine.ytretitle check|apply
"""
import json
import sys
from pathlib import Path

from . import youtube
from .config import ROOT

PLAN = ROOT / "content" / "retitle-plan.json"
API = "https://www.googleapis.com/youtube/v3/videos"


def retitle(token: str, video_id: str, title: str, apply: bool, call=youtube.call) -> str:
    status, _h, body = call("GET", f"{API}?part=snippet&id={video_id}", token)
    items = (body or {}).get("items") or []
    if status != 200 or not items:
        return f"{video_id}: cannot read it ({status})"
    snip = items[0]["snippet"]
    if snip.get("title") == title:
        return f"{video_id}: already '{title}'"
    if not apply:
        return f"{video_id}: would change '{snip.get('title')}' -> '{title}'"
    keep = {k: snip[k] for k in ("categoryId", "description", "tags", "defaultLanguage", "defaultAudioLanguage") if k in snip}
    status, _h, out = call("PUT", f"{API}?part=snippet", token, json_body={"id": video_id, "snippet": {**keep, "title": title}})
    return f"{video_id}: changed to '{title}'" if status == 200 else f"{video_id}: FAILED ({status}) {str(out)[:120]}"


def run(plan: dict, apply: bool, token_for=youtube.access_token, call=youtube.call, out=print) -> list:
    token = token_for(plan["channel"])
    lines = [retitle(token, vid, title, apply, call) for vid, title in plan["titles"].items()]
    for line in lines:
        out(line)
    return lines


def main(argv=None) -> int:
    mode = (argv if argv is not None else sys.argv[1:] or ["check"])[0]
    lines = run(json.loads(PLAN.read_text(encoding="utf-8")), mode == "apply")
    return 1 if any("FAILED" in l or "cannot" in l for l in lines) else 0


if __name__ == "__main__":
    sys.exit(main())
