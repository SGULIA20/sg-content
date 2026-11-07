"""Weekly YouTube research and the topic plan for the coming days (founder, 7 Nov 2026: "we must do this deep research every week and decide
topics for the next week, otherwise these channels will never grow").

Every Sunday evening: (1) read what viewers are watching on YouTube (engine/ytresearch.py), (2) have Claude propose one topic for every Short
and long that is not made yet, from those signals, the festival calendar and the channel's rules, (3) score each proposal with the topic rule
(engine/topicscore.py), drop weak, repeated or banned ones and fill any gap from the scored banks, (4) write content/weekly-plan.json and send
the plan to the founder on Telegram. The pipeline takes a planned topic first (engine/pipeline.py topic_fn); a planned topic whose research
fails is not retried in a loop. Edit the file to override a topic: it is only read, never rewritten, until the next Sunday.

python -m engine.weekly [--dry]
"""
import json
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import buffer, pieces, secrets, slots, telegram, topics, topicscore, ytresearch
from .config import CHANNELS, CONTENT_DIR, ROOT

PLAN = CONTENT_DIR / "weekly-plan.json"
MIN_SCORE = 6                                   # a proposal below this is replaced from the banks
SHORT_DAYS, LONG_DAYS = 14, 21                  # how far ahead a slot is planned
MYTH_SOURCES = ["asi.nic.in", "en.wikipedia.org", "nio.res.in", "britannica.com", "the scripture or text named in the story"]
PLAN_QUERIES = {
    "sglearning": ["share market kyun gira", "gold silver price kyun", "RBI EMI kam", "petrol diesel daam", "UPI fraud", "bank FD interest", "SIP mutual fund", "tax bachane ke tarike"],
    "arthvan": ["mandir ka rahasya", "mahabharat ka sach", "ramayan ka sach", "shiv mandir rahasya", "bharat ka itihas rahasya", "pauranik katha sach", "kedarnath rahasya", "ancient india mystery"],
}
RULES = {
    "sglearning": "Learning with SG: plain-language money explainers for ordinary Indians (a 15-year-old must follow them). One question about the viewer's own "
                  "money or job, a scare or a choice, with a number. Never company results, deals, crypto, roundups or party politics.",
    "arthvan": "SG-MYTH-WORLD: Indian mythology and history told with evidence (scripture, archaeology, disputed, legend labelled). A famous name, a shock question, "
               "an untold angle. Never communal content, never debunking faith, never party politics.",
}


def _ask_claude(prompt: str) -> str:
    import anthropic
    client = anthropic.Anthropic(api_key=secrets.get("ANTHROPIC_API_KEY"))
    r = client.messages.create(model="claude-sonnet-5-5", max_tokens=14000, messages=[{"role": "user", "content": prompt}])
    try:
        from . import writer
        writer.record_spend(r.usage, writer.SPEND_FILE, None, factor=writer.SONNET_VS_OPUS)
    except Exception:
        pass
    return "".join(getattr(b, "text", "") for b in r.content).strip()


def open_slots(root: Path, today: date) -> list:
    """[(piece_id, channel, kind, day)] not made and not started: the Shorts of the next 14 days and the longs of the next 21."""
    started = {p.id for p in pieces.list_all(root) if p.status in buffer.DONE or p.script or p.status in ("intro-wait", "writing", "researched")}
    out = []
    for ch in CHANNELS:
        for kind, span in (("short", SHORT_DAYS), ("long", LONG_DAYS)):
            for day in slots.publish_dates(ch, kind, today + timedelta(days=1), span):
                pid = slots.piece_id(day, ch, kind)
                if pid not in started:
                    out.append((pid, ch, kind, day))
    return sorted(out, key=lambda s: (s[3], s[1], s[2]))


def recent_titles(root: Path, days: int = 45) -> list:
    out = []
    for p in pieces.list_all(root):
        t = (p.script or {}).get("title") or (p.topic or {}).get("title") or (p.topic or {}).get("title_hi")
        if t:
            out.append(str(t))
    return out[-days * 2:]


def _words(s: str) -> set:
    return {w for w in re.findall(r"[a-z0-9]+", s.lower()) if len(w) > 3}


def repeats(title: str, seen: list, threshold: float = 0.6) -> bool:
    a = _words(title)
    return bool(a) and any(len(a & _words(s)) / max(1, min(len(a), len(_words(s)))) >= threshold for s in seen if _words(s))


