"""The founder's 10-second avatar intro in front of every Short and long (founder, 4 Nov 2026: test C, then "now this is superb, lets
continue like this also with long videos ... always").

The piece is written, voiced, painted and assembled as before. Before the upload, the hook, one bridge line and the fixed closing
"Aaiye isko samajhte hain." become the intro script (at most 26 words, so it fits 10 seconds), and the founder gets it on Telegram with
the avatar prompt (body language, lighting, a prop for the topic). The piece waits as "intro-wait". His clip comes back through the
Studio bot as inbox/intro/<piece id>.mp4, is checked (8-12 s, the words), composed in the piece's own frame (title band, captions, badge,
progress bar, a chart when the intro compares figures, the music bed under his voice) and joined to the body from scene 2 with a straight
cut; then the piece uploads. No clip 3 hours before the earliest slot: the plain piece uploads. Nothing ever misses its slot.

python -m engine.intro --plan <id>      print the intro script and prompt (nothing sent)
python -m engine.intro --needed         exit 0 when a waiting piece has its clip or passed its deadline (the Studio workflow then sweeps)
python -m engine.intro --sweep          collect clips, compose, upload; plain upload past the deadline
python -m engine.intro --redo <id>      an already-uploaded piece: compose with its clip, replace the YouTube video (same schedule)
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import captions, pieces, secrets, slots
from .config import CHANNELS, ROOT, VIDEO

CLOSING = "Aaiye isko samajhte hain."
MAX_WORDS = 26                              # about 10 seconds of calm Hinglish
BRIDGE_MAX_WORDS = 13
MIN_S, MAX_S = 8.0, 12.0                    # the clip the founder sends back
DEADLINE_HOURS = 3                          # before the earliest slot (Instagram or YouTube): then the plain piece uploads
MUSIC_LUFS = -26                            # the bed under the founder's voice: audible, below him (founder, 4 Nov 2026, preview 4)
VOICE_LUFS = -16
INBOX = Path("inbox") / "intro"
SILENCE_DB, SILENCE_S = -35, 0.2
SONNET = "claude-sonnet-5-5"

# a prop the avatar can have on the table, from the topic's words (the founder's clip shows the subject in the first second)
PROPS = [
    (("sip", "mutual fund", "fund house", "nav"), 'a phone face-up showing a bank SMS "SIP debited ₹5,000"'),
    (("gold", "sona", "dhanteras", "jewell"), "a small gold coin and a jewellery box"),
    (("fd", "fixed deposit", "bank", "savings", "interest", "byaaj"), "a bank passbook and a pen"),
    (("loan", "emi", "home loan", "car loan"), "a loan statement with the EMI amount circled"),
    (("tax", "regime", "80c", "salary", "ctc"), "a Form 16 and a calculator"),
    (("insurance", "claim", "hospital", "policy"), "a health insurance policy booklet"),
    (("petrol", "diesel", "fuel", "crude"), "a bike key and a fuel receipt"),
    (("job", "layoff", "hiring", "notice period", "appraisal"), "an office ID card on a lanyard"),
    (("upi", "fraud", "scam", "otp"), 'a phone showing a UPI "collect request" pop-up'),
    (("share", "stock", "dividend", "us stocks", "zerodha"), "a phone showing a stock app with one share's price"),
    (("credit card", "minimum due"), "a credit card statement with the minimum due highlighted"),
]
MYTH_PROP = "a printed photograph or old map of the place, held up to the camera for a moment"


def enabled(piece) -> bool:
    """Every painted Short and every long of both channels; never the code-card news, extra or Top 10 Reels."""
    t = {**((piece.topic or {}).get("preset") or {}), **(piece.topic or {})}
    cards = bool(t.get("graphics") or t.get("news") or t.get("extra") or t.get("roundup"))
    return piece.kind in ("short", "long") and piece.channel in CHANNELS and not cards and not re.search(r"-x\d+$|-news$", piece.id)


# ---------- the script and the prompt ----------
def _ask_claude(prompt: str) -> str:
    import anthropic
    client = anthropic.Anthropic(api_key=secrets.get("ANTHROPIC_API_KEY"))
    r = client.messages.create(model=SONNET, max_tokens=120, messages=[{"role": "user", "content": prompt}])
    try:
        from . import writer
        writer.record_spend(r.usage, writer.SPEND_FILE, None, factor=writer.SONNET_VS_OPUS)
    except Exception:
        pass
    return "".join(getattr(b, "text", "") for b in r.content).strip()


def bridge(piece, ask=_ask_claude) -> str:
    """One Hinglish line (at most 13 words) that states the tension behind the question, in everyday words; empty when it cannot be had."""
    script = piece.script or {}
    body = " ".join(sc.get("vo", "") for sc in script.get("scenes", [])[:5])
    prompt = (f"A Hindi/Hinglish money-or-history explainer for ordinary Indians opens with this question: \"{script.get('hook', '')}\"\n"
              f"The script that follows: {body[:900]}\n\nWrite ONE bridge line in Hinglish (Latin script) of at most {BRIDGE_MAX_WORDS} words that "
              f"states the tension or surprise behind the question, in words a 15-year-old knows, no numbers that are not in the script, "
              f"no English finance terms. It must flow naturally before the closing line \"{CLOSING}\". Output only the line.")
    try:
        line = ask(prompt).strip().strip('"').strip("'").split("\n")[0].strip()
    except Exception:
        return ""
    words = line.split()
    if not words or len(words) > BRIDGE_MAX_WORDS + 3:
        return ""
    return line if line[-1] in ".?!" else line + "."


def plan(piece, ask=_ask_claude) -> dict:
    """{"question", "bridge", "closing", "text", "words", "aspect", "prompt"}; the question is the piece's own hook, so the body never contradicts it."""
    script = piece.script or {}
    question = (script.get("hook") or (script.get("scenes") or [{}])[0].get("vo", "")).strip()
    b = bridge(piece, ask)
    text = " ".join(x for x in (question, b, CLOSING) if x)
    if len(text.split()) > MAX_WORDS:
        b, text = "", " ".join((question, CLOSING))
    aspect = "9:16" if piece.kind == "short" else "16:9"
    out = {"question": question, "bridge": b, "closing": CLOSING, "text": text, "words": len(text.split()), "aspect": aspect}
    out["prompt"] = prompt_for(piece, out)
    return out


