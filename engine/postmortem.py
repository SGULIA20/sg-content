"""The weekly post-mortem (founder, 24 Nov 2026: "Build the weekly post-mortem next"; the last part of the December test). Every Monday
Claude is shown how last week's videos really did (for each: the title, the opening line he spoke, the first lines of the script, how
many viewers were still there at each point of the video, views and the share watched), beside the thumbnails of the videos that went
viral that week, and writes what to do differently. Three things come out of it:

  1. lessons for the writers: the script writer and the hook writer read them on every video of the following week;
  2. a look for thumbnails, taken from the viral thumbnails (colour, framing, size of face and words), added to the thumbnail prompt;
  3. a short report for the founder on Telegram.

It reads numbers and other channels' public thumbnails only. It never watches, downloads or copies another creator's video.

python -m engine.postmortem [--dry]
"""
import json
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import pieces, secrets, ytwatch
from .config import CHANNELS, LOGS_DIR, ROOT

MODEL = "claude-opus-5-5"
OUT = LOGS_DIR / "postmortem.json"
DAYS = 10                               # videos published in this window are looked at: a week, and a few days for numbers to settle
MAX_VIDEOS = 16
MAX_THUMBS = 6
FRESH_DAYS = 12                         # lessons older than this are not handed to the writers any more
THUMB = "https://i.ytimg.com/vi/{id}/hqdefault.jpg"
PROMPT = """You are reviewing last week's videos of the YouTube channel "{channel}" ({about}) to make next week's hold more viewers.
The channel is small; its problem is that people leave in the first seconds and little is watched to the end.

OUR VIDEOS (numbers from YouTube's own analytics; "still_watching" is the share of viewers left at that point of the video; the ig_ numbers are the same video as an Instagram Reel, where
"ig_skipped_early_pct" is the share who swiped away in the first three seconds, the fastest sign of a weak opening; "opened_on", where given, is a test:
some Shorts open on the story's picture and some on the presenter, so compare the early swipes of the two groups and say which is ahead and by how much, or that it is too early to tell):
{videos}

{viral}

Work only from this evidence. Compare the videos that held viewers with the ones that lost them: the opening line, the first scenes,
the title, the length. Where the numbers are too few to say (under 50 views), say so and do not build a rule on them.

Reply with JSON only:
{{"lessons": ["<at most 6 short instructions for the script writer and the hook writer, each one concrete enough to follow and tied to
               what the numbers showed, e.g. 'Name the person in the first three words: the two videos that did held 20 points more
               viewers at 10%'>"],
  "thumbnail_look": "<two sentences describing what the viral thumbnails have in common (colours, how much of the frame the face or
                     object takes, how many words and how big), written as an instruction for a thumbnail; empty if none were shown>",
  "best": "<our best video and the one reason it held>", "worst": "<our weakest and the one reason it lost people>",
  "report": "<for the owner, who is not technical: at most 6 short lines in plain English, numbers included, ending with the one change
             that matters most this week>"}}"""
ABOUT = {"sglearning": "anything worth knowing, explained plainly", "arthvan": "the myths of the world and the reason behind each"}


def per_video(token: str, start: date, end: date, call=None) -> dict:
    """{video id: {"views", "watched_pct", "avg_seconds"}} for the channel's videos in the window."""
    kw = {"call": call} if call else {}
    rows = ytwatch.query(token, {"startDate": start.isoformat(), "endDate": end.isoformat(), "dimensions": "video",
                                 "metrics": "views,averageViewPercentage,averageViewDuration", "sort": "-views", "maxResults": 50}, **kw)
    return {r[0]: {"views": int(r[1]), "watched_pct": round(float(r[2]), 1), "avg_seconds": int(r[3])} for r in rows if r and r[0] != "error"}


def instagram(root: Path, today: date, env=None, collect=None) -> dict:
    """{piece id: {"ig_views", "ig_skipped_early_pct", "ig_watched_seconds"}} for the Shorts of the window. Instagram's numbers arrive
    within a day, YouTube's two or three days late, so these let a Reel be judged the morning after it goes out. {} when unreadable."""
    try:
        if collect is None:
            from . import whatworks
            collect = whatworks.collect
        rows = collect(today - timedelta(days=DAYS), today, env, root)
    except Exception as e:
        print(f"post-mortem: Instagram numbers not read ({type(e).__name__}: {secrets.scrub(str(e))[:120]})", flush=True)
        return {}
    return {r["id"]: {"ig_views": r.get("ig_views"), "ig_skipped_early_pct": r.get("ig_skip_rate"), "ig_watched_seconds": r.get("ig_watch_s")}
            for r in rows if r.get("ig_views")}


