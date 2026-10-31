"""YouTube promotion watch, phase 1 (founder, 30 Oct 2026: "start build phase 1" of the Rs 6,000 test, docs/growth-plan.md).

Reads the Google Ads account named in content/ads.json through the Google Ads API (v25; access comes from the YouTube uploads' Google
Cloud project, no developer token since 9 Sep 2026) and YouTube Analytics, then:
  * reports: spend today and since the test began, new subscribers on both channels above the usual pace, cost per subscriber
    (logs/ads.json; the 9 pm card prints it, the Telegram line goes out once a day);
  * guards, only ever pausing: every running campaign is paused when the founder has paused the system (/pause), when this month's
    spend reaches the cap, or when the test has spent at least min_spend and a subscriber costs more than max_cost_per_sub.
It never raises a budget or starts a campaign: scaling stays the founder's call (content/ads.json "scale": false).

python -m engine.ads [--report]
"""
import json
import sys
import urllib.parse
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import secrets, telegram, youtube
from .config import CONTENT_DIR, ROOT

API = "https://googleads.googleapis.com/v25"
ANALYTICS_URL = "https://youtubeanalytics.googleapis.com/v2/reports"
TOKEN_URL = "https://oauth2.googleapis.com/token"
CHANNELS = ("sglearning", "arthvan")


class AdsError(Exception):
    pass


def settings(content: Path = CONTENT_DIR) -> dict:
    try:
        return json.loads((Path(content) / "ads.json").read_text())
    except (OSError, ValueError):
        return {}


def access_token(env=None, post=youtube._post_form) -> str:
    form = {"client_id": secrets.get("YT_CLIENT_ID", env), "client_secret": secrets.get("YT_CLIENT_SECRET", env),
            "refresh_token": secrets.get("ADS_REFRESH_TOKEN", env), "grant_type": "refresh_token"}
    out = post(TOKEN_URL, form)
    if "access_token" not in out:
        raise AdsError(f"Google Ads token refresh failed: {out.get('error_description') or out.get('error')}")
    secrets.remember(out["access_token"])
    return out["access_token"]


def _headers(cfg: dict) -> dict:
    h = {}
    if cfg.get("login_customer_id"):
        h["login-customer-id"] = str(cfg["login_customer_id"]).replace("-", "")
    return h


def search(cid: str, query: str, token: str, cfg: dict, call=youtube.call) -> list:
    status, _h, body = call("POST", f"{API}/customers/{cid}/googleAds:search", token, json_body={"query": query}, headers=_headers(cfg))
    if status != 200:
        raise AdsError(f"Google Ads search {status}: {secrets.scrub(json.dumps(body))[:300]}")
    return body.get("results", [])


def campaigns(cid: str, start: date, end: date, token: str, cfg: dict, call=youtube.call) -> dict:
    """{campaign id: {"name", "status", "cost"}} with cost in the account currency between start and end (inclusive)."""
    q = ("SELECT campaign.id, campaign.name, campaign.status, metrics.cost_micros FROM campaign "
         f"WHERE segments.date BETWEEN '{start.isoformat()}' AND '{end.isoformat()}' AND campaign.status != 'REMOVED'")
    out = {}
    for r in search(cid, q, token, cfg, call):
        c = r.get("campaign", {})
        row = out.setdefault(str(c.get("id")), {"name": c.get("name", ""), "status": c.get("status", ""), "cost": 0.0})
        row["cost"] += int(r.get("metrics", {}).get("costMicros", 0)) / 1_000_000
    return out


def currency(cid: str, token: str, cfg: dict, call=youtube.call) -> str:
    rows = search(cid, "SELECT customer.currency_code FROM customer", token, cfg, call)
    return (rows[0].get("customer", {}) if rows else {}).get("currencyCode", "")


def pause(cid: str, ids: list, token: str, cfg: dict, call=youtube.call) -> None:
    ops = [{"update": {"resourceName": f"customers/{cid}/campaigns/{i}", "status": "PAUSED"}, "updateMask": "status"} for i in ids]
    status, _h, body = call("POST", f"{API}/customers/{cid}/campaigns:mutate", token, json_body={"operations": ops}, headers=_headers(cfg))
    if status != 200:
        raise AdsError(f"Google Ads pause {status}: {secrets.scrub(json.dumps(body))[:300]}")


def subscribers(channel: str, start: date, end: date, env=None, call=youtube.call, token_for=youtube.access_token) -> int:
    q = {"ids": "channel==MINE", "startDate": start.isoformat(), "endDate": end.isoformat(), "metrics": "subscribersGained"}
    status, _h, body = call("GET", ANALYTICS_URL + "?" + urllib.parse.urlencode(q), token_for(channel, env))
    if status != 200:
        raise AdsError(f"analytics {status} for {channel}")
    rows = body.get("rows") or [[0]]
    return int(rows[0][0])


