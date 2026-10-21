"""Pictures through Gemini's Batch API (22 Oct 2026): every panel and the thumbnail of a piece as one job, half the price of the
synchronous calls, back in a few minutes. Cast reference pictures go up once per run through the Files API and are referenced by URI.
Results land in the same cache art.paint() reads, so the rest of the pipeline is unchanged; a job still running when the run cannot
wait parks the piece as "painting" and the next run collects it."""
import base64
import io
import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from . import art, gemini, secrets
from .config import BUDGETS, CACHE_DIR, LOGS_DIR

BATCH_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:batchGenerateContent"
GET_URL = "https://generativelanguage.googleapis.com/v1beta/{name}"
UPLOAD_URL = "https://generativelanguage.googleapis.com/upload/v1beta/files"
WAIT_S = 600
POLL_S = 20
INR_PER_IMAGE = 1.5                                  # half of the synchronous ₹3
LEDGER = LOGS_DIR / "art-batch.jsonl"
_uploaded: dict = {}                                 # (path, mtime) -> file uri, for this process


class BatchError(Exception):
    pass


def upload_ref(path: Path, key: str, opener=None) -> str:
    """Puts one reference picture in the Files API (48 h life) and returns its URI; repeated calls in a run reuse the first upload."""
    path = Path(path)
    memo = (str(path), path.stat().st_mtime)
    if memo in _uploaded:
        return _uploaded[memo]
    data = path.read_bytes()
    mime = art.MIME.get(path.suffix.lower(), "image/png")
    req = urllib.request.Request(UPLOAD_URL, data=data, method="POST",
                                 headers={"x-goog-api-key": key, "X-Goog-Upload-Protocol": "raw", "Content-Type": mime,
                                          "X-Goog-Upload-Header-Content-Length": str(len(data))})
    opener = opener or (lambda r: urllib.request.urlopen(r, timeout=120, context=secrets.ssl_context()))
    with opener(req) as r:
        uri = json.loads(r.read())["file"]["uri"]
    _uploaded[memo] = uri
    return uri


def submit(jobs: list, label: str, key: str, model: str = art.MODEL, post=gemini._post, upload=upload_ref) -> str:
    """jobs: [(prompt, refs, aspect)] -> batch name."""
    reqs = []
    for prompt, refs, aspect in jobs:
        parts = [{"fileData": {"mimeType": art.MIME.get(Path(r).suffix.lower(), "image/png"), "fileUri": upload(Path(r), key)}} for r in refs]
        parts.append({"text": prompt})
        reqs.append({"request": {"contents": [{"parts": parts}], "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": aspect}}}})
    body = {"batch": {"display_name": label[:60], "input_config": {"requests": {"requests": reqs}}}}
    status, data = post(BATCH_URL.format(model=model), body, key)
    if status != 200 or not data.get("name"):
        raise BatchError(f"batch submit failed ({status}): {secrets.scrub(json.dumps(data))[:200]}")
    _log({"at": datetime.now(timezone.utc).isoformat(), "label": label, "name": data["name"], "pictures": len(jobs)})
    return data["name"]


def _get(name: str, key: str) -> dict:
    req = urllib.request.Request(GET_URL.format(name=name), headers={"x-goog-api-key": key})
    with urllib.request.urlopen(req, timeout=60, context=secrets.ssl_context()) as r:
        return json.loads(r.read())


def poll(name: str, key: str, get=None) -> tuple:
    data = (get or _get)(name, key)
    state = (data.get("metadata") or {}).get("state", "")
    if "SUCCEEDED" in state:
        return "done", data
    if "FAILED" in state or "CANCEL" in state or "EXPIRED" in state:
        return "failed", data
    return "running", data


def _png(blob: dict) -> bytes:
    raw = base64.b64decode(blob["data"])
    if "png" in blob.get("mimeType", ""):
        return raw
    from PIL import Image
    buf = io.BytesIO()
    Image.open(io.BytesIO(raw)).convert("RGB").save(buf, format="PNG")
    return buf.getvalue()