def prop_for(piece) -> str:
    if piece.channel == "arthvan":
        return MYTH_PROP
    blob = " ".join([str((piece.script or {}).get("title", "")), str((piece.script or {}).get("hook", "")),
                     str((piece.topic or {}).get("title", "")), str((piece.topic or {}).get("summary", ""))]).lower()
    for keys, prop in PROPS:
        if any(k in blob for k in keys):
            return prop
    return "a phone face-up on the table showing a bank app"


def prompt_for(piece, p: dict) -> str:
    """The avatar prompt in the founder's format: setting, lighting, body language in three beats, prop, camera, watermark; no captions."""
    short = piece.kind == "short"
    size = "9:16 vertical, 1080x1920" if short else "16:9 landscape, 1920x1080"
    setting = ("a bright modern Indian living room in the morning, clean background with depth (plant, bookshelf, softly blurred)"
               if piece.channel == "sglearning" else
               "a study with a wooden bookshelf, old maps and a brass lamp, warm and calm, background softly blurred")
    return (f"{size}, exactly 10 seconds, natural and cinematic. Setting: {setting}. Lighting: soft window key light from the left on the "
            f"face, warm fill from the right, gentle rim light on the hair; no harsh shadows. SG [locked] seated at a wooden table, slightly "
            f"angled, leaning toward camera, navy blazer over white tee. Speaks from the first frame, mouth matched to the words, steady eye "
            f"contact with the lens. Body language in three beats: on the question, eyebrows lift and one open palm turns up; on the second "
            f"line, a slow nod and a half-smile, hand resting on the table; on \"{CLOSING}\", a small \"come with me\" gesture toward the viewer. "
            f"Prop: {prop_for(piece)}. Camera: eye level, slow push-in from mid-shot to medium close-up over the 10 seconds. No watermark, no "
            f"captions, no subtitles, no on-screen text of any kind (the channel badge and captions are added afterwards). "
            f"Export at {('1080x1920' if short else '1920x1080')}.")


