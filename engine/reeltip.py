"""Daily tip: which Reel deserves one of the founder's few Meta Verified Reel links (founder, 24 Oct 2026). Instagram's API cannot add
a link to a Reel and Meta Verified allows only a handful a month, so each morning the strongest Reel of the last three days that is
clearly taking off goes to Telegram with the app and the exact link to paste. At most MAX_PER_MONTH tips a month, each Reel once.

python -m engine.reeltip
"""
import json
import statistics
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

from . import commentdm, instagram, pieces, secrets, telegram, whatworks
from .config import ROOT

STATE = ROOT / "logs" / "reel-tip.json"
MAX_PER_MONTH = 4                   # Meta Verified reportedly allows 2-6 linked Reels a month, depending on the plan
FRESH = timedelta(days=3)           # a link helps while the Reel is still being shown
LOOKBACK = timedelta(days=14)
MIN_VIEWS = 800                     # never spend a link on a Reel few people see
LIFT = 1.5                          # and only on one doing clearly better than the usual Reel
APP_NAME = {"scoremybiz": "ScoreMyBiz", "waypoint": "Waypoint"}


def reel_link(app: str) -> str:
    ref = quote("utm_source=instagram&utm_medium=reel_link&utm_campaign=meta_verified", safe="")
    return f"{commentdm.PLAY[app]}&referrer={ref}"


def views_of(numbers: dict) -> int:
    return int(numbers.get("views") or numbers.get("reach") or 0)


def pick(reels: list, now: datetime, tipped: set) -> dict | None:
    """reels: [{id, timestamp, views, ...}] from the last two weeks. The strongest fresh one, if it stands out."""
    if not reels:
        return None
    usual = statistics.median([r["views"] for r in reels])
    fresh = [r for r in reels if now - r["when"] <= FRESH and r["id"] not in tipped]
    best = max(fresh, key=lambda r: r["views"], default=None)
    if not best or best["views"] < MIN_VIEWS or best["views"] < LIFT * usual:
        return None
    return best


def run(env=None, now: datetime | None = None, call=instagram.call, numbers=whatworks.instagram_numbers, notify=telegram.send,
        root: Path = ROOT, state_path: Path = STATE) -> str:
    now = now or datetime.now(timezone.utc)
    try:
        state = json.loads(Path(state_path).read_text())
    except (FileNotFoundError, ValueError):
        state = {}
    month = now.strftime("%Y-%m")
    if state.get("month") != month:
        state = {"month": month, "tipped": state.get("tipped", [])[-20:], "count": 0}
    if state["count"] >= MAX_PER_MONTH:
        return "monthly tips used"
    token, ig_id = secrets.get("IG_ACCESS_TOKEN", env), secrets.get("IG_USER_ID", env)
    channel_of = {p.ids["ig_reel_id"]: p.channel for p in pieces.list_all(root) if p.ids.get("ig_reel_id")}
    media = call("GET", f"/{ig_id}/media", token, {"fields": "id,caption,media_product_type,permalink,timestamp", "limit": "40"}).get("data", [])
    reels = []
    for m in media:
        when = commentdm._when(m["timestamp"])
        if m.get("media_product_type") != "REELS" or now - when > LOOKBACK:
            continue
        reels.append({**m, "when": when, "views": views_of(numbers(m["id"], token))})
    best = pick(reels, now, set(state["tipped"]))
    if not best:
        Path(state_path).parent.mkdir(parents=True, exist_ok=True)
        Path(state_path).write_text(json.dumps(state, indent=1))
        return "no Reel stands out today"
    app = commentdm.apps_for(best, channel_of)[0]
    usual = int(statistics.median([r["views"] for r in reels]))
    notify(f"🔗 Add a link to this Reel today (Meta Verified, tip {state['count'] + 1} of {MAX_PER_MONTH} this month)\n"
           f"Reel: {best.get('permalink', best['id'])}\n"
           f"It has {best['views']:,} views; your usual Reel has {usual:,}.\n"
           f"Link to add ({APP_NAME[app]}):\n{reel_link(app)}\n"
           f"In the Instagram app, edit this Reel and add the link (a Meta Verified feature).")
    state["tipped"].append(best["id"])
    state["count"] += 1
    Path(state_path).parent.mkdir(parents=True, exist_ok=True)
    Path(state_path).write_text(json.dumps(state, indent=1))
    return f"tipped {best['id']}"


def main(argv=None) -> int:
    try:
        print(run())
    except Exception as e:
        print("reel tip failed:", secrets.scrub(str(e))[:200])
    return 0


if __name__ == "__main__":
    sys.exit(main())
