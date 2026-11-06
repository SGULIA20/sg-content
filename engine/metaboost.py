"""Gated Instagram Reel boosting (founder, 6 Nov 2026: "start with the gated plan at Rs 350 a day").

Once a day: pick the single best Reel that passed the organic gate (enough views, low skip rate, long watch, carries the founder's
intro, 12-72 hours old, not boosted before) and turn it into a Meta ad for one day at the daily budget, across both channels in total.
Caps keep it from running away: Rs 350 a day, a rolling 7-day cap and a month cap (content/meta-boost.json), all counted from what
Meta says was really spent, and an ad account whose currency is not the configured one is never touched.

mode "probe" (the first runs): every object is created PAUSED, so nothing is spent and the founder can look at it in Ads Manager;
mode "live": the ad is switched on. It never raises a budget and pauses everything when the founder has paused the system.
The Marketing API request shapes below follow Meta's docs but have not been exercised against a real ad account yet: that is
what probe mode is for. Needs META_ACCESS_TOKEN, META_AD_ACCOUNT_ID, META_PAGE_ID and IG_USER_ID.

python -m engine.metaboost [--report] [--pause]
"""
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import pieces, secrets, telegram
from .config import CONTENT_DIR, LOGS_DIR, ROOT

API = "https://graph.facebook.com/v25.0"
STATE = LOGS_DIR / "meta-boost.json"


class BoostError(Exception):
    pass


def settings(content: Path = CONTENT_DIR) -> dict:
    try:
        return json.loads((Path(content) / "meta-boost.json").read_text())
    except (OSError, ValueError):
        return {}


def call(method: str, path: str, token: str, params: dict | None = None) -> dict:
    url = path if path.startswith("http") else API + path
    data = None
    if method == "GET" and params:
        url += "?" + urllib.parse.urlencode(params)
    elif params:
        data = urllib.parse.urlencode({k: json.dumps(v) if isinstance(v, (dict, list)) else v for k, v in params.items()}).encode()
    req = urllib.request.Request(url, data=data, method=method, headers={"Authorization": "Bearer " + token})
    try:
        with urllib.request.urlopen(req, timeout=60, context=secrets.ssl_context()) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise BoostError(secrets.scrub(f"HTTP {e.code}: {e.read().decode(errors='replace')[:500]}")) from None
    except Exception as e:
        raise BoostError(secrets.scrub(f"{type(e).__name__}: {e}")) from None


def _state(root: Path) -> dict:
    try:
        return json.loads((Path(root) / "logs" / "meta-boost.json").read_text())
    except (OSError, ValueError):
        return {"boosts": []}


def _save(root: Path, state: dict) -> None:
    path = Path(root) / "logs" / "meta-boost.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=1, ensure_ascii=False))


def _metrics(root: Path) -> dict:
    """Instagram numbers per piece id from the reel diagnosis (refreshed daily) and the weekly report; the newer file wins."""
    out = {}
    for name in ("whatworks.json", "diagnosis.json"):
        try:
            data = json.loads((Path(root) / "logs" / name).read_text())
        except (OSError, ValueError):
            continue
        rows = data.get("rows") or (data.get("week") or []) + (data.get("month") or [])
        for r in rows:
            out[r["id"]] = r
    return out


def _posted_at(piece) -> datetime | None:
    """When the Reel went out: the channel's Instagram slot on its day (the piece record keeps no posting time)."""
    from . import config, slots
    ch = config.CHANNELS.get(piece.channel)
    if ch is None or piece.publish_day is None:
        return None
    return slots.utc_for(piece.publish_day, ch.ig_slot_ist)


def candidates(root: Path, cfg: dict, now: datetime) -> list:
    """Reels that passed the gate, best first: (score, piece, metrics). Watch time counts most, skip rate next."""
    g = cfg.get("gate", {})
    m = _metrics(root)
    boosted = {b["piece"] for b in _state(root)["boosts"]}
    out = []
    for p in pieces.list_all(root):
        if p.kind != "short" or p.status != "posted" or not p.ids.get("ig_reel_id") or p.id in boosted or p.ids.get("ig_reposted_from"):
            continue
        if g.get("intro_required", True) and not p.ids.get("intro"):
            continue
        at = _posted_at(p)
        if at is None:
            continue
        age = (now - at).total_seconds() / 3600
        if not (g.get("min_age_hours", 12) <= age <= g.get("max_age_hours", 72)):
            continue
        r = m.get(p.id) or {}
        views, skip, watch = r.get("ig_views") or 0, r.get("ig_skip_rate"), r.get("ig_watch_s") or 0
        if views < g.get("min_views", 300) or skip is None or skip > g.get("max_skip_rate", 40) or watch < g.get("min_watch_s", 12):
            continue
        out.append((watch * (100 - skip) / 100, p, r))
    return sorted(out, key=lambda t: -t[0])