def earliest_slot_utc(piece) -> datetime:
    """The first time the piece goes out anywhere: a Short's Instagram slot comes before its YouTube time."""
    yt = slots.publish_at(piece.channel, piece.kind, piece.publish_day)
    if piece.kind != "short":
        return yt
    ig = slots.utc_for(piece.publish_day, CHANNELS[piece.channel].ig_slot_ist)
    return min(yt, ig)


def deadline_utc(piece) -> datetime:
    return earliest_slot_utc(piece) - timedelta(hours=DEADLINE_HOURS)


def _wat(dt: datetime) -> str:
    return (dt + timedelta(hours=1)).strftime("%a %d %b %H:%M WAT")


def request_text(piece, p: dict) -> str:
    title = (piece.script or {}).get("title", "").replace("*", "")
    kind = "Short" if piece.kind == "short" else "long video"
    return (f"🎬 Intro for {piece.id} ({kind}: {title})\n\nSay exactly ({p['words']} words, ~10 s):\n\"{p['text']}\"\n\nPrompt:\n{p['prompt']}\n\n"
            f"Send the clip as a FILE (paperclip → File) with the caption:\nintro {piece.id}\n\nBy {_wat(deadline_utc(piece))}; after that the "
            f"plain version goes out at its slot.")


def clip_path(root: Path, piece) -> Path:
    return Path(root) / INBOX / f"{piece.id}.mp4"


# ---------- the clip ----------
def duration(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
                         capture_output=True, text=True, check=True).stdout.strip()
    return float(out or 0)


def speech_segments(path: Path, total: float | None = None) -> list:
    """[(start, end)] of speech, from the silences ffmpeg hears; the whole clip when nothing can be told."""
    total = total or duration(path)
    r = subprocess.run(["ffmpeg", "-v", "info", "-i", str(path), "-af", f"silencedetect=noise={SILENCE_DB}dB:d={SILENCE_S}", "-f", "null", "-"],
                       capture_output=True, text=True)
    starts = [float(x) for x in re.findall(r"silence_start: ([0-9.]+)", r.stderr)]
    ends = [float(x) for x in re.findall(r"silence_end: ([0-9.]+)", r.stderr)]
    silences = sorted(zip(starts, ends + [total] * (len(starts) - len(ends))))
    segs, t = [], 0.0
    for s, e in silences:
        if s - t > 0.15:
            segs.append((round(t, 3), round(s, 3)))
        t = e
    if total - t > 0.15:
        segs.append((round(t, 3), round(total, 3)))
    return segs or [(0.0, total)]


def check(clip: Path, p: dict, transcribe=None, seconds: float | None = None) -> list:
    """Empty = usable. Reasons: wrong length, missing words (the founder's own transcription check), no closing line."""
    from . import inbox
    reasons = []
    secs = duration(clip) if seconds is None else seconds
    if not MIN_S <= secs <= MAX_S:
        reasons.append(f"the clip runs {secs:.1f} s; it should be 8-12 s")
    try:
        heard = (transcribe or inbox.transcribe)(clip)
    except Exception as e:
        return reasons + [f"transcription failed: {type(e).__name__}"]
    sim = inbox.similarity(p["text"], heard)
    if sim < inbox.SIMILARITY_MIN:
        reasons.append(f"missing words (only {sim:.0%} of the script heard): \"{heard[:120]}\"")
    if "samajh" not in heard.lower() and "samjh" not in heard.lower():
        reasons.append("the closing line \"Aaiye isko samajhte hain\" was not heard")
    return reasons


