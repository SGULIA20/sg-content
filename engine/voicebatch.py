"""Voice through Gemini's Batch API (22 Oct 2026): one job per piece with every scene line, half the price, outside the 100-requests-a-day
synchronous limit, audio back in a few minutes. Results land in the same cache that voice.say() reads, so the rest of the pipeline is
unchanged. A job that is still running when the run cannot wait any longer parks the piece as "voicing"; the next run collects it."""
import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from . import gemini, secrets, voice
from .config import CACHE_DIR, LOGS_DIR

BATCH_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{voice.MODEL}:batchGenerateContent"
GET_URL = "https://generativelanguage.googleapis.com/v1beta/{name}"
WAIT_S = 600                 # how long one run waits for a job before parking the piece
POLL_S = 20
LEDGER = LOGS_DIR / "voice-batch.jsonl"


class BatchError(Exception):
    pass


def _speech(voice_id: str) -> dict:
    cfg = {"voice": voice_id} if voice_id.startswith("voice") else {"prebuiltVoiceConfig": {"voiceName": voice_id}}
    return {"responseModalities": ["AUDIO"], "speechConfig": {"voiceConfig": cfg}}


def submit(texts: list, voice_id: str, label: str, key: str | None = None, post=gemini._post) -> str:
    """Starts one job with every line; returns its name (batches/...)."""
    key = key or secrets.get("GEMINI_API_KEY")
    reqs = [{"request": {"contents": [{"parts": [{"text": t}]}], "generationConfig": _speech(voice_id)}} for t in texts]
    body = {"batch": {"display_name": label[:60], "input_config": {"requests": {"requests": reqs}}}}
    status, data = post(BATCH_URL, body, key)
    if status != 200 or not data.get("name"):
        raise BatchError(f"batch submit failed ({status}): {secrets.scrub(json.dumps(data))[:200]}")
    _log({"at": datetime.now(timezone.utc).isoformat(), "label": label, "name": data["name"], "lines": len(texts), "voice": voice_id})
    return data["name"]


def _get(name: str, key: str) -> dict:
    req = urllib.request.Request(GET_URL.format(name=name), headers={"x-goog-api-key": key})
    with urllib.request.urlopen(req, timeout=60, context=secrets.ssl_context()) as r:
        return json.loads(r.read())


def poll(name: str, key: str | None = None, get=None) -> tuple:
    """("running" | "done" | "failed", payload)"""
    data = (get or _get)(name, key or secrets.get("GEMINI_API_KEY"))
    state = (data.get("metadata") or {}).get("state", "")
    if "SUCCEEDED" in state:
        return "done", data
    if "FAILED" in state or "CANCEL" in state or "EXPIRED" in state:
        return "failed", data
    return "running", data


def collect(data: dict, texts: list, voice_id: str, cache_dir: Path = CACHE_DIR / "voice") -> list:
    """Writes every line's audio into the voice cache; returns the indexes that came back without audio."""
    rows = ((data.get("response") or {}).get("inlinedResponses") or {}).get("inlinedResponses") or []
    missing = []
    for i, text in enumerate(texts):
        row = rows[i] if i < len(rows) else {}
        parts = (((row.get("response") or {}).get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
        blob = next((p["inlineData"] for p in parts if p.get("inlineData")), None)
        if not blob:
            missing.append(i)
            continue
        import base64
        raw = base64.b64decode(blob["data"])
        wav = raw if "wav" in blob.get("mimeType", "") else voice._pcm_to_wav(raw)
        voice.cache_path(text, voice_id, cache_dir).write_bytes(wav)
    return missing


def _log(row: dict) -> None:
    try:
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
        with LEDGER.open("a") as f:
            f.write(json.dumps(row) + "\n")
    except OSError:
        pass


def voice_piece(piece, texts: list, voice_id: str, *, key: str | None = None, cache_dir: Path = CACHE_DIR / "voice", wait_s: float = WAIT_S,
                post=gemini._post, get=None, sleep=time.sleep, clock=time.monotonic) -> str:
    """Makes sure every line is in the cache. Returns "ready" when all lines are cached, or "voicing" when a job is still running
    (piece.ids["voice_batch"] remembers it for the next run). Raises BatchError when the batch path itself is unusable."""
    missing = [t for t in texts if not voice.cache_path(t, voice_id, cache_dir).exists()]
    if not missing:
        return "ready"
    key = key or secrets.get("GEMINI_API_KEY")
    job = piece.ids.get("voice_batch") or {}
    if job.get("voice") != voice_id or job.get("lines") != len(missing):
        job = {"name": submit(missing, voice_id, piece.id, key, post), "voice": voice_id, "lines": len(missing), "tries": job.get("tries", 0) + 1}
        piece.ids["voice_batch"] = job
    start = clock()
    while True:
        state, data = poll(job["name"], key, get)
        if state == "done":
            still = collect(data, missing, voice_id, cache_dir)
            piece.ids.pop("voice_batch", None)
            if still:
                raise BatchError(f"{len(still)} line(s) came back without audio")
            return "ready"
        if state == "failed":
            piece.ids.pop("voice_batch", None)
            if job["tries"] >= 2:
                raise BatchError("batch job failed twice")
            job = {"name": submit(missing, voice_id, piece.id, key, post), "voice": voice_id, "lines": len(missing), "tries": job["tries"] + 1}
            piece.ids["voice_batch"] = job
            continue
        if clock() - start >= wait_s:
            return "voicing"
        sleep(POLL_S)
