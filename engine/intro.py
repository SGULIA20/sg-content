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
python -m engine.intro --ask-scheduled  send the intro request for already-scheduled pieces due within 3 days (the produce run does this)
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
CLOSINGS = ["Chaliye, poori baat samajhte hain.",                   # founder, 4 Nov 2026: the same closing on every Reel wears out; rotate
            "Aaiye, iske peeche ki kahani dekhte hain.",            # the wording, keep the purpose (come, let us understand this)
            "Chaliye, isko detail mein dekhte hain.",
            "Aaiye, sach jaante hain.",
            "Chaliye, is sawal ka jawab dhoondte hain.",
            "Aaiye, poora khel samajhte hain.",
            "Chaliye, shuru se dekhte hain.",
            CLOSING]


def closing_for(piece) -> str:
    return _pick(piece, CLOSINGS, 5)
MAX_WORDS = 26                              # about 10 seconds of calm Hinglish
BRIDGE_MAX_WORDS = 13
MIN_S, MAX_S = 8.0, 12.0                    # the clip the founder sends back
DEADLINE_HOURS = 3                          # before the earliest slot (Instagram or YouTube): then the plain piece uploads
MUSIC_LUFS = -26                            # the bed under the founder's voice: audible, below him (founder, 4 Nov 2026, preview 4)
TAIL_S = 0.35                               # after his last word the body starts (founder, 4 Nov 2026: "trim the 1-2 second pause at the end")
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
              f"no English finance terms. It must flow naturally before the closing line \"{closing_for(piece)}\". Output only the line.")
    try:
        line = ask(prompt).strip().strip('"').strip("'").split("\n")[0].strip()
    except Exception as e:
        print(f"intro bridge: no line from Claude ({type(e).__name__}: {secrets.scrub(str(e))[:120]}); question and closing only", flush=True)
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
    closing = closing_for(piece)
    text = " ".join(x for x in (question, b, closing) if x)
    if len(text.split()) > MAX_WORDS:                                 # over 10 seconds: a shorter closing first, the bridge goes last
        closing = _pick(piece, [c for c in CLOSINGS if len(c.split()) <= 4], 5)
        text = " ".join(x for x in (question, b, closing) if x)
    if len(text.split()) > MAX_WORDS:
        b, text = "", " ".join((question, closing))
    aspect = "9:16" if piece.kind == "short" else "16:9"
    out = {"question": question, "bridge": b, "closing": closing, "text": text, "words": len(text.split()), "aspect": aspect}
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


# Every Reel looks different (founder, 4 Nov 2026: "founder should change his clothes, position should move, walk or change background
# in every reel; all can't be the same"): the setting, outfit, pose and camera move rotate with the piece, so two days never repeat.
SETTINGS = {
    "sglearning": [
        "a bright modern Indian living room in the morning, clean background with depth (plant, bookshelf, softly blurred)",
        "a kitchen counter with a steel chai glass and a steaming kettle, warm morning light through the window",
        "a home office with a laptop, a desk lamp and a wall calendar, late-afternoon light",
        "the balcony of a city flat, railing and potted plants, soft overcast daylight, the street blurred below",
        "a bank branch waiting area, blue chairs and a token display, clean fluorescent light softened",
        "a quiet street outside a vegetable market, stalls and baskets blurred behind, golden evening light",
        "a metro station platform before the train, clean steel and glass, cool daylight",
    ],
    "arthvan": [
        "a study with a wooden bookshelf, old maps and a brass lamp, warm and calm, background softly blurred",
        "the stone corridor of an old temple, carved pillars receding, warm sunlight slanting in",
        "a museum gallery with a sandstone sculpture behind glass, dim gallery light, one spotlight",
        "the ramparts of a hill fort at dawn, mist in the valley, soft golden light",
        "a riverbank ghat at sunrise, steps and a temple spire behind, mist on the water",
        "an archaeological dig site with string grids and a tent, bright even daylight",
        "an old library reading room with tall shelves and a ladder, dust in a beam of light",
    ],
}
OUTFITS = ["navy blazer over white tee", "a plain charcoal kurta", "a light blue linen shirt, sleeves rolled", "a maroon sweater over a white collar",
           "a black polo", "a cream Nehru jacket over a white shirt", "a grey half-sleeve shirt, top button open"]
