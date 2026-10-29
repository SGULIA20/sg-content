"""Gemini credit left, as an estimate (founder, 29 Oct 2026: the prepaid balance ran out without warning; Google gives the pipeline no
way to read it). Counts down from the newest top-up in content/gemini-credit.json using our own picture meter (logs/image-spend.json)
times UNMETERED_FACTOR for what we do not meter (voice, research, retries): 24-29 Oct, Rs 2,000 went while pictures metered Rs 1,274."""
import json
from datetime import date, timedelta
from pathlib import Path

from .config import CONTENT_DIR, ROOT

UNMETERED_FACTOR = 1.6
WARN_DAYS = 3
RATE_DAYS = 3                    # the daily rate is the average of the last few full days


def _read(path: Path, default):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return default


def estimate(today: date, root: Path = ROOT, content: Path = CONTENT_DIR) -> dict | None:
    """{"loaded", "since", "spent", "left", "per_day", "days"} or None when no top-up is recorded; loaded is None when the amount is unknown."""
    tops = [t for t in _read(Path(content) / "gemini-credit.json", {}).get("topups", []) if t.get("day")]
    if not tops:
        return None
    last = tops[-1]
    spend = _read(Path(root) / "logs" / "image-spend.json", {})
    since = date.fromisoformat(last["day"])
    spent = sum(v.get("inr", 0) for d, v in spend.items() if since < date.fromisoformat(d) <= today) * UNMETERED_FACTOR
    recent = [spend.get((today - timedelta(days=k)).isoformat(), {}).get("inr", 0) for k in range(1, RATE_DAYS + 1)]
    per_day = sum(recent) / RATE_DAYS * UNMETERED_FACTOR
    out = {"loaded": last.get("inr"), "since": since, "spent": round(spent), "per_day": round(per_day)}
    if out["loaded"] is not None:
        out["left"] = round(out["loaded"] - spent)
        out["days"] = (out["left"] / per_day) if per_day else None
    return out


def line(today: date, root: Path = ROOT, content: Path = CONTENT_DIR) -> str:
    e = estimate(today, root, content)
    if e is None:
        return ""
    if e["loaded"] is None:
        return (f"💳 Gemini credit: topped up {e['since']:%d %b}, amount not recorded yet; tell Claude the amount to start the countdown "
                f"(spending about ₹{e['per_day']} a day).")
    days = e.get("days")
    when = f", about {days:.0f} days at ₹{e['per_day']} a day" if days is not None else ""
    if e["left"] <= 0 or (days is not None and days < WARN_DAYS):
        return f"🔴 Gemini credit nearly gone (estimate): about ₹{max(e['left'], 0)} left{when}. Top up now: aistudio.google.com → Billing."
    return f"💳 Gemini credit left (estimate): about ₹{e['left']} of ₹{e['loaded']}{when}."
