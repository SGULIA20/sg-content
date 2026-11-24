"""One message, once (founder, 24 Nov 2026: "I am getting n number of duplicate messages on my both bots ... if not relevant then
remove"). The same workflows are started several times a day as a safety net, and the Studio sweep runs every five minutes; a report
with nothing new in it, or a failure that had already been told, went out on every one of those runs.

`fresh(key, what)` answers whether this has NOT been said yet: `key` names the message (for example "produce" or "thumb-refused:<id>")
and `what` is the part that matters (the list of problems, a file's hash). The same key with the same content is told once in
`hours`; changed content is told at once. The record lives in logs/told.json, which every job already commits with its logs.
"""
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import ROOT

FILE = "logs/told.json"
KEEP = timedelta(days=4)


def _load(root: Path) -> dict:
    try:
        return json.loads((Path(root) / FILE).read_text())
    except (OSError, ValueError):
        return {}


def fresh(key: str, what="", hours: float = 20, root: Path = ROOT, now: datetime | None = None) -> bool:
    """True, and remembered, when `key` has not carried this `what` in the last `hours`; False when it has (say nothing)."""
    now = now or datetime.now(timezone.utc)
    mark = hashlib.sha256(json.dumps(what, sort_keys=True, default=str, ensure_ascii=False).encode()).hexdigest()[:16]
    told = _load(root)
    last = told.get(key) or {}
    try:
        recent = now - datetime.fromisoformat(last.get("at", "")) < timedelta(hours=hours)
    except ValueError:
        recent = False
    if last.get("mark") == mark and recent:
        return False
    told[key] = {"mark": mark, "at": now.isoformat(timespec="seconds")}
    cutoff = (now - KEEP).isoformat(timespec="seconds")
    told = {k: v for k, v in told.items() if str(v.get("at", "")) >= cutoff}
    path = Path(root) / FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(told, indent=1, sort_keys=True))
    return True
