"""IST slot maths and the publish calendar (spec §1, §3 schedules). IST = UTC+5:30, no daylight saving."""
from datetime import date, datetime, timedelta, timezone

from . import config

IST = timezone(timedelta(hours=5, minutes=30), name="IST")

# A third long a week for two weeks, on the days neither channel has one, so the proven Short questions get their 12-minute telling
# three weeks earlier than the Wed/Sat and Thu/Sun rotation allows (founder, 4 Nov 2026: "Do 1"): Learning with SG Mon 9 and 16 Nov
# (gold on Dhanteras, US stocks from $1), SG-MYTH-WORLD Tue 10 and 17 Nov (Sanchi, Ram Setu). Explicit dates: nothing after them.
EXTRA_LONG_DAYS = {"sglearning": (date(2026, 11, 9), date(2026, 11, 16)), "arthvan": (date(2026, 11, 10), date(2026, 11, 17))}


# Long videos every other day (founder, 28 Nov 2026: "long videos suppose to go every alternate day mon, wed, fri - SG learning and tue, thur,
# sat SG myth"): three a week on each channel from Sunday 29 Nov. Before that date the old table (Learning Wed + Sat, SG-MYTH Thu + Sun) holds,
# so every video already made, scheduled or measured keeps its day.
LONG_DAYS_FROM = date(2026, 11, 29)
OLD_LONG_DAYS = {"sglearning": frozenset({2, 5}), "arthvan": frozenset({3, 6})}


def is_long_day(channel: str, d: date) -> bool:
    days = config.CHANNELS[channel].long_days if d >= LONG_DAYS_FROM else OLD_LONG_DAYS[channel]
    return d.weekday() in days or d in EXTRA_LONG_DAYS.get(channel, ())


def ist(dt_utc: datetime) -> datetime:
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)
    return dt_utc.astimezone(IST)


def utc_for(day: date, hhmm_ist: str) -> datetime:
    h, m = (int(x) for x in hhmm_ist.split(":"))
    return datetime(day.year, day.month, day.day, h, m, tzinfo=IST).astimezone(timezone.utc)


def publish_dates(channel: str, kind: str, start: date, days: int) -> list:
    ch = config.CHANNELS[channel]
    out = []
    for i in range(days):
        d = start + timedelta(days=i)
        if kind == "short" and d.weekday() in ch.short_days:
            out.append(d)
        elif kind == "long" and is_long_day(channel, d):
            out.append(d)
    return out


def piece_id(day: date, channel: str, kind: str) -> str:
    return f"{day.isoformat()}-{channel}-{kind}"


def publish_at(channel: str, kind: str, day: date) -> datetime:
    ch = config.CHANNELS[channel]
    return utc_for(day, ch.short_publish_ist if kind == "short" else ch.long_publish_ist)


def ig_slot_ok(dt_ist: datetime) -> bool:
    h, m = (int(x) for x in config.APP_JOB_IG_SLOT_IST.split(":"))
    guard = dt_ist.replace(hour=h, minute=m, second=0, microsecond=0)
    return abs((dt_ist - guard).total_seconds()) > config.IG_GUARD_MINUTES * 60
