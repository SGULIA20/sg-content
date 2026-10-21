"""The founder's replicated Gemini voice: enrol once, then one synthesis request per scene line with a cache and a daily budget (spec §3 step 5, §6.10).

python -m engine.voice --enrol <reference.wav> <consent.wav> [--name "SG Hinglish v1"]   creates the voice in this project's Gemini project and writes content/voice.json
"""
import argparse
import base64
import hashlib
import json
import re
import sys
import time
import wave
from datetime import date
from pathlib import Path

from . import gemini, secrets
from .config import BUDGETS, CACHE_DIR, CONTENT_DIR, LOGS_DIR, today_ist, today_pacific

MODEL = "gemini-3.8-flash-tts"
VOICES_URL = "https://generativelanguage.googleapis.com/v1beta/voices"
SYNTH_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
STYLE = "clear, warm, natural Hindi explainer voice, medium pace"
VOICE_FILE = CONTENT_DIR / "voice.json"
BUDGET_FILE = LOGS_DIR / "voice-budget.json"
DEFAULT_IDS = ("voice_9c6x5lerrbm4", "voice_7w9h8qkiqz03")      # created 19 Oct 2026 in the founder's first Gemini project
MIN_GAP_S = 6.5            # Tier 1 allows 10 requests a minute; one line every 6.5 s stays under it (21 Oct 2026: a 429 mid-Short)
RATE_RETRIES = 2           # a 429 waits the time Google names (at most RATE_WAIT_MAX_S) and tries again
RATE_WAIT_MAX_S = 65
_last_request = [0.0]


class VoiceError(Exception):
    pass


class VoiceBudget(VoiceError):
    pass


def voice_ids(root: Path = CONTENT_DIR) -> tuple:
    path = Path(root) / "voice.json"
    if not path.exists():
        return DEFAULT_IDS
    d = json.loads(path.read_text())
    return d.get("default", DEFAULT_IDS[0]), d.get("fallback", DEFAULT_IDS[1])


def pick(piece_id: str, root: Path = CONTENT_DIR) -> str:
    """One voice per piece from the pool in content/voice.json, chosen by the piece id so a resumed piece keeps its voice."""
    path = Path(root) / "voice.json"
    if not path.exists():
        return DEFAULT_IDS[0]
    d = json.loads(path.read_text())
    pool = [v for v in d.get("pool", []) if v]
    if not pool:
        return d.get("default", DEFAULT_IDS[0])
    return pool[int(hashlib.sha1(piece_id.encode()).hexdigest(), 16) % len(pool)]


def _b64(path: Path) -> str:
    return base64.b64encode(Path(path).read_bytes()).decode()


def enrol(ref_wav: Path, consent_wav: Path, *, key: str | None = None, display_name: str = "SG Hinglish", post=gemini._post) -> str:
    key = key or secrets.get("GEMINI_API_KEY")
    body = {"store": True, "voice": {"model": MODEL, "type": "replicated", "display_name": display_name,
                                     "replicated": {"source_audio": {"mime_type": "audio/wav", "data": _b64(ref_wav)},
                                                    "consent_audio": {"mime_type": "audio/wav", "data": _b64(consent_wav)}}}}
    status, data = post(VOICES_URL, body, key)
    if status != 200 or "id" not in data:
        raise VoiceError(f"voice enrolment failed ({status}): {secrets.scrub(json.dumps(data))[:300]}")
    return data["id"]


def requests_today(budget: Path = BUDGET_FILE, today: date | None = None) -> int:
    today = today or today_pacific()
    try:
        return int(json.loads(Path(budget).read_text()).get(today.isoformat(), 0))
    except (FileNotFoundError, ValueError):
        return 0


def _count_request(budget: Path, today: date) -> None:
    try:
        data = json.loads(Path(budget).read_text())
    except (FileNotFoundError, ValueError):
        data = {}
    data[today.isoformat()] = int(data.get(today.isoformat(), 0)) + 1
    Path(budget).parent.mkdir(parents=True, exist_ok=True)
    Path(budget).write_text(json.dumps(data, indent=1))


def _seconds(wav: Path) -> float:
    with wave.open(str(wav)) as w:
        return w.getnframes() / w.getframerate()


def _pcm_from(response: dict) -> bytes | None:
    for c in response.get("candidates", []):
        for p in (c.get("content") or {}).get("parts", []):
            blob = p.get("inlineData") or p.get("inline_data")
            if blob and blob.get("data"):
                return base64.b64decode(blob["data"])
    return None


def _pcm_to_wav(pcm: bytes | None, rate: int = 24000) -> bytes | None:
    if not pcm:
        return None
    import io
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate); w.writeframes(pcm)
    return buf.getvalue()


def _audio_from(response: dict) -> bytes | None:
    for step in response.get("steps", []):
        if step.get("type") == "model_output":
            for c in step.get("content", []):
                if c.get("type") == "audio" and c.get("data"):
                    return base64.b64decode(c["data"])
    out = response.get("output_audio") or {}
    return base64.b64decode(out["data"]) if out.get("data") else None


