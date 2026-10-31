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


YOUTUBE_URLS = {"sglearning": "https://www.youtube.com/@sanjeev_gulia?sub_confirmation=1",       # opens the subscribe prompt (founder, 22 Oct 2026)
                "arthvan": "https://www.youtube.com/@sgmythworld?sub_confirmation=1"}


CHANNELS = {
    "sglearning": Channel(
        key="sglearning", youtube_env_token="YT_SGLEARNING_REFRESH_TOKEN", display_name="Learning with SG",
        niche="Paise ki khabar, seedhi baat", short_days=frozenset({MON, TUE, WED, THU, FRI, SAT, SUN}), long_days=frozenset({WED, SAT}),   # founder's table, 21 Oct 2026
        short_publish_ist="20:00", long_publish_ist="19:00", ig_slot_ist="18:30", hashtags_key="sglearning",   # 18:30 India from 30 Oct 2026: room for the same-day news Short
        youtube_category="22"),
    "arthvan": Channel(
        key="arthvan", youtube_env_token="YT_ARTHVAN_REFRESH_TOKEN", display_name="SG-MYTH-WORLD",
        niche="Sabut ke saath", short_days=frozenset({MON, TUE, WED, THU, FRI, SAT, SUN}), long_days=frozenset({THU, SUN}),   # founder's table, 21 Oct 2026: daily Shorts
        short_publish_ist="20:00", long_publish_ist="19:00", ig_slot_ist="21:30", hashtags_key="arthvan",
        youtube_category="27"),
}

BUDGETS = {"voice_requests_per_day": 80, "image_inr_per_day": 900, "claude_usd_per_day": 10.0,     # fill-the-stock rate (22 Oct 2026); back to 450 / 6 once 7 days + 4 longs are in hand
           "image_inr_per_month": 8000, "claude_usd_per_month": 75.0}      # raised 29 Oct 2026 for 3-4 Learning with SG Reels a day (founder, "A")      # hard monthly ceilings (founder, 22 Oct 2026): production stops, never the card   # raised 22 Oct 2026 to build the 7-day / 4-long buffer; a steady day is ≈ ₹160 + $1   # ceilings, not targets: a normal day is 2 Shorts + 1 long ≈ ₹190 of pictures (21 Oct 2026)

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


def today_pacific(now: datetime | None = None) -> date:
    """Gemini API daily quotas (the 100 TTS requests) reset at midnight US Pacific, so the voice counter is keyed by that day."""
    from zoneinfo import ZoneInfo
    now = now or datetime.now(timezone.utc)
    return now.astimezone(ZoneInfo("America/Los_Angeles")).date()


def today_ist(now: datetime | None = None) -> date:
    """The founder's calendar day: every daily meter and digest keys on IST, not the machine's clock."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(IST).date()


STORY_FORMAT = {("sglearning", "short"), ("arthvan", "short"), ("sglearning", "long"), ("arthvan", "long")}   # illustrated stories everywhere (founder, 20 Oct 2026)


def is_story(channel: str, kind: str) -> bool:
    return (channel, kind) in STORY_FORMAT


STORY_WORDS = (150, 260)                      # 60-105 s at ~2.5 words/s; the upper limit is soft (founder, 24 Oct 2026: 15 drafts were rewritten for being 2-5 words over 230)
STORY_WORDS_BY_CHANNEL = {"sglearning": (85, 125)}     # money Shorts 35-45 s (founder, 30 Oct 2026, "C": a one-week test against the 60-74 s ones)


NEWS_STORY_WORDS = (115, 155)                 # a breaking-news or extra Reel explains why, impact and remedies: 50-60 s (founder, 29 Oct 2026)
ROUNDUP_WORDS = (125, 170)                    # the Top 10: twelve one-line scenes (31 Oct 2026: a good draft of 156 words was turned down)


def story_words(channel: str, topic: dict | None = None) -> tuple:
    t = {**((topic or {}).get("preset") or {}), **(topic or {})}
    if channel == "sglearning" and "TOP 10 ROUNDUP" in str(t.get("summary", "")):
        return ROUNDUP_WORDS
    if channel == "sglearning" and topic and (t.get("news") or t.get("extra")):
        return NEWS_STORY_WORDS
    return STORY_WORDS_BY_CHANNEL.get(channel, STORY_WORDS)
STORY_MAX_S = 178.0                           # YouTube Shorts allow up to 3 minutes; the writer aims for 60-90 s but nothing is ever cut or sped up (founder, 22 Oct 2026)

ENABLED_KINDS = {"short", "long"}             # longs twice a week per channel (founder, 20 Oct 2026)

VOICE_CREDIT: dict = {}     # no voice credit: the narration is the designed storyteller voices, not the founder's (founder, 29 Oct 2026: "no change")

LINKEDIN_VIDEOS = False                       # founder, 22 Oct 2026: LinkedIn gets picture posts only; no Short or Reel video goes there from this repo
UNLISTED_KINDS = set()                        # founder 21 Oct 2026: longs go public on schedule like Shorts (`python -m engine.youtube --go-public` still releases any unlisted ones)

INSTAGRAM_CAROUSEL = False                    # founder, 31 Oct 2026: "do not add 7 slides on instagram, only videos": Reel + Story only
