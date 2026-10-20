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
    long_days: frozenset
    short_publish_ist: str
    long_publish_ist: str
    ig_slot_ist: str
    hashtags_key: str
    youtube_category: str


CHANNELS = {
    "sglearning": Channel(
        key="sglearning", youtube_env_token="YT_SGLEARNING_REFRESH_TOKEN", display_name="Learning with SG",
        niche="Paise ki khabar, seedhi baat", short_days=frozenset({MON, TUE, WED, THU, FRI, SAT, SUN}), long_days=frozenset({WED, SUN}),
        short_publish_ist="20:00", long_publish_ist="19:00", ig_slot_ist="13:00", hashtags_key="sglearning",
        youtube_category="22"),
    "arthvan": Channel(
        key="arthvan", youtube_env_token="YT_ARTHVAN_REFRESH_TOKEN", display_name="SG-MYTH-WORLD",
        niche="Sabut ke saath", short_days=frozenset({MON, WED, FRI}), long_days=frozenset({TUE, SAT}),
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


STORY_FORMAT = {("sglearning", "short"), ("arthvan", "short"), ("sglearning", "long"), ("arthvan", "long")}   # illustrated stories everywhere (founder, 20 Oct 2026)


def is_story(channel: str, kind: str) -> bool:
    return (channel, kind) in STORY_FORMAT


STORY_WORDS = (150, 230)                      # a 60-90 s story at the clone's ~2.5 words/s
STORY_MAX_S = 95.0                            # YouTube Shorts and Reels allow up to 3 minutes; stories stop at about 90 s

ENABLED_KINDS = {"short", "long"}             # longs twice a week per channel (founder, 20 Oct 2026)
