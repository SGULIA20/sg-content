"""Launches the founder's Rs 6,000 YouTube promotion test through the Google Ads API (founder, 31 Oct 2026: "I want to automise step 3").

One Demand Gen campaign per channel (YouTube feed, Shorts and watch pages; the API cannot create classic video campaigns): the channel's
newest public long video, India, Hindi and English, Maximize clicks, Rs 3,000 over 14 days (a daily budget of Rs 215 with an end date),
the channel logo and plain Hinglish lines, and a link that opens the channel's Subscribe prompt. Every request goes to Google first in
check-only mode (validateOnly), which spends nothing; only `--live` creates campaigns, once per channel (logs/ads-launch.json). The ads
watch (engine/ads.py) then reports daily and pauses on the founder's rules.

python -m engine.adlaunch            check only: Google validates everything, nothing is created or spent
python -m engine.adlaunch --live     create the campaigns (each channel once)
"""
import base64
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import ads, pieces, secrets, slots, telegram, youtube
from .config import CHANNELS, ROOT, YOUTUBE_URLS

TEST_DAYS = 14
BUDGET_PER_CHANNEL_INR = 3000
INDIA, HINDI, ENGLISH = "geoTargetConstants/2356", "languageConstants/1023", "languageConstants/1000"
LINES = {
    "sglearning": {"headlines": ["Paise ki seedhi baat", "Learning with SG", "Aapke paise ki khabar"],
                   "long": ["Paise, naukri aur AI ki badi khabrein, aam bolchaal mein samjho"],
                   "descriptions": ["Har din ek kaam ki baat: EMI, SIP, naukri, AI. Subscribe karo, free hai."]},
    "arthvan": {"headlines": ["Sabut ke saath itihaas", "SG-MYTH-WORLD", "Purani kahaniyan, naye sabut"],
                "long": ["Mahabharat, Dwarka aur Harappa: kahani aur archaeology ke sabut saath saath"],
                "descriptions": ["Kahani bhi, sabut bhi. Har hafte nayi khoj. Subscribe karo, free hai."]},
}
LAUNCHED = "ads-launch.json"


def best_long(channel: str, root: Path, now_utc: datetime):
    """The channel's newest long video that is already public."""
    longs = [p for p in pieces.list_all(root) if p.channel == channel and p.kind == "long" and p.ids.get("yt_id")
             and not p.ids.get("unlisted") and slots.publish_at(channel, "long", p.publish_day) <= now_utc]
    return max(longs, key=lambda p: p.publish_day) if longs else None


def operations(cid: str, channel: str, video_id: str, logo: bytes, today, n: int) -> list:
    """The mutate operations for one channel's campaign, with temporary ids -n*10-1 ... so channels never collide."""
    rn = lambda kind, k: f"customers/{cid}/{kind}/-{n * 10 + k}"
    name = CHANNELS[channel].display_name
    tag = f"SG test {today.isoformat()} {name}"
    lines = LINES[channel]
    text = lambda xs: [{"text": x} for x in xs]
    end = today + timedelta(days=TEST_DAYS - 1)
    return [
        {"assetOperation": {"create": {"resourceName": rn("assets", 1), "name": f"{tag} logo", "type": "IMAGE",
                                       "imageAsset": {"data": base64.b64encode(logo).decode()}}}},
        {"assetOperation": {"create": {"resourceName": rn("assets", 2), "name": f"{tag} video", "type": "YOUTUBE_VIDEO",
                                       "youtubeVideoAsset": {"youtubeVideoId": video_id}}}},
        {"campaignBudgetOperation": {"create": {"resourceName": rn("campaignBudgets", 3), "name": f"{tag} budget",
                                                "amountMicros": str(round(BUDGET_PER_CHANNEL_INR / TEST_DAYS) * 1_000_000),
                                                "deliveryMethod": "STANDARD", "explicitlyShared": False}}},
        {"campaignOperation": {"create": {"resourceName": rn("campaigns", 4), "name": tag, "status": "ENABLED",
                                          "advertisingChannelType": "DEMAND_GEN", "campaignBudget": rn("campaignBudgets", 3),
                                          "targetSpend": {},
                                          "containsEuPoliticalAdvertising": "DOES_NOT_CONTAIN_EU_POLITICAL_ADVERTISING",
                                          "startDateTime": f"{today.isoformat()} 00:00:00", "endDateTime": f"{end.isoformat()} 23:59:59"}}},
        {"campaignCriterionOperation": {"create": {"campaign": rn("campaigns", 4), "location": {"geoTargetConstant": INDIA}}}},
        {"campaignCriterionOperation": {"create": {"campaign": rn("campaigns", 4), "language": {"languageConstant": HINDI}}}},
        {"campaignCriterionOperation": {"create": {"campaign": rn("campaigns", 4), "language": {"languageConstant": ENGLISH}}}},
        {"adGroupOperation": {"create": {"resourceName": rn("adGroups", 5), "name": f"{tag} group", "campaign": rn("campaigns", 4),
                                         "status": "ENABLED"}}},
        {"adGroupAdOperation": {"create": {"adGroup": rn("adGroups", 5), "status": "ENABLED", "ad": {
            "name": f"{tag} ad", "finalUrls": [YOUTUBE_URLS[channel]],
            "demandGenVideoResponsiveAd": {"headlines": text(lines["headlines"]), "longHeadlines": text(lines["long"]),
                                           "descriptions": text(lines["descriptions"]), "videos": [{"asset": rn("assets", 2)}],
                                           "logoImages": [{"asset": rn("assets", 1)}], "businessName": {"text": name[:25]}}}}}},
    ]