def videos(root: Path, channel: str, today: date, stats: dict, curve, ig: dict | None = None) -> list:
    """Last week's published videos of the channel with what the review needs; most viewed first."""
    out = []
    for p in pieces.list_all(root):
        if p.channel != channel or not p.ids.get("yt_id") or not p.publish_day or not (today - timedelta(days=DAYS) <= p.publish_day <= today):
            continue
        s = stats.get(p.ids["yt_id"], {})
        scenes = (p.script or {}).get("scenes") or []
        row = {"day": p.publish_day.isoformat(), "kind": p.kind, "title": str((p.script or {}).get("title", "")).replace("*", ""),
               "spoken_opening": str(((p.topic or {}).get("intro") or {}).get("text") or (p.script or {}).get("hook") or "")[:200],
               "first_lines": [str(sc.get("vo", ""))[:140] for sc in scenes[:3]], "scenes": len(scenes),
               "views": s.get("views", 0), "watched_pct": s.get("watched_pct"), "avg_seconds": s.get("avg_seconds")}
        row.update((ig or {}).get(p.id, {}))
        if s.get("views", 0) >= 20:                                   # a curve from a handful of views says nothing
            try:
                row["still_watching"] = dict(curve(p.ids["yt_id"]))
            except Exception:
                pass
        if p.ids.get("open_test"):                                     # the opening-picture test: which half this Short was in
            row["opened_on"] = "the story's picture for 1.5 s, then the presenter" if p.ids["open_test"] == "picture" else "the presenter"
        if (p.ids.get("watch") or {}).get("opening") is not None:
            row["review_opening_score"] = p.ids["watch"]["opening"]
            if p.ids["watch"].get("best_change"):                     # what the finished-video review said would have helped most
                row["review_said"] = str(p.ids["watch"]["best_change"])[:200]
        out.append(row)
    return sorted(out, key=lambda r: -r["views"])[:MAX_VIDEOS]


def viral(root: Path, channel: str) -> list:
    """[{"id", "title", "views"}] of the week's most-viewed videos the planner saw (content/weekly-plan.json viral)."""
    try:
        plan = json.loads((Path(root) / "content" / "weekly-plan.json").read_text())
    except (OSError, ValueError):
        return []
    return [v for v in (plan.get("viral") or {}).get(channel, []) if v.get("id")][:MAX_THUMBS]


def content_for(channel: str, vids: list, top: list) -> list:
    text = PROMPT.format(channel=CHANNELS[channel].display_name, about=ABOUT.get(channel, ""),
                         videos=json.dumps(vids, indent=1, ensure_ascii=False),
                         viral=("THE WEEK'S MOST-VIEWED VIDEOS IN THIS SUBJECT (other channels; their thumbnails follow in this order):\n"
                                + "\n".join(f"{i}. {v['views']:,} views: {v['title'][:100]}" for i, v in enumerate(top, 1))) if top else "(no viral list this week)")
    blocks = [{"type": "text", "text": text}]
    for v in top:
        blocks.append({"type": "image", "source": {"type": "url", "url": THUMB.format(id=v["id"])}})
    return blocks


def _ask(content: list) -> str:
    import anthropic
    client = anthropic.Anthropic(api_key=secrets.get("ANTHROPIC_API_KEY"))
    r = client.messages.create(model=MODEL, max_tokens=12000, output_config={"effort": "high"}, messages=[{"role": "user", "content": content}])
    try:
        from . import writer
        writer.record_spend(r.usage, writer.SPEND_FILE, None)
    except Exception:
        pass
    return "".join(getattr(b, "text", "") for b in r.content).strip()


def review(channel: str, vids: list, top: list, ask=_ask) -> dict:
    raw = ask(content_for(channel, vids, top))
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        raise ValueError(f"no JSON in the review (starts: {raw[:100]!r})")
    d = json.loads(m.group(0))
    return {"lessons": [str(x)[:260] for x in (d.get("lessons") or []) if str(x).strip()][:6], "thumbnail_look": str(d.get("thumbnail_look") or "")[:400],
            "best": str(d.get("best") or "")[:240], "worst": str(d.get("worst") or "")[:240], "report": str(d.get("report") or "")[:900]}