def cache_path(text: str, voice_id: str, cache_dir: Path = CACHE_DIR / "voice", style: str = STYLE) -> Path:
    """Where a line's audio lives once made (by say() or by a batch job). Prebuilt voices get no style text; "plain" also retires the
    WAVs from before 22 Oct 2026 that spoke the style note aloud."""
    key_style = style if voice_id.startswith("voice") else "plain"
    Path(cache_dir).mkdir(parents=True, exist_ok=True)
    return Path(cache_dir) / (hashlib.sha1(f"{voice_id}|{key_style}|{text}".encode()).hexdigest() + ".wav")


def say(text: str, voice_id: str, out_wav: Path, *, key: str | None = None, cache_dir: Path = CACHE_DIR / "voice",
        budget: Path = BUDGET_FILE, post=gemini._post, style: str = STYLE, today: date | None = None,
        sleep=time.sleep, clock=time.monotonic) -> float:
    """Synthesizes one line into out_wav (24 kHz mono 16-bit) and returns its length in seconds. Cached by voice, style and text."""
    today = today or today_pacific()
    out_wav = Path(out_wav)
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cached = cache_path(text, voice_id, cache_dir, style)
    if not cached.exists():
        if requests_today(budget, today) >= BUDGETS["voice_requests_per_day"]:
            raise VoiceBudget(f"voice budget of {BUDGETS['voice_requests_per_day']} requests reached for {today}")
        key = key or secrets.get("GEMINI_API_KEY")
        if voice_id.startswith("voice"):                                  # a replicated or designed voice: interactions API
            url = SYNTH_URL
            body = {"model": MODEL,
                    "input": [{"type": "user_input", "content": [{"type": "text", "text": text,
                                                                  "annotations": [{"type": "speech_metadata", "style": style}]}]}],
                    "response_format": {"type": "audio"},
                    "generation_config": {"speech_config": [{"voice": voice_id}]}}
        else:                                                              # a prebuilt voice name (Puck, Kore, ...): generateContent, raw PCM back
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
            body = {"contents": [{"parts": [{"text": text}]}],                 # no style prefix: Puck and Kore read it aloud (22 Oct 2026: "Clear, warm... medium pace. Raat ko...")
                    "generationConfig": {"responseModalities": ["AUDIO"], "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice_id}}}}}
        for attempt in range(RATE_RETRIES + 1):
            wait = _last_request[0] + MIN_GAP_S - clock()
            if wait > 0:
                sleep(wait)
            _last_request[0] = clock()
            status, data = post(url, body, key)
            if status != 429 or attempt == RATE_RETRIES:
                break
            m = re.search(r"retry in (\d+(?:\.\d+)?)\s*s", str((data.get("error") or {}).get("message", "")))
            sleep(min(float(m.group(1)) + 1 if m else 60, RATE_WAIT_MAX_S))
        if status != 429:
            _count_request(budget, today)                                  # a rate-limited (429) request never reached the model
        if status != 200:
            raise VoiceError(f"voice synthesis failed ({status}): {secrets.scrub(str((data.get('error') or {}).get('message', '')))[:300]}")
        audio = _audio_from(data) if url == SYNTH_URL else _pcm_to_wav(_pcm_from(data))
        if not audio:
            raise VoiceError("voice synthesis returned no audio")
        cached.write_bytes(audio)
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    out_wav.write_bytes(cached.read_bytes())
    return _seconds(out_wav)


def lines(piece, voice_id: str, out_dir: Path, **kw) -> list:
    """One WAV per scene, in order: [(path, seconds), ...]."""
    out = []
    for i, scene in enumerate((piece.script or {}).get("scenes", [])):
        wav = Path(out_dir) / f"vo{i:02d}.wav"
        out.append((wav, say(scene["vo"], voice_id, wav, **kw)))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--enrol", nargs=2, metavar=("REF_WAV", "CONSENT_WAV"))
    ap.add_argument("--name", default="SG Hinglish v1")
    a = ap.parse_args(argv)
    if a.enrol:
        vid = enrol(Path(a.enrol[0]), Path(a.enrol[1]), display_name=a.name)
        existing = json.loads(VOICE_FILE.read_text()) if VOICE_FILE.exists() else {}
        data = {"default": vid, "fallback": existing.get("default") or DEFAULT_IDS[0], "created": today_ist().isoformat(), "name": a.name}
        VOICE_FILE.parent.mkdir(parents=True, exist_ok=True)
        VOICE_FILE.write_text(json.dumps(data, indent=1) + "\n")
        print(f"voice {vid} written to {VOICE_FILE}")
        return 0
    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())


# ---- batched synthesis: a few scenes per request (Google allows 100 requests a day), split back into one WAV per scene ----
GROUP = 4                   # scenes per request: a Short becomes 3-4 requests instead of 13, a long about 10 instead of 40
JOIN = "\n\n"               # a paragraph break makes the model pause between scenes; the pause is where the audio is cut
MIN_SILENCE_S = 0.28
FRAME_S = 0.02


def _silences(pcm, rate: int, min_s: float = MIN_SILENCE_S) -> list:
    """[(start, end)] of quiet stretches at least min_s long, by 20 ms RMS frames against a floor relative to the loud parts."""
    import numpy as np
    n = int(rate * FRAME_S)
    if len(pcm) < n * 5:
        return []
    frames = pcm[: len(pcm) // n * n].astype(np.float32).reshape(-1, n)
    rms = np.sqrt((frames ** 2).mean(axis=1))
    floor = max(120.0, float(np.percentile(rms, 90)) * 0.06)
    quiet = rms < floor
    out, start = [], None
    for i, q in enumerate(list(quiet) + [False]):
        if q and start is None:
            start = i
        elif not q and start is not None:
            if (i - start) * FRAME_S >= min_s:
                out.append((start * FRAME_S, i * FRAME_S))
            start = None
    return out


def split_group(wav: Path, texts: list, outs: list) -> list | None:
    """Cuts one group WAV into len(texts) scene WAVs at the pauses nearest each scene's word-share boundary.
    Returns [(path, seconds)] or None when the pauses do not line up (the caller then voices that group line by line)."""
    import numpy as np
    with wave.open(str(wav)) as w:
        rate, pcm = w.getframerate(), np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    total = len(pcm) / rate
    if len(texts) == 1:
        cuts = []
    else:
        words = [max(1, len(t.split())) for t in texts]
        targets = [total * sum(words[:i + 1]) / sum(words) for i in range(len(texts) - 1)]
        mids = [((s + e) / 2, e - s) for s, e in _silences(pcm, rate)]
        tol = max(1.2, 0.35 * total / len(texts))
        cuts, used = [], -1.0
        for t in targets:
            near = [(m, ln) for m, ln in mids if m > used + 0.5 and abs(m - t) <= tol]
            if not near:
                return None
            c = max(near, key=lambda x: (round(x[1], 1), -abs(x[0] - t)))[0]      # the longest pause near the target: paragraph breaks run longer than commas
            cuts.append(c); used = c
    bounds = [0.0] + cuts + [total]
    out = []
    for i, (a, b) in enumerate(zip(bounds, bounds[1:])):
        seg = pcm[int(a * rate): int(b * rate)]
        p = Path(outs[i]); p.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(p), "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate); w.writeframes(seg.tobytes())
        out.append((p, round(len(seg) / rate, 3)))
    return out


def _norm_words(text: str) -> list:
    return [w for w in re.sub(r"[^\w\s]", " ", text.lower()).split() if w]


def transcribe(wav: Path, key: str | None = None, ask=gemini.generate) -> str:
    """What the audio says (Gemini flash, audio in); used only to check that a cut landed on a scene boundary."""
    import base64
    body = {"contents": [{"parts": [{"inlineData": {"mimeType": "audio/wav", "data": base64.b64encode(Path(wav).read_bytes()).decode()}},
                                    {"text": "Transcribe this Hinglish audio exactly as spoken, Latin script, no commentary."}]}]}
    return gemini.text(ask("gemini-3.8-flash", body, key or secrets.get("GEMINI_API_KEY"))).strip()


def segment_matches(heard: str, text: str, edge: int = 2) -> bool:
    """True when the transcript begins with the scene's first words and ends with its last words (allowing one slip at each edge)."""
    h, t = _norm_words(heard), _norm_words(text)
    if len(h) < 2 or len(t) < 2:
        return False
    head_ok = any(w in h[:edge + 2] for w in t[:edge]) and h[0] in t[:edge + 1]
    tail_ok = any(w in h[-(edge + 2):] for w in t[-edge:]) and h[-1] in t[-(edge + 1):]
    return head_ok and tail_ok and abs(len(h) - len(t)) <= max(3, len(t) // 3)


def batched(texts: list, voice_id: str, out_dir: Path, say_fn=None, group: int = GROUP, verify=None, **kw) -> list:
    """One WAV per scene, in order, using one request per `group` scenes. Each cut segment is transcribed and checked against its scene;
    a group whose pauses cannot be matched, or whose segments do not read back right, falls back to a request per line."""
    say_fn = say_fn or say
    verify = verify if verify is not None else (lambda wav, text: segment_matches(transcribe(wav), text))
    out_dir = Path(out_dir)
    result = []
    for g in range(0, len(texts), group):
        chunk = texts[g:g + group]
        outs = [out_dir / f"vo{g + i:02d}.wav" for i in range(len(chunk))]
        if len(chunk) == 1:
            result.append((outs[0], say_fn(chunk[0], voice_id, outs[0], **kw)))
            continue
        gw = out_dir / "groups" / f"g{g:02d}.wav"
        gw.parent.mkdir(parents=True, exist_ok=True)
        say_fn(JOIN.join(chunk), voice_id, gw, **kw)
        parts = split_group(gw, chunk, outs)
        if parts is not None and verify is not False:
            bad = [i for i, ((p, _d), t) in enumerate(zip(parts, chunk)) if not verify(p, t)]
            if bad:
                print(f"voice: group {g // group} segments {bad} did not read back as their scenes", flush=True)
                parts = None
        if parts is None:
            print(f"voice: group {g // group} voiced line by line", flush=True)
            parts = [(o, say_fn(t, voice_id, o, **kw)) for t, o in zip(chunk, outs)]
        result += parts
    return result