POSES = ["seated at a wooden table, slightly angled, leaning toward camera, hands resting on the table",
         "standing, turned a little to the side, weight on one foot, one hand in a pocket",
         "walking slowly toward the camera, the camera tracking back at the same pace, one small hand gesture per line",
         "leaning against a counter or railing, relaxed, arms loosely folded then opening on the question",
         "seated on a stool, elbows on knees, leaning in, close and conversational"]
CAMERAS = ["eye level, slow push-in from mid-shot to medium close-up over the 10 seconds",
           "eye level, a slow lateral slide from left to right, the subject kept centred",
           "a slow pull-back from close-up to mid-shot as he finishes the question, then steady",
           "handheld feel, slight natural movement, medium close-up throughout",
           "low angle, slightly below eye level, slow push-in"]
BEATS = ["on the question, eyebrows lift and one open palm turns up; on the second line, a slow nod and a half-smile; on \"{closing}\", a small \"come with me\" gesture toward the viewer",
         "on the question, a small head tilt and a raised finger; on the second line, both hands open, palms down, settling; on \"{closing}\", a nod and a step closer",
         "on the question, a light shrug with open hands; on the second line, counting one point on a finger; on \"{closing}\", a hand inviting the viewer in",
         "on the question, a direct look with a half-smile; on the second line, a slow nod, hand on chest; on \"{closing}\", a wave of the hand toward the lens"]


def _pick(piece, options: list, salt: int = 0):
    """A steady, different choice per piece: the day number and channel decide, so consecutive days never repeat an option."""
    n = piece.publish_day.toordinal() + salt + (0 if piece.channel == "sglearning" else 3) + (0 if piece.kind == "short" else 4)
    return options[n % len(options)]


def prompt_for(piece, p: dict) -> str:
    """The avatar prompt in the founder's format: setting, lighting, body language in three beats, prop, camera, watermark; no captions.
    Setting, outfit, pose, camera and beats rotate per piece."""
    short = piece.kind == "short"
    size = "9:16 vertical, 1080x1920" if short else "16:9 landscape, 1920x1080"
    handle = "@SGLearning" if piece.channel == "sglearning" else "@SGMythWorld"
    setting = _pick(piece, SETTINGS[piece.channel])
    outfit = _pick(piece, OUTFITS, 1)
    pose = _pick(piece, POSES, 2)
    camera = _pick(piece, CAMERAS, 3)
    beats = _pick(piece, BEATS, 4).format(closing=(p.get("closing") or CLOSING).rstrip("."))
    return (f"{size}, exactly 10 seconds, natural and cinematic. Setting: {setting}. Lighting: soft key light on the face from one side, "
            f"warm fill from the other, gentle rim light on the hair; no harsh shadows. SG [locked] {pose}, wearing {outfit}. Speaks from "
            f"the first frame, mouth matched to the words, steady eye contact with the lens. Body language in three beats: {beats}. "
            f"Prop: {prop_for(piece)}. Camera: {camera}. {handle} watermark top right, white, bold, 80% opacity. No captions, no subtitles, "
            f"no other on-screen text. Export at {('1080x1920' if short else '1920x1080')}.")


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
    sim = recall(p["text"], heard)                                     # the script's words heard; extra words of his are fine
    if sim < inbox.SIMILARITY_MIN:
        reasons.append(f"missing words (only {sim:.0%} of the script heard): \"{heard[:120]}\"")
    closing = p.get("closing") or CLOSING
    if recall(closing, heard) < 0.5 and "samajh" not in heard.lower() and "samjh" not in heard.lower():
        reasons.append(f"the closing line \"{closing}\" was not heard")
    return reasons


def recall(script: str, heard: str) -> float:
    """How much of the script was heard (4 Nov 2026: Jaccard punished a clip that said the script plus a bridge line the plan lacked)."""
    from . import inbox
    want, got = set(inbox._tokens(script)), set(inbox._tokens(heard))
    return len(want & got) / len(want) if want else 0.0


def _phrases(text: str) -> list:
    """The body's phrase split, with a one-word tail ("hai?") joined to the phrase before it: never a caption of its own."""
    out = []
    for ph in captions._phrases(text.strip()):
        if out and len(ph.split()) == 1:
            out[-1] = f"{out[-1]} {ph}"
        else:
            out.append(ph)
    return out