def research(env=None, call=None) -> dict:
    """{"sglearning": [rows], "arthvan": [rows]}: the most-viewed videos of the last 14 days for each channel's queries; never raises."""
    from . import youtube
    since = datetime.now(timezone.utc) - timedelta(days=14)
    out = {}
    for ch, queries in PLAN_QUERIES.items():
        rows, seen = [], set()
        try:
            token = youtube.access_token(ch, env) if call is None else "t"
            for q in queries:
                for r in (ytresearch.search(token, q, since, **({"call": call} if call else {})) or []):
                    if r.get("error"):
                        break
                    if r["id"] not in seen:
                        seen.add(r["id"]); rows.append(r)
        except Exception as e:
            print(f"{ch}: research failed ({secrets.scrub(str(e))[:120]})", flush=True)
        out[ch] = sorted(rows, key=lambda r: -r["views"])[:30]
    return out


def _prompt(channel: str, slots_: list, rows: list, today: date, calendar: list, seen: list) -> str:
    near = [f"{e['name']} on {e['date']}" for e in calendar if -3 <= (datetime.strptime(str(e["date"]), "%Y-%m-%d").date() - today).days <= 21]
    signals = "\n".join(f"- {r['views']:,} views, {r['seconds']} s, {r['channel']}: {r['title'][:110]}" for r in rows[:25]) or "(no YouTube data this week)"
    todo = "\n".join(f"- {pid} ({kind}, goes out {day:%a %d %b})" for pid, _c, kind, day in slots_)
    return (f"You plan next week's topics for a YouTube channel. {RULES[channel]}\n\n"
            f"What Hindi viewers in India watched most on YouTube in the last 14 days (their topics, hooks and lengths are the signal):\n{signals}\n\n"
            f"Festivals and events coming: {', '.join(near) or 'none'}.\n"
            f"Topics already covered recently (do not repeat or rephrase): {'; '.join(seen[-40:]) or 'none'}.\n\n"
            f"Propose ONE topic for each slot below. A long video is a deeper telling of a big story; a Short is one sharp question. Use the signals: a scare or a "
            f"choice tied to money (finance) or a famous name with a shock question or an untold angle (mythology). Tie a topic to a festival only when it truly fits. "
            f"Every topic must be checkable against real sources.\nSlots:\n{todo}\n\n"
            f'Reply with JSON only: a list of {{"slot": "<slot id>", "title": "<Hinglish title as a question, Latin script, no emoji, no asterisks>", "summary": "<at most 40 words: what the video '
            f'explains and which facts must be checked>", "hooks": ["<opening question 1>", "<opening question 2>"], "why": "<which signal or date this follows>"}}.')


def _objects(raw: str) -> list:
    """Every complete JSON object in the text, in order: a reply cut off by the length limit still yields the items before the cut."""
    dec, out, i = json.JSONDecoder(), [], 0
    while True:
        i = raw.find("{", i)
        if i < 0:
            return out
        try:
            obj, end = dec.raw_decode(raw[i:])
        except ValueError:
            i += 1
            continue
        out.append(obj)
        i += end


def parse(raw: str) -> list:
    """The proposals in Claude's reply, whatever wraps it: a code fence, prose, an object holding the list, or a reply cut off midway."""
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", (raw or "").strip(), flags=re.M)
    data = None
    for opener, closer in (("[", "]"), ("{", "}")):
        start, end = raw.find(opener), raw.rfind(closer)
        if start >= 0 and end > start:
            try:
                data = json.loads(raw[start:end + 1])
                break
            except ValueError:
                continue
    if isinstance(data, dict):
        data = next((v for v in data.values() if isinstance(v, list)), [data] if data.get("slot") else [])
    if not isinstance(data, list):
        data = [o for o in _objects(raw) if isinstance(o, dict) and (o.get("slot") or o.get("slot_id"))]
    out = []
    for d in data:
        if not isinstance(d, dict):
            continue
        slot = d.get("slot") or d.get("slot_id") or d.get("id") or d.get("piece")
        title = d.get("title") or d.get("topic")
        if slot and title:
            out.append({**d, "slot": str(slot).strip(), "title": re.sub(r"[*_]|[\U0001F300-\U0001FAFF\u2600-\u27BF]", "", str(title)).strip()})
    return out


