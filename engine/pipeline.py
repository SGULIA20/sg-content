"""One piece from topic to scheduled upload, every step behind an injectable function (spec §3 steps 1-10, §7)."""
import json
import shutil
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Callable

from . import art, assemble, buffer, cards, claims, gemini, lint, pieces, qa, research, secrets, slots, topics, voice, writer, youtube
from .config import CHANNELS, ROOT, VIDEO
from .pieces import Piece

TOPIC_TRIES = 3
RESUMABLE = {"written", "voiced", "drawn", "assembled", "failed-voice", "failed-art", "qa_failed"}
HANDLE = "@sanjeev_gulia"
LONG_TARGET_MINUTES = {"sglearning": 15, "arthvan": 20}


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


def _pick_topic(piece: Piece, deps: Deps, root: Path, used: set) -> dict | None:
    if piece.channel == "arthvan" and piece.kind == "short":
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


def _visual_for(piece: Piece, i: int, scene: dict, deps: Deps, out_dir: Path, size: tuple) -> Path:
    v = scene.get("visual") or {}
    kind = v.get("type", "art")
    out = out_dir / f"visual{i:02d}.png"
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


def _thumb(piece: Piece, deps: Deps, out_dir: Path) -> Path:
    title = piece.script["captions"]["youtube"]["title"]
    words = [w for w in title.replace("?", "? ").split() if w][:4]
    number = next((c["big_number"] for c in piece.script.get("cards", []) if c.get("big_number")), "")
    return deps.render_card("thumb", {"words": words[:3], "number": number, "avatar_path": deps.avatar("surprised")}, out_dir / "thumb.jpg", (1280, 720))


def make(piece: Piece, deps: Deps, root: Path = ROOT, dry_run: bool = False) -> Piece:
    """Runs the pipeline for one piece and records every transition. Returns the piece in its final state for this run."""
    if piece.status in buffer.DONE:
        return piece
    used, prior = _used(root)
    size = VIDEO[piece.kind]
    out_dir = Path(root) / "out" / piece.id
    out_dir.mkdir(parents=True, exist_ok=True)
    # 1-4: topic → research → write → gates, up to three topics (skipped when an accepted script already exists: resume)
    script = piece.script if (piece.script and piece.status in RESUMABLE) else None
    for attempt in range(TOPIC_TRIES if script is None else 0):
        topic = _pick_topic(piece, deps, root, used)
        if not topic:
            pieces.save(pieces.transition(piece, "failed-topic", "no usable topic (for a mythology Short: its long is not made yet)"), root)
            return piece
        piece.topic = {**_jsonable(topic), "target_minutes": LONG_TARGET_MINUTES.get(piece.channel) if piece.kind == "long" else None}
        used.add(topic.get("link") or topic.get("id"))
        if topic.get("long_scenes"):
            piece.facts = topic["long_facts"]
            sheet = {"facts": piece.facts, "summary": "", "long_scenes": topic["long_scenes"], "hook": topic["hook"]}
        else:
            try:
                sheet = deps.research(topic, piece.channel)
            except (research.ResearchError, gemini.GeminiError) as e:
                pieces.save(pieces.transition(piece, "failed-research", f"try {attempt + 1}: {secrets.scrub(str(e))[:200]}"), root)
                continue
            piece.facts = sheet.get("facts", [])
            if not piece.facts:
                pieces.save(pieces.transition(piece, "failed-research", f"try {attempt + 1}: no sourced facts survived the checks"), root)
                continue
        pieces.save(pieces.transition(piece, "researched"), root)
        written = deps.write(piece, sheet, deps.library, deps.hashtags)
        piece.script, piece.writer = written["script"], written["writer"]
        reasons = deps.lint(piece, prior)
        unmatched = deps.claims_check(piece)
        if unmatched:
            reasons.append("numbers without a source: " + ", ".join(f"{n:g}" for n in unmatched))
        if not reasons:
            script = piece.script
            break
        pieces.transition(piece, "rejected", f"try {attempt + 1}: " + "; ".join(reasons))
        pieces.save(piece, root)
    if script is None:
        return piece
    pieces.save(pieces.transition(piece, "written"), root)
    # 5: voice
    lines = []
    try:
        for i, scene in enumerate(script["scenes"]):
            wav = out_dir / "vo" / f"vo{i:02d}.wav"
            lines.append((wav, deps.say(scene["vo"], deps.voice_id, wav)))
    except voice.VoiceError as e:                            # the daily cap, a quota refusal or a dead key: keep the script, retry next run
        pieces.save(pieces.transition(piece, "failed-voice", str(e)), root)
        return piece
    pieces.save(pieces.transition(piece, "voiced"), root)
    # 6-7: pictures and cards
    try:
        visuals = [_visual_for(piece, i, sc, deps, out_dir, size) for i, sc in enumerate(script["scenes"])]
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
    video = deps.build(piece, lines, visuals, size, out_dir, music=bed, source_strips=strips, label_chips=chips, credits=credits)
    if piece.kind == "short":
        shutil.copy(video, out_dir / "story.mp4")
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
    problems = deps.qa(video, piece.kind, sum(d for _w, d in lines), cues, target_seconds=target)
    if problems:
        pieces.save(pieces.transition(piece, "qa_failed", "; ".join(problems)), root)
        return piece
    if dry_run:
        pieces.save(piece, root)
        return piece
    # 10: upload, scheduled
    piece.ids["yt_id"] = deps.upload(piece, video, thumb)
    pieces.save(pieces.transition(piece, "uploaded"), root)
    return piece


def real_deps(root: Path = ROOT, env=None) -> Deps:
    """The production wiring."""
    banned, hashtags = lint.load_lists()
    library = claims.load_library()
    default_voice, _fallback = voice.voice_ids()

    def topic_fn(piece, used):
        if piece.channel == "sglearning":
            from datetime import datetime, timezone
            return topics.pick_finance(topics.fetch_all(), used, datetime.now(timezone.utc))
        return topics.next_myth(root / "content", used)

    def upload_fn(piece, video, thumb):
        import os
        token = youtube.access_token(piece.channel, env)
        meta = youtube.metadata(piece, slots.publish_at(piece.channel, piece.kind, piece.publish_day), env or os.environ)
        vid = youtube.upload(token, video, meta)
        youtube.set_thumbnail(token, vid, thumb)
        if (env or os.environ).get("UNLISTED_DAY1") == "1":
            piece.ids["unlisted"] = True
        return vid

    return Deps(topic=topic_fn, research=lambda topic, ch: research.verify_urls(research.fact_sheet(topic, ch)), write=writer.write, say=voice.say, paint=art.paint, avatar=art.avatar,
                render_card=cards.render, build=assemble.build, qa=qa.report, upload=upload_fn,
                lint=lambda piece, prior: lint.check_script(piece, banned, prior) + lint.check_captions(piece, hashtags),
                claims_check=lambda piece: claims.match(lint.all_text(piece), piece.facts, library),
                commons=art.commons_photo, library=library, hashtags=hashtags, voice_id=default_voice)