def cues_for(text: str, segments: list, total: float) -> list:
    """Captions on the spoken phrases. One phrase per speech segment when the counts match; otherwise the phrases are dealt to the
    segments in order by their share of syllables against each segment's share of speech time (4 Nov 2026: the bridge segment once
    showed "hai?" on its own). Each caption holds until the next begins, the last until the clip ends."""
    phrases = _phrases(text)
    if not phrases or not segments:
        return []
    weights = [max(1, sum(captions.syllables(w) for w in ph.split())) for ph in phrases]
    if len(phrases) == len(segments):
        groups = [[i] for i in range(len(phrases))]
    else:                                                          # each phrase goes to the segment whose share of the speech time holds the
        speech = sum(e - s for s, e in segments) or 1.0            # phrase's share of the syllables (its midpoint), never moving backwards
        ends, acc = [], 0.0
        for s, e in segments:
            acc += (e - s) / speech
            ends.append(acc)
        groups, k, cum, total_w = [[] for _ in segments], 0, 0.0, float(sum(weights))
        for i, w in enumerate(weights):
            mid = (cum + w / 2) / total_w
            cum += w
            while k < len(segments) - 1 and mid > ends[k]:
                k += 1
            groups[k].append(i)
        last = len(phrases) - 1                                    # the closing line is always on the last segment, the question on the first
        if last not in groups[-1]:
            for g in groups:
                if last in g:
                    g.remove(last)
            groups[-1].append(last)
        if 0 not in groups[0]:
            for g in groups:
                if 0 in g:
                    g.remove(0)
            groups[0].insert(0, 0)
    cues = []
    for k, (seg, idx) in enumerate(zip(segments, groups)):
        if not idx:
            continue
        s0 = max(0.0, seg[0] - 0.05)
        seg_end = segments[k + 1][0] if k + 1 < len(segments) else total
        inner = seg[1] - seg[0]
        w_sum = sum(weights[i] for i in idx)
        t = s0
        for n, i in enumerate(idx):
            if n == len(idx) - 1:
                e = seg_end
            else:
                e = round(t + inner * weights[i] / w_sum, 3)
            cues.append((round(t, 3), round(e, 3), phrases[i]))
            t = e
    return cues


def _run(args: list) -> None:
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


def _norm_words(text: str) -> list:
    return re.findall(r"[a-z0-9]+", str(text).lower())


def body_cut(piece, out_dir: Path) -> float:
    """Where the body starts after the founder's intro. A Short: scene 2 (scene 1 is the hook). A long: right after the hook sentence,
    read from the caption timings, since its first scene carries the set-up too (4 Nov 2026, the Tanjore long: cutting the whole
    22-second scene made the video "start from between"). When the hook cannot be placed, a long starts from 0 (the hook is heard twice)."""
    if piece.kind == "short":
        return piece.timings[1] if len(piece.timings) > 1 else 0.0
    hook = _norm_words((piece.script or {}).get("hook", ""))
    ass = Path(out_dir) / "captions.ass"
    if not hook or not ass.exists():
        return 0.0
    heard = []
    for line in ass.read_text(errors="replace").splitlines():
        if not line.startswith("Dialogue:"):
            continue
        parts = line.split(",", 9)
        if len(parts) < 10:
            continue
        heard += _norm_words(parts[9])
        if len(heard) >= len(hook):
            if heard[:len(hook)] == hook:
                h, m, sec = parts[2].split(":")
                return round(int(h) * 3600 + int(m) * 60 + float(sec), 3)
            return 0.0
    return 0.0


