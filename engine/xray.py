"""Reel X-ray (founder, 2 Nov 2026; moved here from arthvan-media with the Studio bot, 4 Nov 2026): the founder sends another creator's
Reel (a screen recording or the saved video, under 20 MB) to the Studio bot; Gemini watches it with sound and answers with why it works
and what to copy for Learning with SG and SG-MYTH-WORLD. The breakdown is saved under logs/xray/ for the planning sessions."""
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from . import secrets
from .gemini import GeminiError

MODEL = "gemini-3.8-flash"
BASE = "https://generativelanguage.googleapis.com"
MAX_BYTES = 20 * 1024 * 1024                       # a bot may download at most 20 MB from Telegram
PROMPT = """You are a short-video strategist. Watch this Instagram Reel (with sound) for a founder who runs two channels:
Learning with SG (Hindi/Hinglish personal finance for ordinary Indians) and SG-MYTH-WORLD (Indian history and mythology with evidence).
His Reels open with a 10-second clip of his own avatar asking a question, then an AI-voiced painted story; his problem is that people
swipe away early.
{note}
Answer in simple English, short lines, with these headings:
1. HOOK (first 3 seconds): exactly what is shown and said, and why it stops the scroll.
2. LENGTH AND PACE: total seconds; how often the picture changes (about how many cuts or movements per 10 seconds).
3. ON-SCREEN TEXT: what is written, how big, where, when it appears.
4. VOICE, MUSIC, STYLE: who speaks, tone, music, visual style.
5. STRUCTURE: the beats in order, with rough timestamps.
6. CALL TO ACTION: what the viewer is asked to do (comment a word, follow, save, share) and how.
7. WHY IT WORKS: the 3 strongest reasons, most important first.
8. COPY FOR US: 3 concrete changes for Learning with SG and 2 for SG-MYTH-WORLD, each doable with an avatar intro, AI voice and drawn visuals.
9. DO NOT COPY: anything that would not suit his channels or could break Instagram/YouTube rules.
At most 380 words. Do not invent numbers you cannot see or hear."""


def _req(url: str, *, data=None, headers=None, method="GET", timeout=180):
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=secrets.ssl_context()) as r:
            return r.headers, r.read()
    except urllib.error.HTTPError as e:
        raise GeminiError(f"Gemini {method} {url.split('?')[0][-40:]} failed ({e.code}): {e.read()[:200].decode(errors='replace')}")


def upload(path: Path, key: str, mime: str = "video/mp4", req=_req) -> dict:
    """Gemini Files API, resumable upload in one go; waits until the video is processed."""
    data = Path(path).read_bytes()
    h, _ = req(f"{BASE}/upload/v1beta/files", method="POST", data=json.dumps({"file": {"display_name": Path(path).name}}).encode(),
               headers={"x-goog-api-key": key, "X-Goog-Upload-Protocol": "resumable", "X-Goog-Upload-Command": "start",
                        "X-Goog-Upload-Header-Content-Length": str(len(data)), "X-Goog-Upload-Header-Content-Type": mime,
                        "Content-Type": "application/json"})
    url = h.get("X-Goog-Upload-URL") or h.get("x-goog-upload-url")
    _h, body = req(url, method="POST", data=data, headers={"X-Goog-Upload-Command": "upload, finalize", "X-Goog-Upload-Offset": "0",
                                                           "Content-Length": str(len(data))})
    f = json.loads(body)["file"]
    for _ in range(40):
        if f.get("state") == "ACTIVE":
            return f
        if f.get("state") == "FAILED":
            raise GeminiError("Gemini could not read the video")
        time.sleep(3)
        _h, body = req(f"{BASE}/v1beta/{f['name']}", headers={"x-goog-api-key": key})
        f = json.loads(body)
    raise GeminiError("Gemini took too long to process the video")


def analyse(path: Path, note: str = "", *, key: str | None = None, req=_req, model: str = MODEL) -> str:
    key = secrets.get("GEMINI_API_KEY") if key is None else key
    f = upload(path, key, req=req)
    prompt = PROMPT.format(note=f"The founder's note: {note.strip()}" if note.strip() else "")
    body = {"contents": [{"parts": [{"file_data": {"mime_type": f.get("mimeType", "video/mp4"), "file_uri": f["uri"]}}, {"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": 2500, "temperature": 0.4}}
    _h, raw = req(f"{BASE}/v1beta/models/{model}:generateContent", method="POST", data=json.dumps(body).encode(),
                  headers={"Content-Type": "application/json", "x-goog-api-key": key}, timeout=300)
    d = json.loads(raw)
    try:
        text = "".join(p.get("text", "") for p in d["candidates"][0]["content"]["parts"]).strip()
    except (KeyError, IndexError):
        raise GeminiError("Gemini gave no answer for the video")
    if not text:
        raise GeminiError("Gemini gave an empty answer for the video")
    return text


def save(root: Path, note: str, text: str, now: datetime | None = None) -> Path:
    now = now or datetime.now(timezone.utc)
    out = Path(root) / "logs" / "xray" / f"{now.strftime('%Y-%m-%d-%H%M%S')}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(f"# Reel X-ray {now.date().isoformat()}\n\nNote: {note.strip() or '-'}\n\n{text}\n")
    return out


def video_of(message: dict) -> dict | None:
    """The video part of a Telegram message: a video, a round video note, or a file sent as a document with a video type."""
    if message.get("video"):
        return message["video"]
    if message.get("video_note"):
        return message["video_note"]
    doc = message.get("document") or {}
    return doc if str(doc.get("mime_type", "")).startswith("video/") else None


def image_of(message: dict) -> dict | None:
    """A photo (largest size) or an image sent as a file."""
    if message.get("photo"):
        return max(message["photo"], key=lambda p: p.get("file_size") or 0)
    doc = message.get("document") or {}
    return doc if str(doc.get("mime_type", "")).startswith("image/") else None