def build(root: Path, today: date, rows: dict, ask=_ask_claude, calendar: list | None = None, content: Path = CONTENT_DIR) -> dict:
    """The plan: {piece_id: topic}, with each topic's score and why. Claude's proposals first; banks fill what is missing or weak."""
    calendar = calendar if calendar is not None else topicscore.load_calendar(content)
    todo = open_slots(root, today)
    seen = recent_titles(root)
    plan, notes = {}, []
    for ch in CHANNELS:
        mine = [s for s in todo if s[1] == ch]
        if not mine:
            continue
        proposals = {}
        try:
            raw = ask(_prompt(ch, mine, rows.get(ch, []), today, calendar, seen))
            for d in parse(raw):
                proposals[d["slot"]] = d
            if not proposals:
                notes.append(f"{ch}: Claude's reply had no usable topics (starts: {str(raw)[:140]!r}); the banks fill the week")
            elif len(proposals) < len(mine):
                notes.append(f"{ch}: Claude proposed {len(proposals)} of {len(mine)} slots; the banks fill the rest")
        except Exception as e:
            notes.append(f"{ch}: Claude could not propose topics ({secrets.scrub(str(e))[:100]}); the banks fill the week")
        used_here = list(seen)
        used_ids = {p.topic.get("id") for p in pieces.list_all(root) if (p.topic or {}).get("id")}
        for pid, _c, kind, day in mine:
            d = proposals.get(pid)
            topic = None
            if d:
                text = {"title": d["title"], "summary": d.get("summary", ""), "hooks": d.get("hooks") or []}
                pts, why = topicscore.score(text, ch, day, calendar)
                if pts >= MIN_SCORE and not repeats(d["title"], used_here):
                    topic = {"id": f"wk-{pid}", **text, "weekly": True, "topic_score": pts, "topic_score_why": why, "follows": str(d.get("why", ""))[:160]}
                    if ch == "arthvan":
                        topic["allowed_sources"] = MYTH_SOURCES
                else:
                    notes.append(f"{pid}: proposal '{d['title'][:50]}' dropped ({pts} points{', repeat' if repeats(d['title'], used_here) else ''})")
            if topic is None:                                                       # a gap: the best unused bank topic
                bank = (topics.next_money_history(content, used_ids, day) if ch == "sglearning" else topics.next_myth(content, used_ids, day)) \
                    if not (ch == "sglearning" and kind == "long") else topics.next_long_finance(content, used_ids)
                title = str(bank.get("title") or bank.get("title_hi") or "") if bank else ""
                if bank and title not in used_here:                               # a bank that has run round once repeats itself: leave the slot to the usual flow
                    topic = {**bank, "weekly": True, "from_bank": True}
                    used_ids.add(bank.get("id"))
            if topic:
                used_here.append(str(topic.get("title") or topic.get("title_hi") or ""))
                plan[pid] = topic
    return {"week_of": today.isoformat(), "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"), "entries": plan, "notes": notes,
            "signals": {ch: [f"{r['views']:,} {r['title'][:70]}" for r in rows.get(ch, [])[:5]] for ch in rows}}


def save(plan: dict, path: Path = PLAN) -> None:
    Path(path).write_text(json.dumps(plan, indent=1, ensure_ascii=False))


def load(path: Path = PLAN) -> dict:
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return {}


def topic_for(root: Path, piece, used: set, path: Path | None = None) -> dict | None:
    """The planned topic of this piece, unless it was already tried (a planned topic whose research failed is not retried in a loop)."""
    entry = (load(path or (Path(root) / "content" / "weekly-plan.json")).get("entries") or {}).get(piece.id)
    if not entry or entry.get("id") in used:
        return None
    return entry


def message(plan: dict) -> str:
    lines = [f"📅 Topic plan from this week's YouTube research (week of {plan['week_of']})"]
    for ch, label in (("sglearning", "Learning with SG"), ("arthvan", "SG-MYTH-WORLD")):
        rows = sorted(((pid, t) for pid, t in plan["entries"].items() if f"-{ch}-" in pid), key=lambda r: r[0])
        lines.append(f"\n{label} ({len(rows)} slots)")
        for pid, t in rows[:16]:
            day = pid[:10]
            kind = "long" if pid.endswith("long") else "Short"
            title = str(t.get("title") or t.get("title_hi") or "")[:70]
            src = "bank" if t.get("from_bank") else "YouTube signal"
            lines.append(f"{day[5:]} {kind}: {title} [{t.get('topic_score', '-')}, {src}]")
        sig = plan.get("signals", {}).get(ch) or []
        if sig:
            lines.append("Most-viewed now: " + " | ".join(sig[:3]))
    for n in plan.get("notes", [])[:4]:
        lines.append(f"• {n}")
    lines.append("\nTo change a topic, tell Claude which day; the pipeline uses this plan first.")
    return "\n".join(lines)


def run(root: Path = ROOT, today: date | None = None, env=None, ask=_ask_claude, notify=telegram.send, rows: dict | None = None, dry: bool = False) -> dict:
    today = today or date.today()
    rows = rows if rows is not None else research(env)
    plan = build(root, today, rows, ask)
    if not dry:
        save(plan, Path(root) / "content" / "weekly-plan.json")
        notify(message(plan))
    return plan


def main(argv=None) -> int:
    dry = "--dry" in (argv if argv is not None else sys.argv[1:])
    plan = run(dry=dry)
    print(message(plan))
    return 0


if __name__ == "__main__":
    sys.exit(main())
