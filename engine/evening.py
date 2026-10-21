"""The evening scorecard (founder, 21 Oct 2026): his planning table with every "Yes" replaced by what actually happened today,
Posted or NOT POSTED, sent to Telegram and saved as logs/evening-latest.txt so the app poster's bot can relay the same text.

Rows and cells follow the founder's table exactly:
  ScoreMyBiz / Waypoint (alternate days)  Reel: YouTube (own channel) + Instagram   Post: Instagram + Threads + LinkedIn   Story: Instagram
  SG-LEARNING  long (Wed, Sat): YouTube      Short (daily): YouTube + Instagram + Threads + LinkedIn
  SG-MYTH      long (Thu, Sun): YouTube      Short (daily): YouTube + Instagram + Threads + LinkedIn
  LinkedIn daily post
Sources: this repo's piece records, and the app poster's public log (logs/posts.jsonl in SGULIA20/arthvan-media)."""
import json
import sys
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import pieces, secrets, slots, telegram
from .config import CHANNELS, ROOT, today_ist

APP_LOG_URL = "https://raw.githubusercontent.com/SGULIA20/arthvan-media/main/logs/posts.jsonl"
APP_EPOCH = date(2026, 10, 11)                               # Waypoint day; the apps alternate from here (arthvan-media rule)
APP_YT = {"scoremybiz": "youtube:sglearning", "waypoint": "youtube:arthvan"}
APP_NAMES = {"scoremybiz": "ScoreMyBiz", "waypoint": "Waypoint"}
OK, NO, NA = "✅ Posted", "🔴 NOT POSTED", "—"
LATEST = ROOT / "logs" / "evening-latest.txt"
STATE = ROOT / "logs" / "evening.json"


def app_for(day: date) -> str:
    return "waypoint" if (day - APP_EPOCH).days % 2 == 0 else "scoremybiz"


def fetch_app_log(url: str = APP_LOG_URL) -> list:
    try:
        with urllib.request.urlopen(url, timeout=30, context=secrets.ssl_context()) as r:
            text = r.read().decode("utf-8", "replace")
    except Exception as e:                                                        # the card still goes out; the app rows say the log was unreadable
        print(f"app log not read: {secrets.scrub(str(e))[:120]}", flush=True)
        return []
    out = []
    for line in text.splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def _app_rows(day: date, log: list) -> list:
    """Three rows for the app whose day it is: Reel, Post, Story."""
    app = app_for(day)
    today = [e for e in log if e.get("date") == day.isoformat() and e.get("status") == "published"]
    insta = {}
    for e in today:
        if e.get("app") == app and not e.get("channel") and isinstance(e.get("ids"), dict):
            insta.update(e["ids"])
    chan = {e["channel"] for e in today if e.get("channel")}
    name = APP_NAMES[app]
    cell = lambda ok: OK if ok else NO
    return [(f"{name} Reel", {"YouTube": cell(APP_YT[app] in chan), "Instagram": cell(bool(insta.get("reel")))}),
            (f"{name} Post", {"Instagram": cell(bool(insta.get("post"))), "Threads": cell("threads" in chan), "LinkedIn": cell("linkedin" in chan)}),
            (f"{name} Story", {"Instagram": cell(bool(insta.get("story")))})]


def _yt_cell(piece, now: datetime) -> str:
    if not piece or not piece.ids.get("yt_id"):
        return NO
    due = slots.publish_at(piece.channel, piece.kind, piece.publish_day)
    return OK if now >= due or piece.ids.get("unlisted") else "⏳ scheduled"


def _channel_rows(day: date, now: datetime, root: Path) -> list:
    rows = []
    for key, label in (("sglearning", "SG-LEARNING"), ("arthvan", "SG-MYTH")):
        ch = CHANNELS[key]
        if day.weekday() in ch.long_days:
            p = pieces.load(slots.piece_id(day, key, "long"), root)
            rows.append((f"{label} long video", {"YouTube": _yt_cell(p, now)}))
        if day.weekday() in ch.short_days:
            p = pieces.load(slots.piece_id(day, key, "short"), root)
            ids = p.ids if p else {}
            story = ids.get("ig_story_id") or ""
            if ids.get("ig_reel_id") and story.startswith("skipped"):
                ig = "✅ Reel (no Story: over 60 s)"
            else:
                ig = OK if ids.get("ig_reel_id") and story else ("🔴 Reel only" if ids.get("ig_reel_id") else ("🔴 Story only" if story else NO))
            rows.append((f"{label} Short", {"YouTube": _yt_cell(p, now), "Instagram": ig,
                                            "Threads": OK if ids.get("threads_id") else NO, "LinkedIn": OK if ids.get("linkedin_id") else NO}))
    return rows


def _personal_row(day: date, log: list) -> tuple:
    done = any(e.get("date") == day.isoformat() and e.get("channel") == "linkedin_personal" and e.get("status") == "published" for e in log)
    return ("LinkedIn daily post", {"LinkedIn": OK if done else NO})


def build(day: date | None = None, now: datetime | None = None, root: Path = ROOT, log: list | None = None) -> str:
    day = day or today_ist()
    now = now or datetime.now(timezone.utc)
    log = fetch_app_log() if log is None else log
    rows = _app_rows(day, log) + _channel_rows(day, now, root) + [_personal_row(day, log)]
    missing = sum(1 for _r, cells in rows for v in cells.values() if v.startswith("🔴"))
    head = f"📋 Evening status {day.strftime('%a %d %b %Y')}" + (" — all posted ✅" if missing == 0 else f" — {missing} NOT POSTED 🔴")
    lines = [head, ""]
    for name, cells in rows:
        lines.append(name)
        lines += [f"   {k}: {v}" for k, v in cells.items()]
    return "\n".join(lines)


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    day = today_ist()
    text = build(day)
    print(text)
    if "--send" not in argv:
        return 0
    LATEST.parent.mkdir(parents=True, exist_ok=True)
    LATEST.write_text(text, encoding="utf-8")
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    if state.get("sent") == day.isoformat():
        print("already sent today")
        return 0
    if telegram.send(text):
        STATE.write_text(json.dumps({"sent": day.isoformat()}))
        return 0
    print("telegram send failed")
    return 1


if __name__ == "__main__":
    sys.exit(main())
