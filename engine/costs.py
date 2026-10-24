"""What each piece costs (founder, 24 Oct 2026: no charges on waste or repeated work). While a piece is being made, every picture, Claude call
and voice line that is paid for adds itself here; pipeline.make stores the running total on the piece (ids["cost"]) so a piece that needs
re-drawing, re-voicing or re-making shows it. The 9 pm digest names a recent piece that cost more than three times the usual for its kind.

    python -m engine.costs        every piece with a cost, the median per kind and the pieces far above it
Voice is counted in lines, not rupees: the Gemini voice meter is a request allowance, so total_inr leaves it out."""
import contextlib
import statistics
import sys
import threading
from datetime import date, datetime
from pathlib import Path

from .config import ROOT, today_ist

INR_PER_USD = 90.0                     # a little above the real rate: the figure should overstate, never understate
ALERT_FACTOR = 3.0
MIN_PIECES = 5                         # fewer pieces of a kind than this is too little to call one of them unusual
RECENT_DAYS = 2                        # only a piece touched in the last two days alerts, so an old one does not repeat every night

_lock = threading.Lock()
_active: dict | None = None


@contextlib.contextmanager
def track():
    """Everything paid for inside the block lands in the dict it yields."""
    global _active
    spent = {"inr": 0.0, "usd": 0.0, "voice": 0}
    with _lock:
        before, _active = _active, spent
    try:
        yield spent
    finally:
        with _lock:
            _active = before


def add(inr: float = 0.0, usd: float = 0.0, voice: int = 0) -> None:
    with _lock:
        if _active is not None:
            _active["inr"] = round(_active["inr"] + inr, 2)
            _active["usd"] = round(_active["usd"] + usd, 6)
            _active["voice"] += voice


def nonzero(spent: dict) -> bool:
    return bool(spent["inr"] or spent["usd"] or spent["voice"])


def merge(a: dict | None, b: dict) -> dict:
    a = a or {}
    return {"inr": round(a.get("inr", 0.0) + b.get("inr", 0.0), 2), "usd": round(a.get("usd", 0.0) + b.get("usd", 0.0), 6),
            "voice": int(a.get("voice", 0)) + int(b.get("voice", 0))}


def total_inr(cost: dict) -> float:
    return cost.get("inr", 0.0) + cost.get("usd", 0.0) * INR_PER_USD


def outliers(rows: list, factor: float = ALERT_FACTOR, min_pieces: int = MIN_PIECES) -> list:
    """rows = [(piece id, total rupees)] of one kind -> [(id, total, median)] for each far above the median."""
    if len(rows) < min_pieces:
        return []
    median = statistics.median(t for _id, t in rows)
    return [(pid, t, median) for pid, t in rows if median > 0 and t > factor * median]


def _kinds(root: Path) -> dict:
    from . import pieces
    kinds: dict = {}
    for p in pieces.list_all(root):
        if p.ids.get("cost"):
            kinds.setdefault(p.kind, []).append(p)
    return kinds


def alerts(root: Path = ROOT, day: date | None = None) -> list:
    day = day or today_ist()
    out = []
    for kind, plist in _kinds(root).items():
        recent = {}
        for p in plist:
            try:
                recent[p.id] = (day - datetime.fromisoformat(p.updated).date()).days <= RECENT_DAYS
            except ValueError:
                recent[p.id] = False
        for pid, total, median in outliers([(p.id, total_inr(p.ids["cost"])) for p in plist]):
            if recent.get(pid):
                out.append(f"{pid} cost ₹{total:.0f}, {total / median:.1f}x the usual ₹{median:.0f} for a {kind}: look for redraws or re-makes in logs/runs.jsonl")
    return out


def main(argv=None) -> int:
    for kind, plist in sorted(_kinds(ROOT).items()):
        rows = sorted(((p.id, total_inr(p.ids["cost"])) for p in plist), key=lambda r: r[0])
        median = statistics.median(t for _id, t in rows)
        print(f"{kind}: {len(rows)} piece(s) with a cost, median ₹{median:.0f}")
        flagged = {pid for pid, _t, _m in outliers(rows)}
        for pid, t in rows:
            cost = next(p for p in plist if p.id == pid).ids["cost"]
            print(f"  {pid}  ₹{t:.0f}  ({cost.get('inr', 0):.0f} pictures + ${cost.get('usd', 0):.2f} Claude + {cost.get('voice', 0)} voice lines)" + ("   <-- unusual" if pid in flagged else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
