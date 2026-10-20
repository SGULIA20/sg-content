"""The founder's replicated Gemini voice: enrol once, then one synthesis request per scene line with a cache and a daily budget (spec §3 step 5, §6.10).

python -m engine.voice --enrol <reference.wav> <consent.wav> [--name "SG Hinglish v1"]   creates the voice in this project's Gemini project and writes content/voice.json
"""
import argparse
import base64
import hashlib
import json
import sys
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


def say(text: str, voice_id: str, out_wav: Path, *, key: str | None = None, cache_dir: Path = CACHE_DIR / "voice",
        budget: Path = BUDGET_FILE, post=gemini._post, style: str = STYLE, today: date | None = None) -> float:
    """Synthesizes one line into out_wav (24 kHz mono 16-bit) and returns its length in seconds. Cached by voice, style and text."""
    today = today or today_pacific()
    out_wav = Path(out_wav)
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cached = cache_dir / (hashlib.sha1(f"{voice_id}|{style}|{text}".encode()).hexdigest() + ".wav")
    if not cached.exists():
        if requests_today(budget, today) >= BUDGETS["voice_requests_per_day"]:
            raise VoiceBudget(f"voice budget of {BUDGETS['voice_requests_per_day']} requests reached for {today}")
        key = key or secrets.get("GEMINI_API_KEY")
        _count_request(budget, today)
        if voice_id.startswith("voice"):                                  # a replicated or designed voice: interactions API
            body = {"model": MODEL,
                    "input": [{"type": "user_input", "content": [{"type": "text", "text": text,
                                                                  "annotations": [{"type": "speech_metadata", "style": style}]}]}],
                    "response_format": {"type": "audio"},
                    "generation_config": {"speech_config": [{"voice": voice_id}]}}
            status, data = post(SYNTH_URL, body, key)
            if status != 200:
                raise VoiceError(f"voice synthesis failed ({status}): {secrets.scrub(str((data.get('error') or {}).get('message', '')))[:300]}")
            audio = _audio_from(data)
        else:                                                              # a prebuilt voice name (Puck, Kore, ...): generateContent, raw PCM back
            body = {"contents": [{"parts": [{"text": f"{style}: {text}" if style else text}]}],
                    "generationConfig": {"responseModalities": ["AUDIO"], "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice_id}}}}}
            status, data = post(f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent", body, key)
            if status != 200:
                raise VoiceError(f"voice synthesis failed ({status}): {secrets.scrub(str((data.get('error') or {}).get('message', '')))[:300]}")
            audio = _pcm_to_wav(_pcm_from(data))
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