def spent(state: dict, since: date) -> float:
    """What the boosts really cost since `since`: Meta's own figure once known, else the planned budget."""
    return sum(b.get("spend") if b.get("spend") is not None else b.get("planned", 0)
               for b in state["boosts"] if date.fromisoformat(b["day"]) >= since and b.get("mode") == "live")


def room(cfg: dict, state: dict, today: date) -> str | None:
    """None when another boost fits under the caps, else why not."""
    if any(b["day"] == today.isoformat() for b in state["boosts"]):
        return "today's boost is already made"
    if spent(state, today - timedelta(days=6)) + cfg["daily_budget"] * cfg.get("days", 1) > cfg["week_cap"]:
        return f"the 7-day cap of {cfg['week_cap']} would be passed"
    if spent(state, today.replace(day=1)) + cfg["daily_budget"] * cfg.get("days", 1) > cfg["month_cap"]:
        return f"this month's cap of {cfg['month_cap']} would be passed"
    return None


def create_boost(piece, cfg: dict, env=None, now: datetime | None = None, call=call) -> dict:
    """Campaign, ad set, creative and ad, all PAUSED; returns their ids. Money is in minor units (rupees x 100)."""
    token, acct, page, ig = (secrets.get(k, env) for k in ("META_ACCESS_TOKEN", "META_AD_ACCOUNT_ID", "META_PAGE_ID", "IG_USER_ID"))
    acct = acct if str(acct).startswith("act_") else f"act_{acct}"
    now = now or datetime.now(timezone.utc)
    info = call("GET", f"/{acct}", token, {"fields": "currency,account_status"})
    if info.get("currency") != cfg["currency"]:
        raise BoostError(f"the ad account is in {info.get('currency')}, not {cfg['currency']}: nothing created")
    name = f"boost {piece.id}"
    camp = call("POST", f"/{acct}/campaigns", token, {"name": name, "objective": cfg["objective"], "status": "PAUSED",
                                                      "special_ad_categories": []})["id"]
    adset = call("POST", f"/{acct}/adsets", token, {
        "name": name, "campaign_id": camp, "status": "PAUSED", "billing_event": "IMPRESSIONS", "optimization_goal": cfg["optimization_goal"],
        "destination_type": cfg["destination_type"], "daily_budget": int(cfg["daily_budget"] * 100),
        "start_time": now.isoformat(timespec="seconds"), "end_time": (now + timedelta(days=cfg.get("days", 1))).isoformat(timespec="seconds"),
        "bid_strategy": "LOWEST_COST_WITHOUT_CAP",
        "targeting": {"geo_locations": {"countries": cfg["countries"]}, "age_min": cfg["age_min"], "age_max": cfg["age_max"],
                      "publisher_platforms": ["instagram"], "instagram_positions": ["reels"]}})["id"]
    creative = call("POST", f"/{acct}/adcreatives", token, {"name": name, "object_id": page, "instagram_user_id": ig,
                                                           "source_instagram_media_id": piece.ids["ig_reel_id"]})["id"]
    ad = call("POST", f"/{acct}/ads", token, {"name": name, "adset_id": adset, "creative": {"creative_id": creative}, "status": "PAUSED"})["id"]
    return {"campaign": camp, "adset": adset, "creative": creative, "ad": ad}


def activate(ids: dict, env=None, call=call) -> None:
    token = secrets.get("META_ACCESS_TOKEN", env)
    for key in ("campaign", "adset", "ad"):
        call("POST", f"/{ids[key]}", token, {"status": "ACTIVE"})


