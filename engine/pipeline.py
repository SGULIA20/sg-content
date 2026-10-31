"""One piece from topic to scheduled upload, every step behind an injectable function (spec §3 steps 1-10, §7)."""
import json
import re
import shutil
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Callable

from . import art, artbatch, assemble, buffer, cards, cartoon, cast, claims, costs, gemini, lint, pieces, qa, research, secrets, slots, storyframe, topics, voice, voicebatch, writer, youtube
from .config import CHANNELS, ROOT, VIDEO, story_words
from .pieces import Piece

TOPIC_TRIES = 3
def is_story(piece: Piece) -> bool:
    from .config import is_story as _is
    return _is(piece.channel, piece.kind)
QA_TOO_LONG = re.compile(r"duration: ([\d.]+)s, allowed [\d.]+-([\d.]+)s")
RESUMABLE = {"written", "voicing", "voiced", "painting", "drawn", "assembled", "failed-voice", "failed-art", "qa_failed"}
DAILY_DRAFTS, DAILY_RESEARCH = 6, 4     # per piece per quota day: a piece that keeps failing stops and waits for tomorrow instead of looping (24 Oct 2026)
PARKED_WRITE = "writing"      # the draft is cooking in Claude's batch lane; topic, facts and the research sheet stay on the piece
HANDLE = "@sanjeev_gulia"
LONG_TARGET_MINUTES = {"sglearning": 12, "arthvan": 14}


@dataclass
class Deps:
    topic: Callable            # (piece, used: set) -> dict | None
    research: Callable         # (topic, channel) -> fact sheet
    write: Callable            # (piece, sheet, library, hashtags) -> {"script", "writer", "note"}
    say: Callable              # (text, voice_id, out_wav) -> seconds
    paint: Callable            # (prompt, out, **kw) -> Path
    avatar: Callable           # (pose) -> Path
    render_card: Callable      # (kind, data, out, size) -> Path
    build: Callable            # (piece, lines, visuals, size, out_dir, **kw) -> Path
    qa: Callable               # (path, kind, voiced_seconds, caption_cues, **kw) -> reasons
    upload: Callable           # (piece, video, thumb) -> youtube id
    lint: Callable             # (piece, prior_scripts) -> reasons
    claims_check: Callable     # (piece) -> unmatched numbers
    commons: Callable          # (query, out_dir) -> {path, credit} | None
    library: list = field(default_factory=list)
    hashtags: dict = field(default_factory=dict)
    voice_id: str = ""
    pack: Callable = None        # (piece) -> parts, for the Gemini presenter-clip path
    pack_send: Callable = None   # (piece, text) -> Path
    cartoon: Callable = None     # (wav, seconds, size, out, mood) -> mp4: code-animated cartoon presenter for avatar scenes
    story_build: Callable = None # (piece, lines, panels, size, out_dir) -> mp4: illustrated-story frame (title band, panel, caption band)
    cast_refs: Callable = None   # (prompt) -> reference PNGs of the cast members the panel names
    subtitles: Callable = None   # (piece, out_dir, video) -> writes SRTs and adds YouTube caption tracks (longs)
    voice_lines: Callable = None # (texts, voice_id, out_dir) -> [(wav, seconds)]: batched synthesis (several scenes per request)
    voice_batch: Callable = None # (piece, texts, voice_id) -> "ready" | "voicing": Gemini Batch API fills the voice cache (half price, no daily cap)
    art_batch: Callable = None   # (piece, jobs) -> "ready" | "painting": Gemini Batch API fills the picture cache at half price
    voice_check: Callable = None # (wav) -> transcript: every voiced line is read back and re-made if spoken twice or cut short


def _jsonable(d: dict) -> dict:
    """Topic dicts may carry datetimes from the feed parser; records and prompts want strings."""
    from datetime import date, datetime
    return {k: (v.isoformat() if isinstance(v, (datetime, date)) else v) for k, v in d.items()}


def _used(root: Path) -> tuple:
    """(links/topic ids used in the last 30 days, prior script texts for the originality check)."""
    links, ids, prior = set(), set(), []
    for p in pieces.list_all(root):
        if p.topic.get("link"):
            links.add(p.topic["link"])
        if p.topic.get("id"):
            ids.add(p.topic["id"])
        if p.script and p.status not in ("rejected",):
            prior.append(lint.script_text(p))
    return links | ids, prior