def cues_for(text: str, segments: list, total: float) -> list:
    """Captions on the spoken phrases: one per speech segment when the counts match, else the body's syllable split over the speech span.
    Each caption holds until the next begins, the last until the clip ends."""
    phrases = captions._phrases(text.strip())
    if len(phrases) == len(segments):
        cues = []
        for i, (ph, (s, _e)) in enumerate(zip(phrases, segments)):
            end = segments[i + 1][0] if i + 1 < len(segments) else total
            cues.append((round(max(0.0, s - 0.05), 3), round(end, 3), ph))
        return cues
    start, end = segments[0][0], segments[-1][1]
    cues = captions.offset(captions.split(text, max(0.5, end - start)), max(0.0, start - 0.05))
    cues = [(s, (cues[i + 1][0] if i + 1 < len(cues) else total), t) for i, (s, _e, t) in enumerate(cues)]
    merged = []                                                    # a one-word tail ("hai?") joins the phrase before it: never a 0.2 s caption
    for s, e, t in cues:
        if merged and (len(t.split()) == 1 or e - s < 0.5):
            ps, _pe, pt = merged[-1]
            merged[-1] = (ps, e, f"{pt} {t}")
        else:
            merged.append((s, e, t))
    return merged


def _run(args: list) -> None:
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