def compose(piece, clip: Path, out_dir: Path, size: tuple | None = None) -> Path:
    """The founder's clip in the piece's own frame, then the body from scene 2, a straight cut. Replaces out/<id>/reel.mp4 (long.mp4),
    keeps the plain file as reel-plain.mp4, refreshes story.mp4 and the Instagram cover (his face with the title band)."""
    from . import assemble, cards, layers, music, storyframe
    out_dir = Path(out_dir)
    p = (piece.topic or {}).get("intro") or plan(piece, ask=lambda _p: "")
    short = piece.kind == "short"
    size = size or VIDEO["short" if short else "long"]
    w, h = size
    full = duration(clip)
    segments = speech_segments(clip, full)
    secs = round(min(full, segments[-1][1] + TAIL_S), 3)         # the silent tail after the last word is cut; the body starts at once
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
    for k, (s, e, text) in enumerate(cues_for(p["text"], segments, secs)):
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
    _run(["-t", f"{secs:.3f}", "-i", str(clip), "-vn", "-af", f"aresample=48000,aformat=channel_layouts=stereo,loudnorm=I={VOICE_LUFS}:TP=-1.5:LRA=11,aresample=48000",
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
    cut = body_cut(piece, out_dir)
    part_b = out_dir / "intro-body.mp4"
    _run(["-ss", f"{cut:.3f}", "-i", str(keep), "-vf", f"scale={w}:{h},setsar=1,fps={VIDEO['fps']},format=yuv420p",
          "-af", "aresample=48000,aformat=channel_layouts=stereo", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", "-b:a", "160k", str(part_b)])
    va = duration(part_a)
    _run(["-i", str(part_a), "-i", str(part_b), "-filter_complex",
          f"[0:v]setsar=1[v0];[1:v]setsar=1[v1];[0:a]atrim=0:{va:.3f},asetpts=PTS-STARTPTS[a0];[v0][a0][v1][1:a]concat=n=2:v=1:a=1[v][a]",
          "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", "-b:a", "160k", "-ar", "48000",
          "-movflags", "+faststart", str(plain)])
    part_b.unlink(missing_ok=True)                                  # an intermediate the size of the whole video: never kept (a 114 MB one sank run 10's push)
    if short:
        assemble.story_copy(plain, out_dir / "story.mp4")
    _run(["-ss", "1.0", "-i", str(plain), "-frames:v", "1", "-q:v", "2", str(out_dir / "cover.jpg")])
    founder_thumb = out_dir.parent.parent / "inbox" / "thumb" / f"{piece.id}.jpg"
    if founder_thumb.exists():                                      # the founder's own thumbnail goes up with the upload (longs, 4 Nov 2026)
        shutil.copy2(founder_thumb, out_dir / "thumb.jpg")
    piece.ids["intro"] = {"clip": str(Path(clip).name), "seconds": round(secs, 2), "clip_seconds": round(full, 2),
                          "composed": datetime.now(timezone.utc).isoformat(timespec="seconds")}
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


def before_upload(piece, root: Path, out_dir: Path, notify=None, now: datetime | None = None, transcribe=None, compose_fn=None, ask=_ask_claude) -> str:
    """What to do with a finished piece: "compose" (his clip is in and checked: composed in place), "wait" (asked, before the deadline),
    or "plain" (deadline passed, or a bad clip past the deadline)."""
    now = now or datetime.now(timezone.utc)
    notify = notify or (lambda t: None)
    if piece.ids.get("intro_skipped"):
        return "plain"
    clip = clip_path(root, piece)
    if _usable_clip(root, piece):
        if not (piece.topic or {}).get("intro"):
            piece.topic["intro"] = plan(piece, ask)
        problems = check(clip, piece.topic["intro"], transcribe)
        if not problems:
            (compose_fn or compose)(piece, clip, out_dir)
            piece.ids.setdefault("intro", {"clip": clip.name, "composed": now.isoformat(timespec="seconds")})
            return "compose"
        piece.ids["intro_rejected"] = _sha(clip)
        notify(f"🎬 {piece.id}: the intro clip was not used: " + "; ".join(problems) + f". Send a new one with the caption intro {piece.id}"
               + ("" if now < deadline_utc(piece) else "; the plain version goes out now."))
    if now >= deadline_utc(piece):
        piece.ids["intro_skipped"] = now.isoformat(timespec="seconds")
        notify(f"🎬 {piece.id}: no intro clip by {_wat(deadline_utc(piece))}; the plain version is scheduled for its slot.")
        return "plain"
    request(piece, root, notify, ask, now)
    return "wait"


def _sha(path: Path) -> str:
    import hashlib
    return hashlib.sha1(Path(path).read_bytes()).hexdigest()[:16]


def collect(piece, deps, root: Path, now: datetime | None = None, notify=None, transcribe=None, compose_fn=None, find=None) -> tuple:
    """One waiting piece: ("uploaded-intro" | "uploaded-plain" | "waiting" | "rejected" | "rebuilt-<status>", piece). A piece whose plain
    video is not on this machine (a long: out/**/long.mp4 is never in git) is rebuilt by the pipeline from the voice and picture caches,
    which compose and upload at its end."""
    from . import pipeline, youtube
    now = now or datetime.now(timezone.utc)
    notify = notify or (lambda t: None)
    out_dir = Path(root) / "out" / piece.id
    video = out_dir / ("reel.mp4" if piece.kind == "short" else "long.mp4")
    thumb = out_dir / "thumb.jpg"
    if not (_usable_clip(root, piece) or now >= deadline_utc(piece)):
        return "waiting", piece
    if not video.exists():
        old = piece.ids.get("yt_id")
        found = (find or (lambda pc: existing_upload(pc, youtube.access_token(pc.channel), after=_last_change(pc))))(piece)
        if found and found != old:                                 # an earlier run already re-made and uploaded it, then its git push failed
            piece.ids["yt_id"], piece.ids["yt_id_replaced"] = found, old      # (4 Nov 2026, the Tanjore long): adopt it, no second 35-minute build
            piece.ids.setdefault("intro", {"clip": clip_path(root, piece).name, "adopted": now.isoformat(timespec="seconds")})
            pieces.save(pieces.transition(piece, "uploaded", f"intro merged; adopted the upload {found} an earlier run made"), root)
            try:                                                   # the superseded copies go, or the slot would publish twice (4 Nov 2026)
                token = youtube.access_token(piece.channel)
                gone = [old] if old and youtube.delete(token, old) else []
                gone += remove_duplicates(piece, found, token_for=lambda ch: token)
                piece.ids["yt_duplicates_removed"] = sorted(set(piece.ids.get("yt_duplicates_removed", []) + gone))
                pieces.save(piece, root)
            except Exception as e:
                gone = []
                notify(f"🎬 {piece.id}: the earlier upload(s) could not be removed ({secrets.scrub(str(e))[:120]}).")
            notify(f"🎬 {piece.id}: your intro is merged; the piece keeps the re-scheduled upload (YouTube {found})"
                   + (f"; removed {', '.join(gone)}." if gone else "."))
            return "adopted-intro", piece
        piece.status = "drawn"                                     # script, facts and timings stay; voice and pictures come from the caches
        pieces.save(piece, root)
        piece = pipeline.make(piece, deps, root)
        if piece.status == "uploaded" and old and piece.ids.get("yt_id") != old:
            try:
                youtube.delete(youtube.access_token(piece.channel), old)
                piece.ids["yt_id_replaced"] = old
                pieces.save(piece, root)
            except Exception as e:
                notify(f"🎬 {piece.id}: re-uploaded, but the earlier upload {old} could not be removed ({secrets.scrub(str(e))[:120]}).")
        if piece.status == "uploaded" and not getattr(find, "test_only", False):
            try:                                                   # stray private copies of the same slot (4 Nov 2026) go too
                gone = remove_duplicates(piece, piece.ids["yt_id"])
                if gone:
                    pieces.save(piece, root)
                    notify(f"🎬 {piece.id}: {len(gone)} duplicate scheduled upload(s) removed: {', '.join(gone)}.")
            except Exception as e:
                notify(f"🎬 {piece.id}: duplicate uploads could not be checked ({secrets.scrub(str(e))[:120]}).")
        return f"rebuilt-{piece.status}", piece
    action = before_upload(piece, root, out_dir, notify, now, transcribe, compose_fn)
    if action == "wait":
        pieces.save(piece, root)
        return "rejected" if piece.ids.get("intro_rejected") else "waiting", piece
    pipeline.finish_upload(piece, deps, root, video, thumb, out_dir)
    notify(f"🎬 {piece.id}: " + ("your intro is merged and the piece is scheduled for its slot." if action == "compose"
                               else "the plain version is scheduled for its slot."))
    return ("uploaded-intro" if action == "compose" else "uploaded-plain"), piece


def thumb_path(root: Path, piece) -> Path:
    return Path(root) / "inbox" / "thumb" / f"{piece.id}.jpg"


def pending_thumbs(root: Path) -> list:
    """Uploaded pieces whose founder thumbnail in inbox/thumb/ has not been set on YouTube yet."""
    out = []
    for jpg in sorted((Path(root) / "inbox" / "thumb").glob("*.jpg")):
        p = pieces.load(jpg.stem, root)
        if p and p.ids.get("yt_id") and p.ids.get("thumb_sha") != _sha(jpg):
            out.append(p)
    return out


def set_thumbs(root: Path, env=None, notify=None, set_thumb=None, token_for=None) -> list:
    """Puts each pending founder thumbnail on its YouTube video; records the file's hash so it is done once per file."""
    from . import youtube
    notify = notify or (lambda t: None)
    out = []
    for p in pending_thumbs(root):
        jpg = thumb_path(root, p)
        tok = (token_for or youtube.access_token)(p.channel, env)
        ok = (set_thumb or youtube.set_thumbnail)(tok, p.ids["yt_id"], jpg)
        if ok:
            p.ids["thumb_sha"] = _sha(jpg)
            if (Path(root) / "out" / p.id).exists():
                shutil.copy2(jpg, Path(root) / "out" / p.id / "thumb.jpg")
            pieces.save(p, root)
            notify(f"🖼 {p.id}: your thumbnail is set on YouTube ({p.ids['yt_id']}).")
        else:
            notify(f"🖼 {p.id}: YouTube refused the thumbnail (JPG under 2 MB, 1280x720?).")
        out.append((p.id, "thumb-set" if ok else "thumb-refused"))
    return out


def waiting(root: Path) -> list:
    return sorted((p for p in pieces.list_all(root) if p.status == "intro-wait"), key=lambda p: p.publish_day)


ASK_AHEAD_DAYS = 3                           # already-scheduled pieces are asked for in a rolling window, not all at once


def scheduled(root: Path, now: datetime | None = None) -> list:
    """Pieces already uploaded for a coming slot that have no intro yet (founder, 4 Nov 2026: "whatever scheduled can be replaced with
    the new one"): their intro is asked for up to ASK_AHEAD_DAYS ahead, and the clip re-uploads the piece in the same slot."""
    now = now or datetime.now(timezone.utc)
    out = []
    for p in pieces.list_all(root):
        if p.status != "uploaded" or not enabled(p) or p.ids.get("intro") or not p.ids.get("yt_id"):
            continue
        if earliest_slot_utc(p) - timedelta(hours=1) <= now:             # too close to its first posting: leave it
            continue
        out.append(p)
    return sorted(out, key=lambda p: p.publish_day)


def ask_scheduled(root: Path, notify, now: datetime | None = None, ask=_ask_claude) -> list:
    """Sends the intro request for scheduled pieces due within ASK_AHEAD_DAYS that have not been asked; skips one whose clip is already in."""
    now = now or datetime.now(timezone.utc)
    asked = []
    for p in scheduled(root, now):
        if (p.publish_day - now.date()).days > ASK_AHEAD_DAYS or p.ids.get("intro_sent") or clip_path(root, p).exists():
            continue
        request(p, root, notify, ask, now)
        pieces.save(p, root)
        asked.append(p.id)
    return asked


def _usable_clip(root: Path, p) -> bool:
    clip = clip_path(root, p)
    return clip.exists() and _sha(clip) != p.ids.get("intro_rejected")


def needed(root: Path, now: datetime | None = None) -> bool:
    """Cheap: does a waiting piece have a fresh clip, or has one passed its deadline?"""
    now = now or datetime.now(timezone.utc)
    for p in waiting(root):
        if _usable_clip(root, p) or now >= deadline_utc(p):
            return True
    return any(_usable_clip(root, p) for p in scheduled(root, now)) or bool(pending_thumbs(root))


def sweep(root: Path, deps, now: datetime | None = None, notify=None, transcribe=None, compose_fn=None, env=None, delete=None, find=None,
          set_thumb=None, token_for=None) -> list:
    """Waiting pieces are collected; scheduled pieces whose clip has come are re-uploaded with it; founder thumbnails are set. Never raises."""
    now = now or datetime.now(timezone.utc)
    out = []
    try:
        out += set_thumbs(root, env, notify, set_thumb, token_for)
    except Exception as e:
        (notify or print)(f"🖼 thumbnails: {type(e).__name__}: {secrets.scrub(str(e))[:160]}")
    for p in waiting(root):
        try:
            action, p = collect(p, deps, root, now, notify, transcribe, compose_fn)
        except Exception as e:
            action = f"failed: {type(e).__name__}: {secrets.scrub(str(e))[:160]}"
            (notify or print)(f"🎬 {p.id}: intro step failed ({action}); it stays waiting, the plain version goes out at the deadline.")
        out.append((p.id, action))
    for p in scheduled(root, now):
        if not _usable_clip(root, p):
            continue
        try:
            action = redo_piece(p, deps, root, env, notify, transcribe, compose_fn, delete, find)
        except Exception as e:
            action = f"failed: {type(e).__name__}: {secrets.scrub(str(e))[:160]}"
            (notify or print)(f"🎬 {p.id}: re-upload with the intro failed ({action}); the scheduled version stays.")
        out.append((p.id, action))
    return out


def existing_uploads(piece, token: str, call=None) -> list:
    """Every private upload scheduled with this piece's title and publish time, newest upload first:
    [{"id", "uploaded" (the upload moment, UTC), "duration"}]. Empty when YouTube cannot be asked."""
    from . import youtube
    call = call or youtube.call
    want_title = youtube.metadata(piece, slots.publish_at(piece.channel, piece.kind, piece.publish_day))["snippet"]["title"]
    want_at = slots.publish_at(piece.channel, piece.kind, piece.publish_day)
    data = "https://www.googleapis.com/youtube/v3"
    status, _h, ch = call("GET", f"{data}/channels?part=contentDetails&mine=true", token)
    if status != 200:
        return []
    uploads = ch["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    status, _h, body = call("GET", f"{data}/playlistItems?part=contentDetails&maxResults=50&playlistId={uploads}", token)
    ids = [i["contentDetails"]["videoId"] for i in (body.get("items") or [])] if status == 200 else []
    if not ids:
        return []
    status, _h, body = call("GET", f"{data}/videos?part=snippet,status,contentDetails&id={','.join(ids)}", token)
    found = []
    for v in (body.get("items") or []) if status == 200 else []:
        at = str((v.get("status") or {}).get("publishAt", ""))
        try:
            same_time = datetime.fromisoformat(at.replace("Z", "+00:00")) == want_at
        except ValueError:
            same_time = False
        if (v.get("snippet") or {}).get("title") == want_title and (v.get("status") or {}).get("privacyStatus") == "private" and same_time:
            found.append({"id": v["id"], "uploaded": _utc((v.get("snippet") or {}).get("publishedAt", "")),
                          "duration": (v.get("contentDetails") or {}).get("duration", "")})
    return sorted(found, key=lambda f: f["uploaded"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)


def _utc(text: str):
    try:
        return datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except ValueError:
        return None


def existing_upload(piece, token: str, call=None, after: datetime | None = None) -> str:
    """The newest private upload with this piece's title and publish time, made after `after` (4 Nov 2026: a redo whose final git
    push failed had replaced the video on YouTube; running it again must adopt that upload, not add a second one). Only an upload
    newer than the piece's last recorded change can be that one: run 15 adopted an older stray copy and never rebuilt."""
    for f in existing_uploads(piece, token, call):
        if after is None or (f["uploaded"] and f["uploaded"] > after):
            return f["id"]
    return ""


def _last_change(piece) -> datetime | None:
    return _utc(piece.updated) if piece.updated else None


def remove_duplicates(piece, keep: str, token_for=None, delete=None, uploads=None) -> list:
    """After a (re)upload: every other private copy scheduled for this piece's slot is removed, so one slot never publishes twice.
    Returns the ids removed."""
    from . import youtube
    token = (token_for or youtube.access_token)(piece.channel)
    delete = delete or (lambda vid: youtube.delete(token, vid))
    gone = []
    for f in (uploads or existing_uploads)(piece, token):
        if f["id"] != keep and delete(f["id"]):
            gone.append(f["id"])
    if gone:
        piece.ids["yt_duplicates_removed"] = piece.ids.get("yt_duplicates_removed", []) + gone
    return gone


def redo_piece(piece, deps, root: Path, env=None, notify=None, transcribe=None, compose_fn=None, delete=None, find=None) -> str:
    """An already-uploaded piece gets its intro: compose with the clip, delete the scheduled YouTube video, upload the new one in the
    same slot (the publish time comes from the piece as before). The plain file is kept as reel-plain.mp4."""
    from . import pipeline, youtube
    notify = notify or (lambda t: None)
    clip = clip_path(root, piece)
    if not (piece.topic or {}).get("intro"):
        piece.topic["intro"] = plan(piece)                            # the real plan, bridge line included (bridge() falls back to none)
    problems = check(clip, piece.topic["intro"], transcribe)
    if problems:
        piece.ids["intro_rejected"] = _sha(clip)
        pieces.save(piece, root)
        notify(f"🎬 {piece.id}: the intro clip was not used: " + "; ".join(problems) + f". Send a new one with the caption intro {piece.id}.")
        return "rejected"
    out_dir = Path(root) / "out" / piece.id
    plain_video = out_dir / ("reel.mp4" if piece.kind == "short" else "long.mp4")
    if not plain_video.exists():                                    # a long: rebuilt from the caches, composed and re-uploaded by collect()
        since = _last_change(piece)                                   # before this run's own save: an upload newer than this is a failed run's
        pieces.save(pieces.transition(piece, "intro-wait", "re-made from the caches to carry the founder's intro"), root)
        action, piece = collect(piece, deps, root, None, notify, transcribe, compose_fn,
                                find=find or (lambda pc: existing_upload(pc, youtube.access_token(pc.channel, env), after=since)))
        return action
    (compose_fn or compose)(piece, clip, out_dir)
    piece.ids.setdefault("intro", {"clip": clip.name, "composed": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    old = piece.ids.get("yt_id")
    found = (find or (lambda pc: existing_upload(pc, youtube.access_token(pc.channel, env), after=_last_change(pc))))(piece)
    if found and found != old:                                        # an earlier redo already replaced the video: adopt it, upload nothing
        piece.ids["yt_id"], piece.ids["yt_id_replaced"] = found, old
        piece.topic["look"] = piece.topic.get("look") or ""
        pieces.save(pieces.transition(piece, "uploaded", f"intro merged; adopted the upload {found} an earlier run made"), root)
        try:                                                      # the superseded copies go, or the slot would publish twice (4 Nov 2026)
            rm = delete or (lambda ch, vid: youtube.delete(youtube.access_token(ch, env), vid))
            gone = [old] if old and (rm(piece.channel, old) or delete) else []
            gone += remove_duplicates(piece, found, token_for=lambda ch: youtube.access_token(ch, env),
                                      delete=(lambda vid: rm(piece.channel, vid) or True) if delete else None)
            piece.ids["yt_duplicates_removed"] = sorted(set(piece.ids.get("yt_duplicates_removed", []) + gone))
            pieces.save(piece, root)
        except Exception as e:
            gone = []
            notify(f"🎬 {piece.id}: the earlier upload(s) could not be removed ({secrets.scrub(str(e))[:120]}).")
        notify(f"🎬 {piece.id}: your intro is merged; the piece keeps the re-scheduled upload (YouTube {found})"
               + (f"; removed {', '.join(gone)}." if gone else "."))
        return "adopted-intro"
    if old:
        (delete or (lambda ch, vid: youtube.delete(youtube.access_token(ch, env), vid)))(piece.channel, old)
        piece.ids["yt_id_replaced"] = old
    video = out_dir / ("reel.mp4" if piece.kind == "short" else "long.mp4")
    pipeline.finish_upload(piece, deps, root, video, out_dir / "thumb.jpg", out_dir)
    notify(f"🎬 {piece.id}: your intro is merged and the piece is re-scheduled for its slot (YouTube {piece.ids['yt_id']}, the earlier upload removed).")
    return "re-uploaded-intro"


def redo(piece_id: str, root: Path = ROOT, env=None, deps=None, notify=None) -> str:
    from . import pipeline
    piece = pieces.load(piece_id, root)
    if piece is None:
        return f"{piece_id}: no such piece"
    if not clip_path(root, piece).exists():
        return f"{piece_id}: no clip at {clip_path(root, piece)}"
    return f"{piece_id}: " + redo_piece(piece, deps or pipeline.real_deps(root, env), root, env, notify)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan"); ap.add_argument("--needed", action="store_true"); ap.add_argument("--sweep", action="store_true"); ap.add_argument("--redo")
    ap.add_argument("--ask-scheduled", action="store_true"); ap.add_argument("--uploads", help="piece id: list its private scheduled uploads on YouTube")
    ap.add_argument("--tidy", help="piece id: remove every private scheduled copy on YouTube except the recorded yt_id")
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
    if a.ask_scheduled:
        from . import telegram
        print("asked:", ask_scheduled(ROOT, telegram.send) or "nothing"); return 0
    if a.tidy:
        piece = pieces.load(a.tidy, ROOT)
        gone = remove_duplicates(piece, piece.ids["yt_id"])
        pieces.save(piece, ROOT)
        print(f"{a.tidy}: kept {piece.ids['yt_id']}, removed {', '.join(gone) or 'nothing'}"); return 0
    if a.uploads:
        from . import youtube
        piece = pieces.load(a.uploads, ROOT)
        for f in existing_uploads(piece, youtube.access_token(piece.channel)):
            print(f"{f['id']}  uploaded {f['uploaded']:%Y-%m-%d %H:%M} UTC  {f['duration']}" if f["uploaded"] else f"{f['id']}  {f['duration']}")
        print("recorded:", piece.ids.get("yt_id"), "replaced:", piece.ids.get("yt_id_replaced")); return 0
    if a.redo:
        from . import telegram
        print(redo(a.redo, ROOT, notify=telegram.send)); return 0
    ap.print_help(); return 2


if __name__ == "__main__":
    sys.exit(main())
