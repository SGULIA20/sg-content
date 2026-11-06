"""Gemini credit left, as an estimate (founder, 29 Oct 2026: the prepaid balance ran out without warning; Google gives the pipeline no
way to read it). Counts down from the newest top-up in content/gemini-credit.json.

6 Nov 2026 (founder: "fix the credit meter to count all Gemini calls"): the meter now adds up every call the repo can see, not just
pictures: pictures (logs/image-spend.json, exact), text calls by tokens and search queries (logs/gemini-calls.jsonl), single voice
requests (logs/voice-budget.json) and batched voice lines (logs/voice-batch.jsonl). The rates below are estimates, so the total is
then scaled by a factor learned from the last time the founder read a real balance (a top-up entry carrying "spent_since_previous"):
real spend over metered spend for the same days. What the repo cannot see (arthvan-media and ScoreMyBiz share the key) lands in that factor."""
import json
from datetime import date, timedelta
from pathlib import Path

from .config import CONTENT_DIR, ROOT

# Rupee rates, estimates (not read from Google); the learned factor corrects them.
INR_PER_M_TOKENS_IN = 26.0
INR_PER_M_TOKENS_OUT = 220.0           # output and thinking tokens
INR_PER_SEARCH_QUERY = 3.0
INR_PER_VOICE_REQUEST = 1.5
INR_PER_VOICE_BATCH_LINE = 0.75
DEFAULT_FACTOR = 1.3                   # until a real balance reading has taught the meter
FACTOR_RANGE = (1.0, 4.0)
WARN_DAYS = 3
RATE_DAYS = 3                    # the daily rate is the average of the last few full days


def _read(path: Path, default):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return default


def _lines(path: Path):
    try:
        for row in Path(path).read_text().splitlines():
            try:
                yield json.loads(row)
            except ValueError:
                continue
    except OSError:
        return


def day_costs(root: Path = ROOT) -> dict:
    """{"2026-11-05": rupees, ...}: everything the repo's logs show was spent on Gemini that day, before the learned factor."""
    logs = Path(root) / "logs"
    days = {}

    def add(day, inr):
        days[day] = days.get(day, 0.0) + inr
    for d, v in _read(logs / "image-spend.json", {}).items():
        add(d, float(v.get("inr", 0)))
    for r in _lines(logs / "gemini-calls.jsonl"):
        if "IMAGE" in (r.get("modalities") or []):
            continue                                                   # pictures are already counted above
        add(r.get("at", "")[:10], (r.get("in", 0) or 0) / 1e6 * INR_PER_M_TOKENS_IN
            + ((r.get("out", 0) or 0) + (r.get("thought", 0) or 0)) / 1e6 * INR_PER_M_TOKENS_OUT
            + (r.get("search_queries", 0) or 0) * INR_PER_SEARCH_QUERY)
    for d, n in _read(logs / "voice-budget.json", {}).items():
        add(d, float(n) * INR_PER_VOICE_REQUEST)
    for r in _lines(logs / "voice-batch.jsonl"):
        add(r.get("at", "")[:10], float(r.get("lines", 0) or 0) * INR_PER_VOICE_BATCH_LINE)
    return days


def _between(days: dict, start: date, end: date) -> float:
    return sum(v for d, v in days.items() if d and start <= date.fromisoformat(d) < end)


def factor(tops: list, days: dict) -> float:
    """Real spend over metered spend between the last two balance readings; DEFAULT_FACTOR when no reading says."""
    for i in range(len(tops) - 1, 0, -1):
        real = tops[i].get("spent_since_previous")
        if real:
            metered = _between(days, date.fromisoformat(tops[i - 1]["day"]), date.fromisoformat(tops[i]["day"]))
            if metered > 0:
                return min(max(real / metered, FACTOR_RANGE[0]), FACTOR_RANGE[1])
    return DEFAULT_FACTOR


def estimate(today: date, root: Path = ROOT, content: Path = CONTENT_DIR) -> dict | None:
    """{"loaded", "since", "spent", "left", "per_day", "days", "factor"} or None when no top-up is recorded; loaded is None when the amount is unknown."""
    tops = [t for t in _read(Path(content) / "gemini-credit.json", {}).get("topups", []) if t.get("day")]
    if not tops:
        return None
    last = tops[-1]
    days = day_costs(root)
    f = factor(tops, days)
    since = date.fromisoformat(last["day"])
    spent = _between(days, since, today + timedelta(days=1)) * f
    recent = [days.get((today - timedelta(days=k)).isoformat(), 0) for k in range(1, RATE_DAYS + 1)]
    per_day = sum(recent) / RATE_DAYS * f
    out = {"loaded": last.get("inr"), "since": since, "spent": round(spent), "per_day": round(per_day), "factor": round(f, 2)}
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
