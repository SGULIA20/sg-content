"""Comment APP, get the link by DM (founder, 23 Oct 2026). Every hour: new comments on the last week's Instagram posts that say APP
(or link) get one private reply with the right app's Play link: ScoreMyBiz under Learning with SG and ScoreMyBiz posts, Waypoint under
SG-MYTH-WORLD and Waypoint posts. Instagram allows one private reply per comment, within 7 days; each comment is answered once
(logs/comment-dm.json). Needs the instagram_business_manage_messages permission on the Instagram token; without it the founder is
told once a day on Telegram and nothing else happens.

python -m engine.commentdm
"""
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

from . import instagram, pieces, secrets, telegram
from .config import ROOT

STATE = ROOT / "logs" / "comment-dm.json"
WINDOW = timedelta(days=7)
MAX_PER_RUN = 30
ASKS = re.compile(r"(?<![\w])(app|apps|link|ऐप|लिंक)(?![\w])", re.IGNORECASE)
PLAY = {"scoremybiz": "https://play.google.com/store/apps/details?id=com.scoremybiz.app",
        "waypoint": "https://play.google.com/store/apps/details?id=com.arthvananalytics.waypoint"}
CHANNEL_APP = {"sglearning": "scoremybiz", "arthvan": "waypoint"}       # the same pairing as the app posts (arthvan-media, 22 Oct 2026)
MESSAGE = {"scoremybiz": "Namaste! 🙏 ScoreMyBiz: dukaan ka hisaab aur business score, 30 din free. Link: {url}",
           "waypoint": "Namaste! 🙏 Waypoint app ka link: {url}"}


def play_link(app: str) -> str:
    ref = quote("utm_source=instagram&utm_medium=dm&utm_campaign=comment_app", safe="")
    return f"{PLAY[app]}&referrer={ref}"                  # the referrer shows in Play Console's acquisition report


def message(apps: list) -> str:
    return "\n\n".join(MESSAGE[a].format(url=play_link(a)) for a in apps)


def apps_for(media: dict, channel_of: dict) -> list:
    """Which app a post is about: our own Reels by channel, app posts by their caption, anything else gets both links."""
    ch = channel_of.get(media["id"])
    if ch in CHANNEL_APP:
        return [CHANNEL_APP[ch]]
    cap = (media.get("caption") or "").lower()
    named = [a for a in ("scoremybiz", "waypoint") if a in cap]
    return named or ["scoremybiz", "waypoint"]


def _when(ts: str) -> datetime:
    return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S%z")


def load_state(path: Path = STATE) -> dict:
    try:
        return json.loads(Path(path).read_text())
    except (FileNotFoundError, ValueError):
        return {"sent": {}}


def run(env=None, now: datetime | None = None, call=instagram.call, notify=telegram.send, root: Path = ROOT, state_path: Path = STATE) -> dict:
    now = now or datetime.now(timezone.utc)
    token, ig_id = secrets.get("IG_ACCESS_TOKEN", env), secrets.get("IG_USER_ID", env)
    state = load_state(state_path)
    sent = state.setdefault("sent", {})
    channel_of = {p.ids["ig_reel_id"]: p.channel for p in pieces.list_all(root) if p.ids.get("ig_reel_id")}
    done, errors = [], []
    media = call("GET", f"/{ig_id}/media", token, {"fields": "id,caption,timestamp", "limit": "30"}).get("data", [])
    for m in media:
        if now - _when(m["timestamp"]) > WINDOW:
            continue
        comments = call("GET", f"/{m['id']}/comments", token, {"fields": "id,text,timestamp,from", "limit": "50"}).get("data", [])
        for c in comments:
            if len(done) >= MAX_PER_RUN:
                break
            if c["id"] in sent or (c.get("from") or {}).get("id") == ig_id or not ASKS.search(c.get("text") or ""):
                continue
            if now - _when(c["timestamp"]) > WINDOW:
                continue
            try:
                call("POST", f"/{ig_id}/messages", token, {"recipient": json.dumps({"comment_id": c["id"]}),
                                                            "message": json.dumps({"text": message(apps_for(m, channel_of))})})
                sent[c["id"]] = now.isoformat(timespec="seconds")
                done.append(c["id"])
            except instagram.InstagramError as e:
                errors.append(str(e)[:200])
                break                                     # a permission problem fails every send: stop and report once
    cutoff = (now - timedelta(days=14)).isoformat()
    state["sent"] = {k: v for k, v in sent.items() if v >= cutoff}
    day = now.date().isoformat()
    if done:
        notify(f"💬 Sent the app link by DM to {len(done)} Instagram comment(s) that asked for it.")
    if errors and state.get("error_day") != day:
        state["error_day"] = day
        notify("💬 Comment-to-DM could not send: " + errors[0] + "\nIf it says permission, the Instagram token needs "
               "instagram_business_manage_messages (Meta app → Instagram → permissions), then a new token.")
    Path(state_path).parent.mkdir(parents=True, exist_ok=True)
    Path(state_path).write_text(json.dumps(state, indent=1))
    return {"sent": len(done), "errors": errors}