SHORT_PANEL_NOTE = (" Full-bleed tall picture filling the whole canvas edge to edge: no border, no frame, no panel outline, no empty box or blank"
                    " strip anywhere (26 Oct 2026: a comic-style panel came back framed with an empty box below). Keep the lower third calm"
                    " (floor, table, sea, sky or ground continuing the scene), with no face or key object there.")
LONG_PANEL_NOTE = (" Very wide cinematic frame; every face and the key object sit in the middle band, nothing important near the top or"
                   " bottom edge (31 Oct 2026: 4:5 panels lost the heads when fitted into the wide strip between the title and caption bands).")
LONG_PANEL_ASPECT = "21:9"                     # the long video's picture strip is 1920x713 (about 2.7:1); 21:9 loses little


def panel_request(piece: Piece, prompt: str) -> tuple:
    """(full prompt, aspect) for one story panel. The half-price batch and the per-scene call must send exactly this, or the scene
    call misses the batch's cached picture and paints it again at full price (26-31 Oct 2026: every panel was paid twice)."""
    if piece.kind == "short":
        return art.style_prompt(piece.channel, prompt + SHORT_PANEL_NOTE), "2:3"
    return art.style_prompt(piece.channel, prompt + LONG_PANEL_NOTE), LONG_PANEL_ASPECT


def recent_openers(root: Path, piece: Piece, n: int = 5) -> list:
    """[(id, first picture prompt)] of the same channel's last n Shorts before this one."""
    rows = []
    for p in pieces.list_all(root):
        if p.channel == piece.channel and p.kind == "short" and p.id != piece.id and p.script and p.status != "rejected" \
                and p.publish_day < piece.publish_day:
            sc = (p.script.get("scenes") or [{}])[0]
            rows.append((p.publish_day, p.id, str((sc.get("visual") or {}).get("prompt") or "")))
    return [(pid, prompt) for _d, pid, prompt in sorted(rows)[-n:]]


FRESH_WEEKDAY = 6                  # Sunday's Short is always a new topic: no remakes (founder, 27 Oct 2026)


WEAK_VIEWS, WEAK_SETTLED_DAYS = 1000, 4         # founder, 27 Oct 2026: Reels under 1,000 Instagram views get a second chance, one a day
WEAK_NOTE = ("A SECOND CHANCE for a topic whose first Reel few people watched (it had {views} views). Same sourced facts, but a NEW "
             "angle: a sharper opening question, a different first picture, a different story moment. Never reuse its lines or its title.")


def weak_remake_topic(piece: Piece, root: Path, today: date | None = None) -> dict | None:
    """Mon-Sat: the oldest Short (either channel) under WEAK_VIEWS on Instagram, settled for WEAK_SETTLED_DAYS, never remade and not
    itself a remake, comes back as a fresh version in its own channel's slot. At most one per day across both channels."""
    if piece.kind != "short" or piece.publish_day.weekday() == FRESH_WEEKDAY:
        return None
    today = today or date.today()
    try:
        rows = json.loads((Path(root) / "logs" / "whatworks.json").read_text()).get("month") or []
    except (FileNotFoundError, ValueError):
        return None
    all_pieces = pieces.list_all(root)
    remade = {p.topic.get("remake_of") for p in all_pieces if p.topic.get("remake_of")}
    is_remake = {p.id for p in all_pieces if p.topic.get("remake_of")}
    if any(p.publish_day == piece.publish_day and p.id != piece.id and p.topic.get("remake_kind") == "weak" for p in all_pieces):
        return None                                                   # today's second chance is already the other channel's
    weak = sorted((r for r in rows if r.get("ig_views") is not None and r["ig_views"] < WEAK_VIEWS and r["id"] not in remade
                   and r["id"] not in is_remake and (today - date.fromisoformat(r["day"])).days >= WEAK_SETTLED_DAYS),
                  key=lambda r: (r["day"], r["id"]))
    if not weak or weak[0]["channel"] != piece.channel:
        return None
    orig = pieces.load(weak[0]["id"], root)
    if not (orig and orig.facts and orig.script):
        return None
    base = {k: v for k, v in orig.topic.items() if k not in ("look", "sheet", "revise", "rewrite")}
    return {**base, "id": f"{orig.topic.get('id') or orig.id}#second", "remake_of": orig.id, "remake_kind": "weak",
            "remake_note": WEAK_NOTE.format(views=weak[0]["ig_views"]), "remake_views": weak[0]["ig_views"], "remake_facts": orig.facts}


