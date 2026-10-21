"""Fill the buffer: make the pieces the calendar needs, in order, within the day's budgets, then tell the founder (spec §3, §7).

python -m engine.produce [--max 3] [--dry-run] [--only sglearning:short,arthvan:long] [--long-minutes 3] [--date YYYY-MM-DD]
Exit 0 also when a budget stopped the run early (that is normal); exit 1 only on an unexpected exception.
"""
import argparse
import json
import os
import sys
import traceback
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import buffer, digest, gitsync, pieces, pipeline, secrets, slots, telegram
from .config import ROOT

MAX_DEFAULT = 3


def _log_run(root: Path, record: dict) -> None:
    path = Path(root) / "logs" / "runs.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


FALLBACK_HOURS = 3           # a pack still waiting for clips this close to its slot is rendered the automatic way
PACK_STATUSES = ("awaiting-clips", "awaiting-confirm")


def run(root: Path = ROOT, today: date | None = None, max_pieces: int = MAX_DEFAULT, dry_run: bool = False, only: set | None = None,
        long_minutes: int | None = None, deps: pipeline.Deps | None = None, notify=telegram.send, mode: str = "auto",
        now_utc: datetime | None = None) -> int:
    now_utc = now_utc or datetime.now(timezone.utc)
    today = today or slots.ist(now_utc).date()
    if telegram.paused(root):
        print("paused: nothing made", flush=True)
        return 0
    deps = deps or pipeline.real_deps(root)
    plan = buffer.needed(root, today)
    if only:
        plan = [(d, c, k) for d, c, k in plan if f"{c}:{k}" in only]
    made, stopped, ok = [], "", True
    try:
        for day, channel, kind in plan[:max_pieces]:
            pid = slots.piece_id(day, channel, kind)
            piece = pieces.load(pid, root) or pieces.Piece(id=pid, channel=channel, kind=kind, publish_day=day)
            if piece.status in buffer.DONE:
                continue
            if piece.status in PACK_STATUSES:
                deadline = slots.publish_at(channel, kind, day) - timedelta(hours=FALLBACK_HOURS)
                if mode == "pack" or now_utc < deadline:
                    continue                                               # the founder's clips may still come
                pieces.transition(piece, "written", f"pack cancelled: no clips {FALLBACK_HOURS} h before the slot; rendered the automatic way")
                notify(f"{pid}: pack cancelled, rendering the automatic version instead")
            if not (piece.script and piece.status in pipeline.RESUMABLE):
                piece.status = "planned"                                   # a parked piece keeps its script and resumes
            if kind == "long" and long_minutes:
                pipeline.LONG_TARGET_MINUTES[channel] = long_minutes
            print(f"making {pid}", flush=True)
            try:
                piece = pipeline.make(piece, deps, root, dry_run=dry_run, pack_mode=(mode == "pack"))
            except Exception as e:                          # one piece's surprise never stops the others (21 Oct crash)
                ok = False
                traceback.print_exc()
                reason = f"crashed: {type(e).__name__}: {secrets.scrub(str(e))[:200]}"
                pieces.save(pieces.transition(piece, "failed-crash", reason), root)
                made.append((pid, reason))
                gitsync.safe_commit(root, f"produce: {pid} failed-crash")
                continue
            made.append((pid, piece.status))
            gitsync.safe_commit(root, f"produce: {pid} {piece.status}")
            print(f"  -> {piece.status}" + (f": {piece.reasons[-1]}" if piece.reasons else ""), flush=True)
            if piece.status in ("failed-voice", "failed-art"):
                stopped = piece.status
                break
    except Exception as e:                                  # anything unexpected: log it, report it, exit 1
        ok = False
        traceback.print_exc()
        made.append(("run", f"crashed: {type(e).__name__}: {str(e)[:200]}"))
    _log_run(root, {"day": today.isoformat(), "at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "ok": ok,
                    "dry_run": dry_run, "made": made, "stopped": stopped})
    text = digest.run_summary(root, today)
    if stopped:
        text += f"\nStopped for today: {stopped}. It carries on at the next run."
    alerts = digest.alerts(root, today)
    if alerts:
        text += "\nALERTS:\n" + "\n".join("  ! " + a for a in alerts)
    if not ok:
        text += "\nCRASHED (the other pieces carried on): " + "; ".join(f"{a} {b}" for a, b in made if str(b).startswith("crashed"))
    if not dry_run or os.environ.get("NOTIFY_DRY_RUN") == "1":
        notify(text)
    print(text, flush=True)
    return 0 if ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--max", type=int, default=MAX_DEFAULT)
    ap.add_argument("--dry-run", action="store_true", help="stop before upload; files stay in out/")
    ap.add_argument("--only", help="comma list of channel:kind to make, e.g. sglearning:short,arthvan:long")
    ap.add_argument("--long-minutes", type=int, help="override the long video target (for a quick test render)")
    ap.add_argument("--date", help="IST date YYYY-MM-DD (default today)")
    ap.add_argument("--mode", choices=["auto", "pack"], default="auto", help="pack = write the script and send the Gemini prompt pack, no render")
    a = ap.parse_args(argv)
    telegram.poll_commands(status_fn=lambda: digest.status_line(ROOT))
    return run(ROOT, date.fromisoformat(a.date) if a.date else None, a.max, a.dry_run,
               set(a.only.split(",")) if a.only else None, a.long_minutes, mode=a.mode)


if __name__ == "__main__":
    sys.exit(main())