NEEDED = ("instagram_business_manage_messages", "instagram_business_manage_comments")


def check(env=None, call=instagram.call, notify=telegram.send) -> int:
    """Read-only (founder, 2 Nov 2026): does the Instagram token carry the permissions the comment-to-DM gift needs? Asks Instagram
    which scopes the token has, and how many comments in the last week asked for the app, so we know whether 0 DMs sent means
    "no permission" or "nobody asked". Sends nothing."""
    token, ig_id = secrets.get("IG_ACCESS_TOKEN", env), secrets.get("IG_USER_ID", env)
    try:
        me = call("GET", "/me", token, {"fields": "id,username"})
    except instagram.InstagramError as e:
        notify(f"💬 DM check: the Instagram token does not work at all: {str(e)[:160]}")
        return 1
    scopes = []
    try:
        dbg = call("GET", "/debug_token", token, {"input_token": token})
        scopes = (dbg.get("data") or {}).get("scopes") or []
    except instagram.InstagramError as e:
        print(f"debug_token not available: {str(e)[:160]}", flush=True)
    now = datetime.now(timezone.utc)
    asked = total = 0
    media = call("GET", f"/{ig_id}/media", token, {"fields": "id,timestamp", "limit": "30"}).get("data", [])
    for m in media:
        if now - _when(m["timestamp"]) > WINDOW:
            continue
        for c in call("GET", f"/{m['id']}/comments", token, {"fields": "id,text,from", "limit": "50"}).get("data", []):
            if (c.get("from") or {}).get("id") == ig_id:
                continue
            total += 1
            asked += bool(ASKS.search(c.get("text") or ""))
    missing = [s for s in NEEDED if scopes and s not in scopes]
    verdict = ("✅ DM permission present" if scopes and not missing else
               f"❌ missing: {', '.join(missing)}" if missing else "❓ Instagram did not list the token's permissions (debug_token unavailable); "
               "the only sure test is a real send")
    text = (f"💬 DM check for @{me.get('username', '?')}: {verdict}. Last 7 days: {total} comments from others on our posts, {asked} asked for the app. "
            f"Token scopes: {', '.join(scopes) or 'not listed'}.")
    print(text, flush=True)
    notify(text)
    return 0 if not missing else 1


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if "--check" in argv:
        try:
            return check()
        except Exception as e:
            print("DM check failed:", secrets.scrub(str(e))[:300], flush=True)
            telegram.send("💬 DM check failed: " + secrets.scrub(str(e))[:200])
            return 1
    try:
        print(run())
    except Exception as e:                                  # one bad hour never needs attention; the next run tries again
        print("comment-dm failed:", secrets.scrub(str(e))[:200])
    return 0


if __name__ == "__main__":
    sys.exit(main())
