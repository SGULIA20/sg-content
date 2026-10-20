"""What the buffer still needs: Shorts seven days ahead, longs a little further, longs first (spec §3 buffer rule)."""
from datetime import date, timedelta
from pathlib import Path

from . import pieces, slots
from . import config
from .config import CHANNELS, ROOT

DONE = {"uploaded", "posted"}


def long_for_short(channel: str, day: date) -> str:
    """The long whose scenes a mythology Short is cut from: the most recent long publish day at or before the Short's day."""
    long_day = CHANNELS[channel].long_day
    back = (day.weekday() - long_day) % 7 or 7            # strictly before: a Short never cuts from a long published the same day
    return slots.piece_id(day - timedelta(days=back), channel, "long")


def next_long_for_short(channel: str, day: date) -> str:
    """The long published after the Short's day (used as a teaser source when the previous long does not exist yet, e.g. launch week)."""
    long_day = CHANNELS[channel].long_day
    ahead = (long_day - day.weekday()) % 7 or 7
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
    return [x for x in sorted(longs) + sorted(shorts) if x[2] in config.ENABLED_KINDS]