def _pick_topic(piece: Piece, deps: Deps, root: Path, used: set) -> dict | None:
    if piece.topic.get("preset"):                                     # a topic chosen up front (the news Short, an extra Reel)
        return piece.topic["preset"]
    remake = None if (piece.id.endswith("-news") or re.search(r"-x\d+$", piece.id)) else weak_remake_topic(piece, root)
    if remake:
        return remake
    if piece.channel == "arthvan" and piece.kind == "short" and not is_story(piece):
        long_id = buffer.long_for_short(piece.channel, piece.publish_day)
        long_p = pieces.load(long_id, root)
        if not long_p or not long_p.script:                       # launch week: tease the coming long instead
            long_id = buffer.next_long_for_short(piece.channel, piece.publish_day)
            long_p = pieces.load(long_id, root)
        if not long_p or not long_p.script:
            return None
        siblings = [p for p in pieces.list_all(root) if p.channel == "arthvan" and p.kind == "short" and p.topic.get("from_long") == long_id and p.id != piece.id]
        hooks = long_p.topic.get("hooks") or []
        hook = hooks[len(siblings) % len(hooks)] if hooks else long_p.script.get("hook", "")
        return {"from_long": long_id, "id": f"{long_p.topic.get('id', long_id)}#short{len(siblings) + 1}", "hook": hook,
                "title": long_p.topic.get("title_hi", long_id), "long_scenes": long_p.script["scenes"], "long_facts": long_p.facts}
    return deps.topic(piece, used)


def place_key(piece: Piece) -> str:
    """The place a myth Short is about, as one search word ("Konark, Odisha" -> "Konark"), only when the script itself names it:
    a remade topic can carry the first story's place (2 Nov: place Abhaneri, story about Kedarnath), and a wrong photo is worse than none."""
    place = str((piece.topic or {}).get("place") or "")
    key = place.split(",")[0].split(" to ")[0].strip()
    said = " ".join([str((piece.script or {}).get("title", "")), str((piece.script or {}).get("hook", ""))]).lower()
    return key if key and key.lower() in said else ""


def _place_photo(piece: Piece, deps: Deps, out_dir: Path, out: Path, scene: dict) -> Path | None:
    """Founder, 30 Oct 2026 ("B"): a myth Short opens on a real photo of its place (free-licensed, Wikimedia Commons, credited),
    which stops the scroll better than a drawing of it; the drawn story follows. None when no fitting photo is found."""
    key = place_key(piece)
    if not (key and deps.commons):
        return None
    try:
        got = deps.commons(key, out_dir / "photos")
    except Exception as e:
        print(f"{piece.id}: no place photo ({secrets.scrub(str(e))[:80]})", flush=True)
        return None
    if not got or key.lower() not in str(got.get("title", "")).lower():
        return None
    piece.topic.setdefault("credits", []).append(got["credit"])
    scene["credit"] = got["credit"]
    shutil.copy(got["path"], out)
    return out


def graphics(piece: Piece) -> bool:
    """News Reels drawn as code-made cards, no paid pictures (founder, 30 Oct 2026)."""
    t = piece.topic or {}
    return bool(t.get("graphics") or (t.get("preset") or {}).get("graphics"))


def _newscard(piece: Piece, i: int, scene: dict, deps: Deps, out: Path, size: tuple) -> Path:
    from . import newscard, storyframe
    t = {**(piece.topic.get("preset") or {}), **piece.topic}
    scenes = piece.script["scenes"]
    roundup = "TOP 10 ROUNDUP" in str(t.get("summary", ""))
    data = newscard.data(scene, i, len(scenes), t.get("category") or "money", roundup)
    return deps.render_card("newscard", data, out, (size[0], size[1] - int(size[1] * storyframe.TOP)))