def pause_ids(ids: dict, env=None, call=call) -> None:
    token = secrets.get("META_ACCESS_TOKEN", env)
    for key in ("ad", "adset", "campaign"):
        call("POST", f"/{ids[key]}", token, {"status": "PAUSED"})


def refresh_spend(state: dict, env=None, call=call) -> None:
    """Meta's own spend for every live boost, so the caps count real money."""
    token = secrets.get("META_ACCESS_TOKEN", env)
    for b in state["boosts"]:
        if b.get("mode") == "live" and b.get("ids"):
            try:
                rows = call("GET", f"/{b['ids']['ad']}/insights", token, {"fields": "spend,reach,actions", "date_preset": "maximum"}).get("data") or []
                if rows:
                    b["spend"] = float(rows[0].get("spend", 0))
                    b["reach"] = int(rows[0].get("reach", 0) or 0)
            except BoostError:
                pass


def run(root: Path = ROOT, now: datetime | None = None, env=None, notify=telegram.send, cfg: dict | None = None, call=call) -> str:
    cfg = cfg if cfg is not None else settings()
    now = now or datetime.now(timezone.utc)
    if not cfg.get("enabled"):
        return "off"
    state = _state(root)
    if telegram.paused(root):
        for b in state["boosts"]:
            if b.get("mode") == "live" and b.get("ids") and not b.get("paused"):
                try:
                    pause_ids(b["ids"], env, call); b["paused"] = True
                except (BoostError, secrets.MissingSecret):
                    pass
        _save(root, state)
        return "paused by the founder"
    try:
        for k in ("META_ACCESS_TOKEN", "META_AD_ACCOUNT_ID", "META_PAGE_ID", "IG_USER_ID"):
            secrets.get(k, env)
    except secrets.MissingSecret as e:
        return f"skipped: {e} is not set yet"
    refresh_spend(state, env, call)
    why = room(cfg, state, now.date())
    if why:
        _save(root, state)
        return f"no boost: {why}"
    found = candidates(root, cfg, now)
    if not found:
        _save(root, state)
        return "no boost: no Reel passed the gate today"
    score, piece, r = found[0]
    try:
        ids = create_boost(piece, cfg, env, now, call)
        if cfg.get("mode") == "live":
            activate(ids, env, call)
    except (BoostError, secrets.MissingSecret) as e:
        _save(root, state)
        notify(f"⚠️ Boost of {piece.id} failed: {str(e)[:300]}")
        return f"failed: {e}"
    mode = "live" if cfg.get("mode") == "live" else "probe"
    state["boosts"].append({"day": now.date().isoformat(), "piece": piece.id, "mode": mode, "ids": ids,
                            "planned": cfg["daily_budget"] * cfg.get("days", 1), "views": r.get("ig_views"), "skip": r.get("ig_skip_rate"), "watch_s": r.get("ig_watch_s")})
    _save(root, state)
    verb = "is running" if mode == "live" else "was created PAUSED (probe mode, nothing spent): review it in Ads Manager"
    notify(f"📣 Boost {verb}: {piece.id} ({r.get('ig_views')} views, {r.get('ig_skip_rate')}% skip, {r.get('ig_watch_s')} s watched). "
           f"₹{cfg['daily_budget']} for {cfg.get('days', 1)} day.")
    return f"{mode}: {piece.id}"


def report(root: Path = ROOT, today: date | None = None, cfg: dict | None = None) -> str:
    cfg = cfg if cfg is not None else settings()
    today = today or date.today()
    state = _state(root)
    live = [b for b in state["boosts"] if b.get("mode") == "live"]
    return (f"📣 Boosts: {len(state['boosts'])} made ({len(live)} live). Spent the last 7 days ₹{spent(state, today - timedelta(days=6)):.0f} of ₹{cfg.get('week_cap')}, "
            f"this month ₹{spent(state, today.replace(day=1)):.0f} of ₹{cfg.get('month_cap')}.")


def main(argv=None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if "--report" in args:
        print(report()); return 0
    if "--pause" in args:
        state = _state(ROOT)
        for b in state["boosts"]:
            if b.get("mode") == "live" and b.get("ids") and not b.get("paused"):
                pause_ids(b["ids"]); b["paused"] = True
        _save(ROOT, state); print("paused every live boost"); return 0
    print(run())
    return 0


if __name__ == "__main__":
    sys.exit(main())