def collect(data: dict, tags: list, cache_dir: Path, spend: Path, today, model: str = art.MODEL) -> list:
    """Writes every returned picture into the art cache under its tag; returns the indexes that came back without one."""
    rows = ((data.get("response") or {}).get("inlinedResponses") or {}).get("inlinedResponses") or []
    missing, got = [], 0
    for i, tag in enumerate(tags):
        row = rows[i] if i < len(rows) else {}
        parts = (((row.get("response") or {}).get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
        blob = next((p.get("inlineData") or p.get("inline_data") for p in parts if p.get("inlineData") or p.get("inline_data")), None)
        if not blob:
            missing.append(i)
            continue
        (Path(cache_dir) / f"{tag}.png").write_bytes(_png(blob))
        got += 1
    if got:
        art._record(spend, today, INR_PER_IMAGE * got)
    return missing


def _log(row: dict) -> None:
    try:
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
        with LEDGER.open("a") as f:
            f.write(json.dumps(row) + "\n")
    except OSError:
        pass


def paint_piece(piece, jobs: list, *, key: str | None = None, model: str = art.MODEL, cache_dir: Path = CACHE_DIR / "art",
                spend: Path = art.SPEND_FILE, today=None, wait_s: float = WAIT_S, post=gemini._post, get=None, upload=upload_ref,
                sleep=time.sleep, clock=time.monotonic) -> str:
    """Makes sure every picture in `jobs` [(prompt, refs, aspect)] is in the cache. "ready" when they all are; "painting" when the job is
    still running (piece.ids["art_batch"] remembers it). Pictures the job does not return are left for the synchronous path."""
    from .config import today_pacific
    today = today or today_pacific()
    Path(cache_dir).mkdir(parents=True, exist_ok=True)
    wanted = {}
    for prompt, refs, aspect in jobs:
        tag = art.cache_tag(prompt, refs, aspect, model)
        if not (Path(cache_dir) / f"{tag}.png").exists():
            wanted.setdefault(tag, (prompt, list(refs), aspect))
    if not wanted:
        return "ready"
    if art.spent_today(spend, today) + INR_PER_IMAGE * len(wanted) > BUDGETS["image_inr_per_day"]:
        raise art.ImageBudget(f"image budget of ₹{BUDGETS['image_inr_per_day']} would be passed by {len(wanted)} batch pictures on {today}")
    if art.spent_month(spend, today) + INR_PER_IMAGE * len(wanted) > BUDGETS["image_inr_per_month"]:
        raise art.ImageBudget(f"monthly picture ceiling of ₹{BUDGETS['image_inr_per_month']} would be passed")
    key = key or secrets.get("GEMINI_API_KEY")
    tags = list(wanted)
    job = piece.ids.get("art_batch") or {}
    if job.get("tags") != tags:
        job = {"name": submit([wanted[t] for t in tags], piece.id, key, model, post, upload), "tags": tags, "tries": job.get("tries", 0) + 1}
        piece.ids["art_batch"] = job
    start = clock()
    while True:
        state, data = poll(job["name"], key, get)
        if state == "done":
            missing = collect(data, tags, cache_dir, spend, today, model)
            piece.ids.pop("art_batch", None)
            if missing:
                print(f"art batch: {len(missing)} picture(s) came back empty; they will be painted one by one", flush=True)
            return "ready"
        if state == "failed":
            piece.ids.pop("art_batch", None)
            if job["tries"] >= 2:
                raise BatchError("picture batch failed twice")
            job = {"name": submit([wanted[t] for t in tags], piece.id, key, model, post, upload), "tags": tags, "tries": job["tries"] + 1}
            piece.ids["art_batch"] = job
            continue
        if clock() - start >= wait_s:
            return "painting"
        sleep(POLL_S)