def _visual_for(piece: Piece, i: int, scene: dict, deps: Deps, out_dir: Path, size: tuple, line=None) -> Path:
    v = scene.get("visual") or {}
    kind = v.get("type", "art")
    out = out_dir / f"visual{i:02d}.png"
    if graphics(piece) and piece.kind == "short":
        return _newscard(piece, i, scene, deps, out, size)
    if i == 0 and piece.channel == "arthvan" and piece.kind == "short":
        photo = _place_photo(piece, deps, out_dir, out, scene)
        if photo:
            return photo
    if is_story(piece):
        kind = "art"
    if kind == "avatar" and deps.cartoon and line is not None:
        wav, seconds = line
        return deps.cartoon(wav, seconds + assemble.PAD_S, size, out_dir / f"visual{i:02d}.mp4", v.get("prompt") or "explaining_front")
    if kind == "avatar":
        src = deps.avatar(v.get("prompt") or "explaining_front")
        if i == 0:
            return deps.render_card("hook", {"line": piece.script["hook"], "avatar_path": src}, out, size)
        if i == len(piece.script["scenes"]) - 1:
            return deps.render_card("end", {"question": piece.script["end_question"], "handle": HANDLE, "avatar_path": src}, out, size)
        return deps.render_card("avatar", {"avatar_path": src}, out, size)
    if kind == "card" and v.get("card"):
        return deps.render_card("number", v["card"], out, size)
    if kind == "photo":
        got = deps.commons(v.get("prompt", ""), out_dir / "photos")
        if got:
            piece.topic.setdefault("credits", []).append(got["credit"])
            scene["credit"] = got["credit"]
            shutil.copy(got["path"], out)
            return out
    if is_story(piece):
        prompt = v.get("prompt") or piece.script["hook"]
        refs = deps.cast_refs(prompt, channel=piece.channel) if deps.cast_refs else []
        full, aspect = panel_request(piece, prompt)
        got = deps.paint(full, out, aspect=aspect, refs=refs)
        if piece.kind == "short" and Path(got).exists() and art.blank_share(got) > art.BLANK_MAX:   # framed, with an empty box below: redraw once
            got = deps.paint(art.style_prompt(piece.channel, prompt + SHORT_PANEL_NOTE + " Paint the scene all the way down to the bottom edge."),
                             out, aspect="2:3", refs=refs)
        return got
    aspect = "9:16" if size[1] > size[0] else "16:9"
    return deps.paint(art.style_prompt(piece.channel, v.get("prompt") or piece.script["hook"]), out, aspect=aspect)


def _source_strips(piece: Piece, deps: Deps, out_dir: Path, size: tuple) -> dict:
    """One strip per distinct source actually used; keyed by fact index so each scene shows its own source."""
    if piece.channel != "sglearning" or not piece.facts:
        return {}
    strips, by_name = {}, {}
    for sc in piece.script["scenes"]:
        for i in sc.get("facts_used", []):
            if i in strips or i >= len(piece.facts):
                continue
            f = piece.facts[i]
            name = f.get("source_name", "Source")
            if name not in by_name:
                by_name[name] = deps.render_card("source", {"name": name, "date": f.get("source_date", "")}, out_dir / f"source-{len(by_name)}.png", (size[0], 120))
            strips[i] = by_name[name]
    return strips


def _label_chips(piece: Piece, deps: Deps, out_dir: Path) -> dict:
    if piece.channel != "arthvan":
        return {}
    return {lab: deps.render_card("label", {"label": lab}, out_dir / f"label-{lab}.png", (400, 90)) for lab in lint.MYTH_LABELS}


def picture_jobs(piece: Piece, deps: Deps) -> list:
    """[(prompt, refs, aspect)] for every drawn panel of a story piece plus its thumbnail picture, exactly as the per-scene calls build them."""
    from . import thumbs
    jobs = []
    for sc in (piece.script or {}).get("scenes", []):
        prompt = (sc.get("visual") or {}).get("prompt") or piece.script["hook"]
        refs = deps.cast_refs(prompt, channel=piece.channel) if deps.cast_refs else []
        full, aspect = panel_request(piece, prompt)
        jobs.append((full, list(refs), aspect))
    jobs.append((thumbs.paint_prompt(piece), [], "9:16" if piece.kind == "short" else "16:9"))
    return jobs


def _thumb(piece: Piece, deps: Deps, out_dir: Path) -> Path:
    """The topic-name thumbnail (engine.thumbs); Shorts also get a 9:16 cover for Instagram."""
    from . import thumbs
    if is_story(piece) and graphics(piece) and (out_dir / "visual00.png").exists():     # the first news card stands in for the picture
        return thumbs.make(piece, out_dir, paint=lambda prompt, out, aspect=None, refs=None: out_dir / "visual00.png",
                           render=deps.render_card)["thumb"]
    if is_story(piece):
        return thumbs.make(piece, out_dir, paint=deps.paint, render=deps.render_card, cast_refs=deps.cast_refs or (lambda s, **kw: []))["thumb"]
    title = piece.script["captions"]["youtube"]["title"]
    words = [w for w in title.replace("?", "? ").split() if w][:4]
    number = next((c["big_number"] for c in piece.script.get("cards", []) if c.get("big_number")), "")
    return deps.render_card("thumb", {"words": words[:3], "number": number, "avatar_path": deps.avatar("surprised")}, out_dir / "thumb.jpg", (1280, 720))


