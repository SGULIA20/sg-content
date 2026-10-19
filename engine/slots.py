"""IST slot maths and the publish calendar (spec §1, §3 schedules). IST = UTC+5:30, no daylight saving."""
from datetime import date, datetime, timedelta, timezone

from . import config

IST = timezone(timedelta(hours=5, minutes=30), name="IST")


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
        elif kind == "long" and d.weekday() == ch.long_day:
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
