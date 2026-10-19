"""Channels, slots, budgets and paths for the SG Content pipeline (spec §1, §3, §6.10)."""
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

MON, TUE, WED, THU, FRI, SAT, SUN = range(7)


@dataclass(frozen=True)
class Channel:
    key: str
    youtube_env_token: str
    display_name: str
    niche: str
    short_days: frozenset
    long_day: int
    short_publish_ist: str
    long_publish_ist: str
    ig_slot_ist: str
    hashtags_key: str
    youtube_category: str


CHANNELS = {
    "sglearning": Channel(
        key="sglearning", youtube_env_token="YT_SGLEARNING_REFRESH_TOKEN", display_name="Learning with SG",
        niche="Paise ki khabar, seedhi baat", short_days=frozenset({MON, TUE, WED, THU, FRI, SAT, SUN}), long_day=SUN,
        short_publish_ist="20:00", long_publish_ist="19:00", ig_slot_ist="13:00", hashtags_key="sglearning",
        youtube_category="22"),
    "arthvan": Channel(
        key="arthvan", youtube_env_token="YT_ARTHVAN_REFRESH_TOKEN", display_name="SG-MYTH-WORLD",
        niche="Sabut ke saath", short_days=frozenset({MON, WED, FRI}), long_day=SAT,
        short_publish_ist="20:00", long_publish_ist="19:00", ig_slot_ist="21:30", hashtags_key="arthvan",
        youtube_category="27"),
}

BUDGETS = {"voice_requests_per_day": 80, "image_inr_per_day": 150, "claude_usd_per_day": 1.0}

VIDEO = {"short": (1080, 1920), "long": (1920, 1080), "fps": 30}

APP_JOB_IG_SLOT_IST = "20:07"      # the arthvan-media Reel job posts here; never post within 60 minutes of it
IG_GUARD_MINUTES = 60

PIECES_DIR = ROOT / "pieces"
OUT_DIR = ROOT / "out"
LOGS_DIR = ROOT / "logs"
CACHE_DIR = ROOT / "cache"
CONTENT_DIR = ROOT / "content"
ASSETS_DIR = ROOT / "assets"
TEMPLATES_DIR = ROOT / "templates"


IST = timezone(timedelta(hours=5, minutes=30), name="IST")


def today_ist(now: datetime | None = None) -> date:
    """The founder's calendar day: every daily meter and digest keys on IST, not the machine's clock."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(IST).date()
