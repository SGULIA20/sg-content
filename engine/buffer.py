"""What the buffer still needs: Shorts seven days ahead, longs a little further, longs first (spec §3 buffer rule)."""
from datetime import date, timedelta
from pathlib import Path

from . import pieces, slots
from . import config
from .config import CHANNELS, ROOT

DONE = {"uploaded", "posted"}


def long_for_short(channel: str, day: date) -> str:
    """The long whose scenes a mythology Short is cut from: the most recent long publish day at or before the Short's day."""
    back = min(((day.weekday() - ld) % 7 or 7) for ld in CHANNELS[channel].long_days)   # most recent long strictly before the Short's day
    return slots.piece_id(day - timedelta(days=back), channel, "long")


def next_long_for_short(channel: str, day: date) -> str:
    """The long published after the Short's day (used as a teaser source when the previous long does not exist yet, e.g. launch week)."""
    ahead = min(((ld - day.weekday()) % 7 or 7) for ld in CHANNELS[channel].long_days)
    return slots.piece_id(day + timedelta(days=ahead), channel, "long")


def needed(root: Path = ROOT, today_ist: date | None = None, horizon_short: int = 7, horizon_long: int = 3) -> list:
    """[(publish_day, channel, kind)] not yet uploaded, longs first (by date), then Shorts (by date, then channel)."""
    today_ist = today_ist or date.today()
    done = {p.id for p in pieces.list_all(root) if p.status in DONE}
    longs, shorts = [], []
    for ch in CHANNELS:
        for day in slots.publish_dates(ch, "long", today_ist, horizon_short + horizon_long):
            if slots.piece_id(day, ch, "long") not in done:
                longs.append((day, ch, "long"))
        for day in slots.publish_dates(ch, "short", today_ist, horizon_short):
            if slots.piece_id(day, ch, "short") not in done:
                shorts.append((day, ch, "short"))
    longs, shorts = sorted(longs), sorted(shorts)
    # order: the Shorts due today or tomorrow, then one long, then the rest day by day (a long eats most of the daily voice quota)
    soon = [x for x in shorts if (x[0] - today_ist).days <= 0]        # today's Shorts first (tomorrow's come in tomorrow's run)
    later = [x for x in shorts if (x[0] - today_ist).days > 0]
    ordered = soon + longs[:1]
    rest_longs = longs[1:]
    for x in later:
        ordered.append(x)
        if rest_longs and (x[0] - today_ist).days % 2 == 0:
            ordered.append(rest_longs.pop(0))
    ordered += rest_longs
    return [x for x in ordered if x[2] in config.ENABLED_KINDS]