def _allow(piece: Piece, what: str, limit: int) -> bool:
    """Counts one more draft or research call for this piece today; False when today's allowance is used up."""
    from .config import today_pacific
    b = piece.ids.setdefault("budget", {})
    day = today_pacific().isoformat()
    if b.get("day") != day:
        b.clear(); b["day"] = day
    if b.get(what, 0) >= limit:
        return False
    b[what] = b.get(what, 0) + 1
    return True


def make(piece: Piece, deps: Deps, root: Path = ROOT, dry_run: bool = False, pack_mode: bool = False) -> Piece:
    """_make, plus the running cost of the piece (engine/costs.py): kept on the piece in ids["cost"] across runs, re-makes and crashes."""
    with costs.track() as spent:
        try:
            result = _make(piece, deps, root, dry_run, pack_mode)
        finally:
            if not dry_run and costs.nonzero(spent):
                piece.ids["cost"] = costs.merge(piece.ids.get("cost"), spent)
    if not dry_run and costs.nonzero(spent):
        result.ids["cost"] = piece.ids["cost"]
        pieces.save(result, root)
    return result


def _make(piece: Piece, deps: Deps, root: Path = ROOT, dry_run: bool = False, pack_mode: bool = False) -> Piece:
    """Runs the pipeline for one piece and records every transition. Returns the piece in its final state for this run."""
    if piece.status in buffer.DONE:
        return piece
    used, prior = _used(root)
    size = VIDEO[piece.kind]
    out_dir = Path(root) / "out" / piece.id
    out_dir.mkdir(parents=True, exist_ok=True)
    # 1-4: topic → research → write → gates, up to three topics (skipped when an accepted script already exists: resume)
    script = piece.script if (piece.script and piece.status in RESUMABLE) else None
    sheet, revise = None, None
    resume_write = piece.status == PARKED_WRITE and bool(piece.topic.get("sheet"))
    if resume_write:                                                   # the draft is cooking in Claude's batch lane: same topic, same sheet
        script, sheet, revise = None, piece.topic["sheet"], piece.topic.get("revise")
        piece.facts = sheet.get("facts", piece.facts)
    carried = piece.topic.pop("rewrite", None) if script is None else None
    if carried and (piece.topic.get("title") or piece.topic.get("long_scenes")):
        sheet = {"facts": piece.facts, "summary": ""}             # a video that came out too long: same topic, shorter script
        if piece.topic.get("long_scenes"):
            sheet.update(long_scenes=piece.topic["long_scenes"], hook=piece.topic.get("hook"))
        revise = carried
    for attempt in range(TOPIC_TRIES if script is None else 0):
        if resume_write and attempt == 0:
            pass                                                       # just collect (or re-ask for) the draft
        elif revise is None:                                           # a fresh topic (a length-only miss keeps the topic and asks for a trim)
            topic = _pick_topic(piece, deps, root, used)
            if not topic:
                pieces.save(pieces.transition(piece, "failed-topic", "no usable topic (for a mythology Short: its long is not made yet)"), root)
                return piece
            piece.topic = {**_jsonable(topic), "target_minutes": LONG_TARGET_MINUTES.get(piece.channel) if piece.kind == "long" else None}
            used.add(topic.get("link") or topic.get("id"))
            if topic.get("long_scenes"):
                piece.facts = topic["long_facts"]
                sheet = {"facts": piece.facts, "summary": "", "long_scenes": topic["long_scenes"], "hook": topic["hook"]}
            elif topic.get("remake_of"):                               # a past winner: its own sourced facts, no new research
                piece.facts = topic["remake_facts"]
                piece.topic.pop("remake_facts", None)
                sheet = {"facts": piece.facts, "summary": topic["remake_note"]}
            else:
                if not _allow(piece, "research", DAILY_RESEARCH):
                    pieces.save(pieces.transition(piece, "rejected", f"research budget used for today ({DAILY_RESEARCH} calls); the next quota day retries"), root)
                    return piece
                try:
                    sheet = deps.research(topic, piece.channel)
                except (research.ResearchError, gemini.GeminiError) as e:
                    pieces.save(pieces.transition(piece, "failed-research", f"try {attempt + 1}: {secrets.scrub(str(e))[:200]}"), root)
                    continue
                piece.facts = sheet.get("facts", [])
                if topic.get("extra") and topic.get("summary") and topic.get("link"):
                    # 31 Oct 2026: a chosen story's own brief (the Top 10's ten checked figures, a news item's reported numbers) is a
                    # reported source too; research verified only item 1, so the number check turned the Top 10 down three times
                    piece.facts = piece.facts + [{"text": str(topic["summary"]), "url": topic["link"], "label": "reported",
                                                  "date": str(topic.get("published", ""))[:10], "source": topic.get("source", "brief")}]
                if not piece.facts:
                    pieces.save(pieces.transition(piece, "failed-research", f"try {attempt + 1}: no sourced facts survived the checks"), root)
                    continue
            pieces.save(pieces.transition(piece, "researched"), root)
        else:
            piece.topic["revise"] = revise
        collecting = resume_write and attempt == 0 and bool(piece.ids.get("write_batch"))    # only ordering a draft counts, not checking on one
        if not collecting and not _allow(piece, "drafts", DAILY_DRAFTS):
            pieces.save(pieces.transition(piece, "rejected", f"draft budget used for today ({DAILY_DRAFTS} drafts); the next quota day retries"), root)
            return piece
        try:
            written = deps.write(piece, sheet, deps.library, deps.hashtags)
        except writer.WriterError as e:
            pieces.save(pieces.transition(piece, "failed-write", secrets.scrub(str(e))[:300]), root)
            return piece
        if written.get("state") == "writing":
            piece.topic["sheet"] = _jsonable(sheet)
            pieces.save(pieces.transition(piece, PARKED_WRITE, "draft cooking in Claude's batch lane; the next run collects it"), root)
            return piece
        piece.topic.pop("sheet", None)
        if written.get("note", "").startswith("claude failed"):
            piece.reasons.append(written["note"][:300])
        piece.script, piece.writer = written["script"], written["writer"]
        piece.topic.pop("revise", None)
        reasons = deps.lint(piece, prior)
        unmatched = deps.claims_check(piece)
        if unmatched:
            reasons.append("numbers without a source: " + ", ".join(f"{n:g}" for n in unmatched))
        if not reasons:
            script = piece.script
            break
        pieces.transition(piece, "rejected", f"try {attempt + 1}: " + "; ".join(reasons))
        pieces.save(piece, root)
        fixable = ("length", "label", "card", "hashtags", "disclaimer", "title", "threads", "instagram",
                   "numbers without a source", "hook", "opener", "send", "jargon")   # same topic: drop those numbers, rewrite the opening or the ending
        revise = "; ".join(reasons) if all(r.startswith(fixable) for r in reasons) else None      # formatting misses: same topic, trimmed draft
    if script is None:
        return piece
    pieces.save(pieces.transition(piece, "written"), root)
    if pack_mode:                                                  # Gemini presenter clips: stop here, send the pack, wait for the founder's clips
        from . import promptpack
        parts = (deps.pack or promptpack.write)(piece)
        piece.topic["pack"] = parts
        text = promptpack.render(piece, parts)
        (deps.pack_send or promptpack.send)(piece, text)
        if piece.status != "awaiting-clips":
            pieces.save(pieces.transition(piece, "awaiting-clips"), root)
        return piece
    # 5: voice
    lines = []
    voice_id = voice.pick(piece.id) if voice.pick else deps.voice_id
    piece.topic["voice"] = voice_id
    try:
        if deps.voice_batch:
            try:
                if deps.voice_batch(piece, [sc["vo"] for sc in script["scenes"]], voice_id) == "voicing":
                    pieces.save(pieces.transition(piece, "voicing", "voice job still running; the next run collects it"), root)
                    return piece
            except Exception as e:                       # the batch path is an optimisation: fall back to the synchronous lines
                print(f"voice batch unavailable ({secrets.scrub(str(e))[:120]}); voicing line by line", flush=True)
        if deps.voice_lines:
            lines = deps.voice_lines([sc["vo"] for sc in script["scenes"]], voice_id, out_dir / "vo")
        elif deps.voice_check:
            lines = voice.verified_lines([sc["vo"] for sc in script["scenes"]], voice_id, out_dir / "vo", say_fn=deps.say, transcribe_fn=deps.voice_check)
        else:
            for i, scene in enumerate(script["scenes"]):
                wav = out_dir / "vo" / f"vo{i:02d}.wav"
                lines.append((wav, deps.say(scene["vo"], voice_id, wav)))
    except voice.VoiceError as e:                            # the daily cap, a quota refusal or a dead key: keep the script, retry next run
        pieces.save(pieces.transition(piece, "failed-voice", str(e)), root)
        return piece
    pieces.save(pieces.transition(piece, "voiced"), root)
    # 6-7: pictures and cards (every panel and the thumbnail go out as one half-price batch job first; the per-scene calls then hit the cache)
    try:
        if deps.art_batch and is_story(piece) and not graphics(piece):
            try:
                if deps.art_batch(piece, picture_jobs(piece, deps)) == "painting":
                    pieces.save(pieces.transition(piece, "painting", "picture job still running; the next run collects it"), root)
                    return piece
            except art.ImageBudget:
                raise
            except Exception as e:                       # the batch path is an optimisation: paint one by one instead
                print(f"picture batch unavailable ({secrets.scrub(str(e))[:120]}); painting one by one", flush=True)
        visuals = [_visual_for(piece, i, sc, deps, out_dir, size, line=lines[i]) for i, sc in enumerate(script["scenes"])]
        strips = _source_strips(piece, deps, out_dir, size)
        chips = _label_chips(piece, deps, out_dir)
        credits = {i: deps.render_card("source", {"name": sc["credit"], "date": "photo"}, out_dir / f"credit-{i}.png", (size[0], 120))
                   for i, sc in enumerate(script["scenes"]) if sc.get("credit")}
        thumb = _thumb(piece, deps, out_dir)
    except art.ImageError as e:
        pieces.save(pieces.transition(piece, "failed-art", str(e)), root)
        return piece
    pieces.save(pieces.transition(piece, "drawn"), root)
    # 8: assemble
    from . import music
    bed = music.bed("calm" if piece.channel == "sglearning" else "epic", sum(d for _w, d in lines) + 5)
    if is_story(piece) and deps.story_build:
        video = deps.story_build(piece, lines, visuals, size, out_dir)
    else:
        video = deps.build(piece, lines, visuals, size, out_dir, music=bed, source_strips=strips, label_chips=chips, credits=credits)
    if piece.kind == "short":
        if assemble.story_copy(video, out_dir / "story.mp4") is None:          # founder, 22 Oct 2026: never trim; a Reel over 60 s simply has no Story
            piece.ids["ig_story_id"] = "skipped: Reel over 60 s"
        if script.get("carousel"):
            for j, card in enumerate(script.get("cards", []), start=1):
                deps.render_card("slide", card, out_dir / f"slide{j:02d}.jpg", (1080, 1350))
    pieces.save(pieces.transition(piece, "assembled"), root)
    # 9: QA
    from . import captions as _captions
    cues = []
    for (wav, d), start, sc in zip(lines, piece.timings, script["scenes"]):
        cues += _captions.offset(_captions.split(sc["vo"], d), start)
    target = (piece.topic.get("target_minutes") or 0) * 60 or None
    speech_end = (piece.timings[-1] + lines[-1][1]) if piece.timings and lines else None       # where the last narrated word should end
    problems = deps.qa(video, piece.kind, sum(d for _w, d in lines), cues, target_seconds=target, story=is_story(piece),
                       check_freeze=not is_story(piece), speech_end=speech_end)                 # a story panel's slow push-in is calm by design, not a frozen frame
    if problems:
        too_long = next((m for m in map(QA_TOO_LONG.match, problems) if m and float(m.group(1)) > float(m.group(2))), None)
        if too_long:                                                   # the same script and cached voice would fail again forever:
            dur, hi = float(too_long.group(1)), float(too_long.group(2))     # rewrite shorter, scaled to how fast this voice spoke
            words = sum(len(sc["vo"].split()) for sc in script["scenes"])
            lo_words = (story_words(piece.channel, piece.topic) if is_story(piece) else lint.SHORT_WORDS)[0]
            cap = max(lo_words, int(words * (hi * 0.9) / dur))
            piece.topic["rewrite"] = (f"length: the voiced video ran {dur:.0f}s, the limit is {hi:.0f}s; "
                                      f"rewrite the same story in at most {cap} words of voice in total")
            piece.script = None
        pieces.save(pieces.transition(piece, "qa_failed", "; ".join(problems)), root)
        return piece
    if dry_run:
        pieces.save(piece, root)
        return piece
    # 10: upload, scheduled
    piece.ids["yt_id"] = deps.upload(piece, video, thumb)
    piece.topic["look"] = art.look(piece.channel)                     # which picture style this piece was drawn in (weekly report)
    pieces.save(pieces.transition(piece, "uploaded"), root)
    if piece.kind == "long" and deps.subtitles:
        try:
            deps.subtitles(piece, out_dir, video)                    # caption tracks are a bonus: never fail an uploaded piece over them
        except Exception as e:
            print(f"subtitles skipped for {piece.id}: {secrets.scrub(str(e))[:200]}", flush=True)
        pieces.save(piece, root)
    return piece