def run(root: Path = ROOT, now_utc: datetime | None = None, env=None, live: bool = False, notify=telegram.send, call=youtube.call,
        token=None, cfg: dict | None = None) -> int:
    now_utc = now_utc or datetime.now(timezone.utc)
    cfg = ads.settings() if cfg is None else cfg
    cid = str(cfg.get("customer_id", "")).replace("-", "")
    if not cid:
        notify("📣 Ads launch: no Google Ads customer ID in content/ads.json yet.")
        return 1
    state_path = Path(root) / "logs" / LAUNCHED
    try:
        launched = json.loads(state_path.read_text())
    except (OSError, ValueError):
        launched = {}
    today = slots.ist(now_utc).date()
    ops, plan = [], []
    for n, channel in enumerate(("sglearning", "arthvan"), 1):
        if channel in launched:
            continue
        video = best_long(channel, root, now_utc)
        if video is None:
            plan.append(f"{CHANNELS[channel].display_name}: no public long video yet, skipped")
            continue
        logo = (Path(root) / "assets" / "logo" / f"{channel}-320.png").read_bytes()
        ops += operations(cid, channel, video.ids["yt_id"], logo, today, n)
        plan.append(f"{CHANNELS[channel].display_name}: {video.id} (youtu.be/{video.ids['yt_id']})")
    if not ops:
        notify("📣 Ads launch: nothing to launch (" + "; ".join(plan or ["both channels already launched"]) + ").")
        return 0
    tok = token or ads.access_token(env)
    status, _h, body = call("POST", f"{ads.API}/customers/{cid}/googleAds:mutate", tok,
                            json_body={"mutateOperations": ops, "validateOnly": not live}, headers=ads._headers(cfg))
    if status != 200:
        notify(f"📣 Ads launch {'FAILED' if live else 'check found problems'} ({status}): {secrets.scrub(json.dumps(body))[:700]}")
        return 1
    if not live:
        notify("📣 Ads launch check passed ✅ (nothing created, nothing spent). Ready to launch Rs 3,000 per channel over 14 days: "
               + "; ".join(plan))
        return 0
    for line in plan:
        for channel in ("sglearning", "arthvan"):
            if line.startswith(CHANNELS[channel].display_name) and "skipped" not in line:
                launched[channel] = {"day": today.isoformat(), "video": line}
    state_path.parent.mkdir(exist_ok=True)
    state_path.write_text(json.dumps(launched, indent=1))
    notify("🚀 Ads launched: Rs 3,000 per channel over 14 days, India, Hindi and English; clicks open the Subscribe prompt. "
           + "; ".join(plan) + ". The watch pauses them on your rules and reports daily at 20:30 WAT.")
    return 0


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    try:
        return run(live="--live" in argv)
    except Exception as e:
        telegram.send(f"📣 Ads launch crashed: {secrets.scrub(str(e))[:200]}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