def decide(cfg: dict, spend_test: float, spend_month: float, extra_subs: int, paused_by_founder: bool) -> str:
    """Why every running campaign must be paused now, or "" to leave them alone."""
    if paused_by_founder:
        return "the system is paused (/pause)"
    if cfg.get("monthly_cap_inr") and spend_month >= cfg["monthly_cap_inr"]:
        return f"this month's spend reached the Rs {cfg['monthly_cap_inr']:,} cap"
    rule = cfg.get("pause_rule", {})
    if spend_test >= rule.get("min_spend_inr", 1500) and spend_test / max(extra_subs, 1) > rule.get("max_cost_per_sub_inr", 25):
        return f"a new subscriber costs more than Rs {rule.get('max_cost_per_sub_inr', 25)} after Rs {int(spend_test):,} spent"
    return ""


def run(root: Path = ROOT, now_utc: datetime | None = None, env=None, notify=telegram.send, report: bool = False, cfg: dict | None = None,
        call=youtube.call, token=None, subs=None) -> int:
    now_utc = now_utc or datetime.now(timezone.utc)
    cfg = settings() if cfg is None else cfg
    cid = str(cfg.get("customer_id", "")).replace("-", "")
    if not cid:
        print("ads: no customer_id in content/ads.json yet", flush=True)
        return 0
    today = now_utc.date()
    start = date.fromisoformat(cfg.get("test_start") or today.isoformat())
    tok = token or access_token(env)
    cur = currency(cid, tok, cfg, call)
    if cur != "INR":
        notify(f"📣 Ads watch: the Google Ads account is in {cur or 'an unknown currency'}, not INR; the rupee rules are off until that is fixed.")
        return 1
    rows_test = campaigns(cid, start, today, tok, cfg, call)
    rows_month = campaigns(cid, today.replace(day=1), today, tok, cfg, call)
    rows_today = campaigns(cid, today, today, tok, cfg, call)
    spend_test = sum(r["cost"] for r in rows_test.values())
    spend_month = sum(r["cost"] for r in rows_month.values())
    spend_today = sum(r["cost"] for r in rows_today.values())
    days = (today - start).days + 1
    got = subs or (lambda ch: subscribers(ch, start, today, env, call))
    gained = sum(got(ch) for ch in CHANNELS)
    extra = max(gained - round(cfg.get("baseline_subs_per_day", 0) * days), 0)
    per_sub = spend_test / extra if extra else None
    why = decide(cfg, spend_test, spend_month, extra, telegram.paused(root))
    running = [i for i, r in {**rows_test, **rows_month}.items() if r["status"] == "ENABLED"]
    acted = []
    if why and running:
        pause(cid, running, tok, cfg, call)
        acted = running
        notify(f"⏸ Ads paused ({len(running)} campaign(s)): {why}. Restart them in Google Ads when you decide.")
    state = {"day": today.isoformat(), "spend_today": round(spend_today), "spend_test": round(spend_test), "spend_month": round(spend_month),
             "test_start": start.isoformat(), "subs_gained": gained, "subs_above_usual": extra,
             "cost_per_sub": round(per_sub, 1) if per_sub else None, "paused_now": acted, "reason": why}
    (Path(root) / "logs").mkdir(exist_ok=True)
    (Path(root) / "logs" / "ads.json").write_text(json.dumps(state, indent=1))
    if report:
        notify(line(state))
    return 0


def line(state: dict) -> str:
    per = f"Rs {state['cost_per_sub']} per new subscriber" if state.get("cost_per_sub") else "no new subscribers above the usual pace yet"
    return (f"📣 Ads: Rs {state['spend_today']:,} today, Rs {state['spend_test']:,} since {state['test_start'][5:]} · "
            f"{state['subs_above_usual']} subscribers above the usual pace · {per}")


def card_line(root: Path = ROOT, day: date | None = None) -> str:
    """The 9 pm card's line, from the last run on that day; "" when the watch has not run today."""
    try:
        state = json.loads((Path(root) / "logs" / "ads.json").read_text())
    except (OSError, ValueError):
        return ""
    return line(state) if day is None or state.get("day") == day.isoformat() else ""


def check(env=None, notify=telegram.send, call=youtube.call, token=None) -> int:
    """Proves the Google Ads permission works and lists the Ads accounts it can reach (founder, 31 Oct 2026: "please check step 4")."""
    try:
        tok = token or access_token(env)
    except secrets.MissingSecret:
        notify("📣 Ads check: ADS_REFRESH_TOKEN is not saved in GitHub yet (step 4 not finished).")
        return 1
    status, _h, body = call("GET", f"{API}/customers:listAccessibleCustomers", tok)
    if status != 200:
        notify(f"📣 Ads check: the permission works, but Google Ads answered {status}: {secrets.scrub(json.dumps(body))[:200]}")
        return 1
    ids = [r.split("/")[-1] for r in body.get("resourceNames", [])]
    shown = ", ".join(f"{i[:3]}-{i[3:6]}-{i[6:]}" for i in ids) or "none yet (create the Google Ads account)"
    notify(f"📣 Ads check: step 4 works ✅. Google Ads accounts this permission can reach: {shown}")
    print(shown, flush=True)
    return 0


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    try:
        if "--check" in argv:
            return check()
        return run(report="--report" in argv)
    except Exception as e:
        telegram.send(f"📣 Ads watch failed: {secrets.scrub(str(e))[:200]}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
