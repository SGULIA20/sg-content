"""Subtitles for long videos: cue list from the scene timings, SRT files per language (Claude Sonnet translates), YouTube caption tracks.

The YouTube captions endpoint needs the youtube.force-ssl scope; tokens without it get a clear message and the SRT files stay in
out/<id>/subs/ so `python -m engine.subtitles <piece-id>` can upload them once the channel is re-authorised (scripts/yt_authorize.py)."""
import json
import re
import sys
import uuid
from pathlib import Path

from . import secrets
from .config import ROOT
from .pieces import Piece

LANGS = {"hi": "Hindi (Devanagari script)", "en": "English", "gu": "Gujarati", "mr": "Marathi", "ta": "Tamil", "te": "Telugu",
         "bn": "Bengali", "kn": "Kannada", "ml": "Malayalam"}
NAMES = {"hi": "हिन्दी", "en": "English", "gu": "ગુજરાતી", "mr": "मराठी", "ta": "தமிழ்", "te": "తెలుగు", "bn": "বাংলা", "kn": "ಕನ್ನಡ", "ml": "മലയാളം"}
MODEL = "claude-sonnet-5-5"
WORDS_PER_CUE = 11
SPEAK_RATE = 2.5                                             # words per second, used only when the clip length is unknown
CAPTIONS_URL = "https://www.googleapis.com/upload/youtube/v3/captions?part=snippet&uploadType=multipart"
SCOPE_HINT = "the YouTube token lacks the youtube.force-ssl scope: run scripts/yt_authorize.py once per channel, then `python -m engine.subtitles <piece-id>`"


class SubtitleError(Exception):
    pass


def _chunks(text: str, per: int = WORDS_PER_CUE) -> list:
    """Splits a scene's narration into cue-sized pieces at sentence or comma boundaries, never mid-phrase when avoidable."""
    bits = [b.strip() for b in re.split(r"(?<=[.!?।,;])\s+", text.strip()) if b.strip()]
    out, cur = [], ""
    for b in bits:
        if cur and len((cur + " " + b).split()) > per:
            out.append(cur); cur = b
        else:
            cur = (cur + " " + b).strip()
    if cur:
        out.append(cur)
    final = []
    for c in out:                                            # a single long sentence still gets cut to size
        w = c.split()
        final += [" ".join(w[i:i + per]) for i in range(0, len(w), per)] if len(w) > per * 1.5 else [c]
    return final


def cues(piece: Piece, duration: float | None = None) -> list:
    """[(start, end, text)] over the whole video: each scene's time split across its chunks by word share."""
    scenes = (piece.script or {}).get("scenes", [])
    starts = list(piece.timings or [])
    if not scenes or len(starts) != len(scenes):
        raise SubtitleError(f"{piece.id}: timings ({len(starts)}) do not match scenes ({len(scenes)})")
    last_words = len(scenes[-1].get("vo", "").split())
    ends = starts[1:] + [duration if duration else starts[-1] + last_words / SPEAK_RATE]
    out = []
    for sc, s, e in zip(scenes, starts, ends):
        parts = _chunks(sc.get("vo", ""))
        total = sum(len(p.split()) for p in parts) or 1
        t = s
        for p in parts:
            d = (e - s) * len(p.split()) / total
            out.append((round(t, 3), round(min(t + d, e), 3), p))
            t += d
    return out


def _ts(t: float) -> str:
    ms = int(round(t * 1000))
    h, rem = divmod(ms, 3600000); m, rem = divmod(rem, 60000); s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def srt(cue_list: list) -> str:
    return "\n".join(f"{i}\n{_ts(s)} --> {_ts(e)}\n{text}\n" for i, (s, e, text) in enumerate(cue_list, 1))


