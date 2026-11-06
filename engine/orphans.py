"""Moves videos that were made outside the one-day-one-video rule to free December days (founder, 6 Nov 2026: "Reschedule them on next
month, money already spent"). The plan lives in content/orphans-plan.json. `check` only reports; `apply` moves each video that is
still waiting on its old day and whose new slot is empty. A video already on its new day is left alone, so it can be run again."""
import argparse
import json
import sys
from datetime import datetime, timezone

from . import slots, youtube
from .config import ROOT

PLAN = ROOT / "content" / "orphans-plan.json"


def load_plan(path=PLAN) -> list:
    return json.loads(path.read_text(encoding="utf-8"))["moves"]


def target(move: dict) -> datetime:
    from datetime import date
    return slots.publish_at(move["channel"], move["kind"], date.fromisoformat(move["date"]))


def run(moves, apply=False, token_for=None, scheduled_at=None, reschedule=None, out=print) -> dict:
    token_for = token_for or (lambda ch: youtube.access_token(ch))
    scheduled_at = scheduled_at or youtube.scheduled_at
    reschedule = reschedule or youtube.reschedule
    tokens, result = {}, {"moved": [], "already": [], "blocked": [], "failed": []}
    for m in moves:
        when = target(m)
        token = tokens.setdefault(m["channel"], token_for(m["channel"]))
        held = scheduled_at(token, when)
        label = f"{m['video']} ({m['channel']} {m['kind']}) -> {m['date']}"
        if m["video"] in held:
            result["already"].append(m["video"]); out(f"already there: {label}"); continue
        if held:
            result["blocked"].append(m["video"]); out(f"BLOCKED, slot holds {', '.join(held)}: {label}"); continue
        if not apply:
            out(f"would move: {label}"); continue
        if reschedule(token, m["video"], when):
            result["moved"].append(m["video"]); out(f"moved: {label}")
        else:
            result["failed"].append(m["video"]); out(f"FAILED: {label}")
    return result


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["check", "apply"])
    a = ap.parse_args(argv)
    r = run(load_plan(), apply=a.mode == "apply")
    return 1 if r["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