def load(path: Path | None = None) -> dict:
    try:
        return json.loads(Path(path or OUT).read_text())
    except (OSError, ValueError):
        return {}


def lessons(channel: str, today: date | None = None, path: Path | None = None) -> list:
    """This week's lessons for the writers; [] when there is no fresh post-mortem (a stale one is not followed for ever)."""
    data = load(path)
    try:
        made = date.fromisoformat(str(data.get("date")))
    except ValueError:
        return []
    if ((today or date.today()) - made).days > FRESH_DAYS:
        return []
    return list((data.get(channel) or {}).get("lessons") or [])


def thumbnail_look(channel: str, today: date | None = None, path: Path | None = None) -> str:
    data = load(path)
    try:
        made = date.fromisoformat(str(data.get("date")))
    except ValueError:
        return ""
    return "" if ((today or date.today()) - made).days > FRESH_DAYS else str((data.get(channel) or {}).get("thumbnail_look") or "")


def run(root: Path = ROOT, today: date | None = None, env=None, ask=_ask, notify=None, token_for=None, call=None, out: Path | None = None, dry: bool = False,
        daily: bool = False, ig_collect=None) -> dict:
    """daily (founder, 24 Nov 2026: "I want you to review each reel or long video you are posting and take necessary actions for next
    reel or video"): the same review every morning over the rolling window, so each video that went out yesterday is judged (Instagram's
    numbers are in by then) and the lessons the writers, the hook writer and the planner read are renewed before the next video is made.
    He is told only what changed, in a few lines; the long report stays for Monday."""
    from . import youtube
    today = today or datetime.now(timezone.utc).date()
    result, report = {"date": today.isoformat()}, [f"🔎 {'Yesterday\'s videos reviewed' if daily else 'Weekly post-mortem'} ({today:%d %b})"]
    ig = instagram(root, today, env, ig_collect)
    for ch in CHANNELS:
        try:
            token = (token_for or youtube.access_token)(ch, env)
            start = today - timedelta(days=DAYS + 2)
            stats = per_video(token, start, today, call)
            kw = {"call": call} if call else {}
            vids = videos(root, ch, today, stats, lambda vid: ytwatch.retention(token, vid, start, today, **kw), ig)
            if not vids:
                report.append(f"\n{CHANNELS[ch].display_name}: no published videos in the last {DAYS} days to review.")
                continue
            r = review(ch, vids, viral(root, ch), ask)
            result[ch] = {**r, "videos": len(vids)}
            if daily:
                report.append(f"\n{CHANNELS[ch].display_name}: next videos will\n" + "\n".join(f"• {x}" for x in r["lessons"][:3]))
            else:
                report.append(f"\n{CHANNELS[ch].display_name} ({len(vids)} videos)\n{r['report']}")
        except Exception as e:
            print(f"post-mortem: {ch} skipped ({type(e).__name__}: {secrets.scrub(str(e))[:160]})", flush=True)
            report.append(f"\n{CHANNELS[ch].display_name}: the review could not be made this week ({type(e).__name__}).")
    report.append("\nThese now apply to every video written from today." if daily else "\nThe lessons are now given to the script and hook writers for the coming week.")
    if not dry:
        if len(result) > 1:                                           # an empty week leaves last week's lessons in place until they go stale
            Path(out or OUT).parent.mkdir(parents=True, exist_ok=True)
            Path(out or OUT).write_text(json.dumps(result, indent=1, ensure_ascii=False))
        from . import monday, once
        if notify is None and monday.hold("postmortem", "\n".join(report)):      # on Monday the three reports go out as one message
            return result
        if daily and not once.fresh("daily-lessons", {ch: (result.get(ch) or {}).get("lessons") for ch in CHANNELS}, hours=72, root=root):
            return result                                             # the same lessons as before: nothing new to tell him
        if notify is None:
            from . import telegram
            notify = telegram.send
        notify("\n".join(report)[:3900])
    return result


def main(argv=None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    print(json.dumps(run(dry="--dry" in args, daily="--daily" in args), indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
