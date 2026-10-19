"""Text for the founder: what a run made, what is in the buffer, what it cost, and alerts (spec §3 step 12, §7)."""
import json
from datetime import date, timedelta
from pathlib import Path

from . import pieces, slots, telegram
from .config import BUDGETS, CHANNELS, ROOT, today_ist

BUFFER_ALERT_DAYS = 2
TOKEN_ALERT_DAYS = 7


def _json(path: Path) -> dict:
    try:
        return json.loads(Path(path).read_text())
    except (FileNotFoundError, ValueError):
        return {}


def _touched_today(p, day: date) -> bool:
    """`updated` is UTC; the founder's day is IST."""
    if not p.updated:
        return False
    try:
        from datetime import datetime
        return slots.ist(datetime.fromisoformat(p.updated)).date() == day
    except ValueError:
        return p.updated[:10] == day.isoformat()


def buffer_days(root: Path, today: date, horizon: int = 14) -> dict:
    """Per channel: how many consecutive upcoming Short slots (from today) already have an uploaded or posted piece."""
    ready = {p.id for p in pieces.list_all(root) if p.status in ("uploaded", "posted")}
    out = {}
    for ch in CHANNELS:
        n = 0
        for day in slots.publish_dates(ch, "short", today, horizon):
            if slots.piece_id(day, ch, "short") in ready:
                n += 1
            else:
                break
        out[ch] = n
    return out


def run_summary(root: Path, day: date) -> str:
    rows = pieces.list_all(root)
    today = [p for p in rows if _touched_today(p, day)]
    made = [p for p in today if p.status in ("uploaded", "posted")]
    rejected = [p for p in today if p.status == "rejected"]
    failed = [p for p in today if p.status.startswith("failed-") or p.status == "qa_failed"]
    posted = [p for p in today if p.status == "posted"]
    voice = int(_json(Path(root) / "logs" / "voice-budget.json").get(day.isoformat(), 0))
    inr = float(_json(Path(root) / "logs" / "image-spend.json").get(day.isoformat(), {}).get("inr", 0))
    usd = float(_json(Path(root) / "logs" / "claude-spend.json").get(day.isoformat(), {}).get("usd", 0))
    buf = buffer_days(root, day)
    lines = [f"SG Content {day.isoformat()}: made {len(made)}, rejected {len(rejected)}, failed {len(failed)}, posted {len(posted)}"]
    for p in made:
        lines.append(f"  + {p.id} ({p.writer or 'claude'})")
    for p in rejected + failed:
        lines.append(f"  - {p.id}: {p.status}: {p.reasons[-1] if p.reasons else ''}")
    lines.append("buffer: " + ", ".join(f"{ch} {n} day{'s' if n != 1 else ''}" for ch, n in buf.items()))
    lines.append(f"spend: voice {voice}/{BUDGETS['voice_requests_per_day']} requests, images ₹{inr:.0f}, Claude ${usd:.2f}")
    if telegram.paused(root):
        lines.append("PAUSED (/resume to continue)")
    return "\n".join(lines)


def alerts(root: Path, day: date) -> list:
    out = []
    for ch, n in buffer_days(root, day).items():
        if n < BUFFER_ALERT_DAYS:
            out.append(f"{ch}: buffer is {n} day(s); the next Short slot has nothing ready")
    runs_path = Path(root) / "logs" / "runs.jsonl"
    if runs_path.exists():
        runs = [json.loads(l) for l in runs_path.read_text().splitlines() if l.strip()]
        if len(runs) >= 2 and not runs[-1].get("ok", True) and not runs[-2].get("ok", True):
            out.append("two consecutive runs failed; see logs/runs.jsonl")
    tokens = _json(Path(root) / "logs" / "tokens.json")
    for key, name in (("instagram_expires", "Instagram token"), ("threads_expires", "Threads token")):
        if tokens.get(key):
            try:
                left = (date.fromisoformat(tokens[key]) - day).days
            except ValueError:
                continue
            if left <= TOKEN_ALERT_DAYS:
                out.append(f"{name} expires in {left} day(s): run the refresh workflow or re-authorise")
    return out


def status_line(root: Path = ROOT, day: date | None = None) -> str:
    day = day or today_ist()
    buf = buffer_days(root, day)
    state = "paused" if telegram.paused(root) else "running"
    return f"{state}; buffer " + ", ".join(f"{ch} {n}d" for ch, n in buf.items())