def compose(piece, clip: Path, out_dir: Path, size: tuple | None = None) -> Path:
    """The founder's clip in the piece's own frame, then the body from scene 2, a straight cut. Replaces out/<id>/reel.mp4 (long.mp4),
    keeps the plain file as reel-plain.mp4, refreshes story.mp4 and the Instagram cover (his face with the title band)."""
    from . import assemble, cards, layers, music, storyframe
    out_dir = Path(out_dir)
    p = (piece.topic or {}).get("intro") or plan(piece, ask=lambda _p: "")
    short = piece.kind == "short"
    size = size or VIDEO["short" if short else "long"]
    w, h = size
    secs = duration(clip)
    band_h = int(h * storyframe.TOP)
    title_png = out_dir / "title.png"
    if not title_png.exists():
        title = (piece.script or {}).get("title") or (piece.script or {}).get("hook", "")
        cards.render("storytitle", {"title_html": storyframe.title_html(title), **storyframe.brand(piece.channel),
                                    "pad": storyframe.TITLE_PAD_SHORT if short else 60, "strip": "none" if short else "flex"}, title_png, (w, band_h))
    shade = None
    if short:
        shade = out_dir / "shade.png"
        if not shade.exists():
            cards.render("storyshade", {}, shade, (w, storyframe.SHADE_H + storyframe.LIFT))
    bottom_y = h - storyframe.CAP_H - storyframe.LIFT if short else h - band_h
    keyword = (re.search(r"\*(.+?)\*", (piece.script or {}).get("title", "")) or [None, ""])[1]
    overlays = []
    for k, (s, e, text) in enumerate(cues_for(p["text"], speech_segments(clip, secs), secs)):
        png = out_dir / "cues" / f"intro-{k:02d}.png"
        png.parent.mkdir(parents=True, exist_ok=True)
        if short:
            cards.render("storycap2", {"text_html": storyframe.caption_html(text, keyword)}, png, (w, storyframe.CAP_H))
        else:
            cards.render("storycap", {"text": text}, png, (w, band_h))
        overlays.append((png, 0, bottom_y, s, e))
    if short:                                                       # the first 10 seconds carry graphics too (founder, 4 Nov 2026)
        n = len((piece.script or {}).get("scenes") or []) + 1
        overlays += layers.scene_overlays(p["text"], 0, n, size, out_dir / "layers", top=band_h, side=storyframe.SAFE_SIDE,
                                          chart_y=band_h + 230, dur=secs)
    video = storyframe.scene(clip, secs, size, out_dir / "intro-video.mp4", title_png, overlays, logo_png=storyframe.logo(piece.channel),
                             watermark_png=storyframe.logo(piece.channel, 600), punch=False, shade_png=shade)
    # audio in separate passes: loudnorm buffers about 3 s, and a mixer that stops at the first input's end lost the last line (4 Nov 2026)
    voice = out_dir / "intro-voice.wav"
    _run(["-i", str(clip), "-vn", "-af", f"aresample=48000,aformat=channel_layouts=stereo,loudnorm=I={VOICE_LUFS}:TP=-1.5:LRA=11,aresample=48000",
          "-c:a", "pcm_s16le", str(voice)])
    bed = out_dir / "intro-music.wav"
    _run(["-i", str(music.bed("light", secs + 5)), "-af", f"aresample=48000,aformat=channel_layouts=stereo,loudnorm=I={MUSIC_LUFS}:TP=-6:LRA=7,"
          f"aresample=48000,atrim=0:{secs:.3f}", "-c:a", "pcm_s16le", str(bed)])
    mixed = out_dir / "intro-audio.wav"
    _run(["-i", str(voice), "-i", str(bed), "-filter_complex", "[0:a][1:a]amix=inputs=2:duration=first:normalize=0[a]", "-map", "[a]",
          "-c:a", "pcm_s16le", str(mixed)])
    if abs(duration(mixed) - secs) > 0.3:
        raise RuntimeError(f"intro audio is {duration(mixed):.2f} s for a {secs:.2f} s clip")
    part_a = out_dir / "intro-part.mp4"
    _run(["-i", str(video), "-i", str(mixed), "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-shortest", str(part_a)])
    plain = out_dir / ("reel.mp4" if short else "long.mp4")
    keep = out_dir / ("reel-plain.mp4" if short else "long-plain.mp4")
    if not keep.exists():
        shutil.copy2(plain, keep)
    cut = piece.timings[1] if len(piece.timings) > 1 else 0.0
    part_b = out_dir / "intro-body.mp4"
    _run(["-ss", f"{cut:.3f}", "-i", str(keep), "-vf", f"scale={w}:{h},setsar=1,fps={VIDEO['fps']},format=yuv420p",
          "-af", "aresample=48000,aformat=channel_layouts=stereo", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", "-b:a", "160k", str(part_b)])
    va = duration(part_a)
    _run(["-i", str(part_a), "-i", str(part_b), "-filter_complex",
          f"[0:v]setsar=1[v0];[1:v]setsar=1[v1];[0:a]atrim=0:{va:.3f},asetpts=PTS-STARTPTS[a0];[v0][a0][v1][1:a]concat=n=2:v=1:a=1[v][a]",
          "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", "-b:a", "160k", "-ar", "48000",
          "-movflags", "+faststart", str(plain)])
    if short:
        assemble.story_copy(plain, out_dir / "story.mp4")
    _run(["-ss", "1.0", "-i", str(plain), "-frames:v", "1", "-q:v", "2", str(out_dir / "cover.jpg")])
    piece.ids["intro"] = {"clip": str(Path(clip).name), "seconds": round(secs, 2), "composed": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    return plain


# ---------- the wait, the collection, the sweep ----------
def request(piece, root: Path, notify, ask=_ask_claude, now: datetime | None = None) -> dict:
    """Plans the intro once and sends it to the founder once; returns the plan."""
    if not (piece.topic or {}).get("intro"):
        piece.topic["intro"] = plan(piece, ask)
    if not piece.ids.get("intro_sent"):
        notify(request_text(piece, piece.topic["intro"]))
        piece.ids["intro_sent"] = (now or datetime.now(timezone.utc)).isoformat(timespec="seconds")
    return piece.topic["intro"]


def _sha(path: Path) -> str:
    import hashlib
    return hashlib.sha1(Path(path).read_bytes()).hexdigest()[:16]


def collect(piece, deps, root: Path, now: datetime | None = None, notify=None, transcribe=None, compose_fn=None) -> tuple:
    """One waiting piece: ("uploaded-intro" | "uploaded-plain" | "waiting" | "rejected", piece)."""
    from . import pipeline
    now = now or datetime.now(timezone.utc)
    notify = notify or (lambda t: None)
    out_dir = Path(root) / "out" / piece.id
    video = out_dir / ("reel.mp4" if piece.kind == "short" else "long.mp4")
    thumb = out_dir / "thumb.jpg"
    clip = clip_path(root, piece)
    p = (piece.topic or {}).get("intro") or {}
    if clip.exists() and _sha(clip) != piece.ids.get("intro_rejected"):
        problems = check(clip, p, transcribe)
        if problems:
            piece.ids["intro_rejected"] = _sha(clip)
            notify(f"🎬 {piece.id}: the intro clip was not used: " + "; ".join(problems) + f". Send a new one with the caption intro {piece.id}"
                   + ("" if now < deadline_utc(piece) else "; the plain version goes out now."))
            pieces.save(piece, root)
            if now < deadline_utc(piece):
                return "rejected", piece
        else:
            (compose_fn or compose)(piece, clip, out_dir)
            pipeline.finish_upload(piece, deps, root, video, thumb, out_dir)
            notify(f"🎬 {piece.id}: your intro is merged and the piece is scheduled for its slot.")
            return "uploaded-intro", piece
    if now >= deadline_utc(piece):
        piece.ids["intro_skipped"] = now.isoformat(timespec="seconds")
        pipeline.finish_upload(piece, deps, root, video, thumb, out_dir)
        notify(f"🎬 {piece.id}: no intro clip by {_wat(deadline_utc(piece))}; the plain version is scheduled for its slot.")
        return "uploaded-plain", piece
    return "waiting", piece


def waiting(root: Path) -> list:
    return sorted((p for p in pieces.list_all(root) if p.status == "intro-wait"), key=lambda p: p.publish_day)


def needed(root: Path, now: datetime | None = None) -> bool:
    """Cheap: does a waiting piece have a fresh clip, or has one passed its deadline?"""
    now = now or datetime.now(timezone.utc)
    for p in waiting(root):
        clip = clip_path(root, p)
        if (clip.exists() and _sha(clip) != p.ids.get("intro_rejected")) or now >= deadline_utc(p):
            return True
    return False


def sweep(root: Path, deps, now: datetime | None = None, notify=None, transcribe=None, compose_fn=None) -> list:
    out = []
    for p in waiting(root):
        try:
            action, p = collect(p, deps, root, now, notify, transcribe, compose_fn)
        except Exception as e:
            action = f"failed: {type(e).__name__}: {secrets.scrub(str(e))[:160]}"
            (notify or print)(f"🎬 {p.id}: intro step failed ({action}); it stays waiting, the plain version goes out at the deadline.")
        out.append((p.id, action))
    return out


def redo(piece_id: str, root: Path = ROOT, env=None, deps=None, notify=None) -> str:
    """An already-uploaded piece gets its intro: compose with the clip in the inbox, delete the scheduled YouTube video, upload the new one."""
    from . import pipeline, youtube
    piece = pieces.load(piece_id, root)
    if piece is None:
        return f"{piece_id}: no such piece"
    clip = clip_path(root, piece)
    if not clip.exists():
        return f"{piece_id}: no clip at {clip}"
    deps = deps or pipeline.real_deps(root, env)
    if not (piece.topic or {}).get("intro"):
        piece.topic["intro"] = plan(piece, ask=lambda _p: "")
    problems = check(clip, piece.topic["intro"])
    if problems:
        return f"{piece_id}: clip not used: " + "; ".join(problems)
    out_dir = Path(root) / "out" / piece.id
    compose(piece, clip, out_dir)
    old = piece.ids.get("yt_id")
    if old:
        youtube.delete(youtube.access_token(piece.channel, env), old)
        piece.ids["yt_id_replaced"] = old
    video = out_dir / ("reel.mp4" if piece.kind == "short" else "long.mp4")
    piece.ids["yt_id"] = deps.upload(piece, video, out_dir / "thumb.jpg")
    pieces.save(piece, root)
    msg = f"🎬 {piece.id}: intro merged and re-uploaded for its slot (YouTube {piece.ids['yt_id']}, replaced {old or 'nothing'})."
    (notify or print)(msg)
    return msg


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan"); ap.add_argument("--needed", action="store_true"); ap.add_argument("--sweep", action="store_true"); ap.add_argument("--redo")
    a = ap.parse_args(argv)
    if a.plan:
        piece = pieces.load(a.plan, ROOT)
        p = plan(piece)
        print(request_text(piece, p)); return 0
    if a.needed:
        ok = needed(ROOT); print("sweep needed" if ok else "nothing to do"); return 0 if ok else 3
    if a.sweep:
        from . import pipeline, telegram
        for pid, action in sweep(ROOT, pipeline.real_deps(ROOT), notify=telegram.send):
            print(f"{pid}: {action}")
        return 0
    if a.redo:
        from . import telegram
        print(redo(a.redo, ROOT, notify=telegram.send)); return 0
    ap.print_help(); return 2


if __name__ == "__main__":
    sys.exit(main())