def translate(lines: list, lang: str, client=None, model: str = MODEL) -> list:
    """Translates the cue texts in order (same count) into one language; Hinglish stays natural, numbers and names unchanged."""
    import anthropic
    client = client or anthropic.Anthropic(api_key=secrets.get("ANTHROPIC_API_KEY"))
    target = LANGS[lang]
    system = (f"You translate Hinglish (Hindi written in Latin letters, mixed with English) video narration into {target} subtitles. "
              "Input is a JSON array of strings; return ONLY a JSON array of the same length, same order, one translation per string. "
              "Keep numbers, currency amounts, years and proper names exactly as they are. Plain spoken language a shopkeeper understands; "
              "no explanations, no extra text.")
    if lang == "hi":
        system += " For Hindi: write the same sentences in Devanagari script, keeping the everyday English words people actually say (EMI, bank, loan) in Devanagari or Latin as a Hindi newspaper would."
    out = []
    for i in range(0, len(lines), 40):                        # batches keep every answer well inside one response
        batch = lines[i:i + 40]
        r = client.messages.create(model=model, max_tokens=8000, system=system,
                                   messages=[{"role": "user", "content": json.dumps(batch, ensure_ascii=False)}])
        text = "".join(getattr(b, "text", "") for b in r.content)
        m = re.search(r"\[.*\]", text, re.S)
        try:
            got = json.loads(m.group(0) if m else text)
        except json.JSONDecodeError:
            raise SubtitleError(f"{lang}: translation was not a JSON array")
        if len(got) != len(batch):
            raise SubtitleError(f"{lang}: {len(got)} translations for {len(batch)} lines")
        out += [str(g) for g in got]
    return out


def write_all(piece: Piece, out_dir: Path, langs=None, duration: float | None = None, client=None, translate_fn=translate) -> dict:
    """Writes out_dir/subs/<lang>.srt for every language; returns {lang: path}. The source Hinglish goes out as hi-Latn.srt for reference."""
    subs = Path(out_dir) / "subs"
    subs.mkdir(parents=True, exist_ok=True)
    base = cues(piece, duration)
    texts = [t for _s, _e, t in base]
    (subs / "hi-Latn.srt").write_text(srt(base), encoding="utf-8")
    paths = {}
    for lang in (langs or list(LANGS)):
        path = subs / f"{lang}.srt"
        if not path.exists():
            got = translate_fn(texts, lang, client) if translate_fn is translate else translate_fn(texts, lang)
            path.write_text(srt([(s, e, g) for (s, e, _t), g in zip(base, got)]), encoding="utf-8")
        paths[lang] = path
    return paths


def _multipart(meta: dict, body: bytes) -> tuple:
    boundary = "sg" + uuid.uuid4().hex
    parts = (f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n{json.dumps(meta)}\r\n"
             f"--{boundary}\r\nContent-Type: application/octet-stream\r\n\r\n").encode() + body + f"\r\n--{boundary}--\r\n".encode()
    return parts, f"multipart/related; boundary={boundary}"


def upload(token: str, video_id: str, lang: str, path: Path, call=None) -> str:
    """Adds one published caption track; returns its id. Raises SubtitleError with the scope hint on 403."""
    from .youtube import call as yt_call
    call = call or yt_call
    meta = {"snippet": {"videoId": video_id, "language": lang, "name": NAMES.get(lang, lang), "isDraft": False}}
    data, ctype = _multipart(meta, Path(path).read_bytes())
    status, _h, body = call("POST", CAPTIONS_URL, token, data=data, headers={"Content-Type": ctype})
    if status in (200, 201) and isinstance(body, dict) and body.get("id"):
        return body["id"]
    if status == 403:
        raise SubtitleError(SCOPE_HINT)
    raise SubtitleError(f"caption upload {lang} failed ({status}): {secrets.scrub(json.dumps(body))[:160]}")


def upload_all(token: str, piece: Piece, paths: dict, call=None) -> dict:
    """Uploads every track not yet recorded in piece.ids['captions']; stops at the first scope error."""
    done = dict(piece.ids.get("captions") or {})
    for lang, path in paths.items():
        if lang in done:
            continue
        done[lang] = upload(token, piece.ids["yt_id"], lang, path, call)
        piece.ids["captions"] = done
    return done


def main(argv=None) -> int:
    import os
    from . import pieces, youtube
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print("usage: python -m engine.subtitles <piece-id> [lang ...]"); return 2
    piece = pieces.load(argv[0], ROOT)
    if not piece or not piece.ids.get("yt_id"):
        print(f"{argv[0]}: not found or not uploaded"); return 1
    out_dir = ROOT / "out" / piece.id
    paths = write_all(piece, out_dir, langs=argv[1:] or None)
    token = youtube.access_token(piece.channel, os.environ)
    try:
        done = upload_all(token, piece, paths)
    finally:
        pieces.save(piece, ROOT)
    print(f"{piece.id}: caption tracks live for {', '.join(sorted(done))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