def real_deps(root: Path = ROOT, env=None) -> Deps:
    """The production wiring."""
    banned, hashtags = lint.load_lists()
    library = claims.load_library()
    default_voice, _fallback = voice.voice_ids()

    def topic_fn(piece, used):
        if piece.channel == "sglearning":
            if piece.kind == "long":
                return topics.next_long_finance(root / "content", used)
            from datetime import datetime, timezone
            return topics.pick_finance(topics.fetch_all(), used, datetime.now(timezone.utc))
        return topics.next_myth(root / "content", used)

    def upload_fn(piece, video, thumb):
        import os
        token = youtube.access_token(piece.channel, env)
        when = slots.publish_at(piece.channel, piece.kind, piece.publish_day)
        if piece.topic.get("slot_ist"):                                   # an extra Reel (engine/extra.py): its own time, at least 10 minutes ahead
            from datetime import datetime as _dt, timedelta as _td, timezone as _tz
            when = max(slots.utc_for(piece.publish_day, piece.topic["slot_ist"]), _dt.now(_tz.utc) + _td(minutes=10))
        meta = youtube.metadata(piece, when, env or os.environ)
        vid = youtube.upload(token, video, meta)
        youtube.set_thumbnail(token, vid, thumb)
        from . import config as _cfg
        if (env or os.environ).get("UNLISTED_DAY1") == "1" or piece.kind in _cfg.UNLISTED_KINDS:
            piece.ids["unlisted"] = True
        return vid

    def subtitles_fn(piece, out_dir, video):
        import os
        from . import subtitles
        paths = subtitles.write_all(piece, out_dir, duration=qa.probe(video).get("duration"))
        subtitles.upload_all(youtube.access_token(piece.channel, env or os.environ), piece, paths)

    from . import writebatch
    return Deps(topic=topic_fn, research=lambda topic, ch: research.verify_urls(research.fact_sheet(topic, ch)),
                write=lambda piece, sheet, lib, tags: writer.write(piece, sheet, lib, tags, batch_fn=writebatch.write_piece), say=lambda *a, **k: voice.say(*a, plain=True, **k), paint=art.paint, avatar=art.avatar,
                render_card=cards.render, build=assemble.build, qa=qa.report, upload=upload_fn,
                lint=lambda piece, prior: (lint.check_script(piece, banned, prior) + lint.check_captions(piece, hashtags)
                                           + lint.check_opener(piece, recent_openers(root, piece)) + lint.check_send(piece)),
                claims_check=lambda piece: claims.match(lint.all_text(piece), piece.facts, library,
                                                        context=(piece.topic.get("title"), piece.topic.get("title_hi"))),
                commons=art.commons_photo, library=library, hashtags=hashtags, voice_id=default_voice,
                cartoon=cartoon.talking_head_clip, story_build=storyframe.build, cast_refs=cast.refs_for, subtitles=subtitles_fn,
                voice_batch=lambda piece, texts, vid: voicebatch.voice_piece(piece, texts, vid),
                art_batch=lambda piece, jobs: artbatch.paint_piece(piece, jobs), voice_check=voice.transcribe)
    # voice.batched (several scenes per TTS request) stays unwired: on 22 Oct 2026 the model's paragraph pauses were not distinct enough
    # to cut on, and the transcript check sent every group back to line-by-line. Wire it in once the cut is reliable.
