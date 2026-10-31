"""Scripts through Claude's Message Batches (22 Oct 2026): the same Opus request as the synchronous writer, at half the price, back in a few
minutes (the API promises within 24 h). One batch per draft; a draft still cooking when the run cannot wait parks the piece as "writing"
and the next run collects it. The synchronous writer stays the fallback when this lane errors."""
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from . import secrets, writer
from .config import LOGS_DIR

WAIT_S = 600
POLL_S = 20
STALE_S = 2 * 3600          # 27 Oct 2026: a batch still running after this is cancelled and the draft is written directly (the buffer comes first)
BETAS = ["server-side-fallback-2026-07-01"]
LEDGER = LOGS_DIR / "write-batch.jsonl"


class WriteBatchError(Exception):
    pass


def _client(client=None):
    if client is not None:
        return client
    import anthropic
    return anthropic.Anthropic(api_key=secrets.get("ANTHROPIC_API_KEY"))


def _key(params: dict) -> str:
    return hashlib.sha1(json.dumps(params, sort_keys=True, default=str).encode()).hexdigest()[:16]


def _log(row: dict) -> None:
    try:
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
        with LEDGER.open("a") as f:
            f.write(json.dumps(row) + "\n")
    except OSError:
        pass


def write_piece(piece, sheet: dict, library: list, hashtags: dict, formula: str | None = None, *, client=None,
                spend: Path = writer.SPEND_FILE, today=None, wait_s: float = WAIT_S, sleep=time.sleep, clock=time.monotonic, patch_reasons=None,
                now=time.time) -> tuple:
    """("ready", script) once the draft is back and parsed; ("writing", None) while the batch still runs (piece.ids["write_batch"] keeps it).
    Raises WriteBatchError when the lane fails, so the caller can fall back to the synchronous writer."""
    from .config import today_pacific
    today = today or today_pacific()
    client = _client(client)
    if patch_reasons:
        params = writer.patch_params(piece, sheet, library, hashtags, piece.script, patch_reasons, formula)
    else:
        params = writer.claude_params(piece, sheet, library, hashtags, formula)
    key = _key(params)
    job = piece.ids.get("write_batch") or {}
    # A draft already ordered is collected, never re-ordered (27 Oct 2026): the request changes a little between runs (the latest hook
    # lessons, recent openers, prompt edits), and re-ordering on every change left the 2 Nov Shorts parked for a day, one unused batch per run.
    if not job or job.get("patch", False) != bool(patch_reasons):
        try:
            batch = client.beta.messages.batches.create(requests=[{"custom_id": piece.id, "params": params}], betas=BETAS)
        except Exception as e:
            raise WriteBatchError(f"batch create failed: {type(e).__name__}: {secrets.scrub(str(e))[:160]}") from e
        job = {"id": batch.id, "key": key, "patch": bool(patch_reasons), "tries": job.get("tries", 0) + 1, "at": time.time()}
        piece.ids["write_batch"] = job
        _log({"at": datetime.now(timezone.utc).isoformat(), "piece": piece.id, "batch": batch.id, "revise": bool(piece.topic.get("revise"))})
    start = clock()
    while True:
        try:
            status = client.beta.messages.batches.retrieve(job["id"]).processing_status
        except Exception as e:
            raise WriteBatchError(f"batch poll failed: {type(e).__name__}: {secrets.scrub(str(e))[:160]}") from e
        if status == "ended":
            piece.ids.pop("write_batch", None)
            for r in client.beta.messages.batches.results(job["id"]):
                if r.custom_id != piece.id:
                    continue
                if r.result.type != "succeeded":
                    raise WriteBatchError(f"batch result {r.result.type}: {secrets.scrub(str(getattr(r.result, 'error', '')))[:160]}")
                message = r.result.message
                writer.record_spend(message.usage, spend, today, factor=0.5 * writer.price_factor(params))
                if message.stop_reason == "refusal":
                    raise WriteBatchError("Claude refused the request")
                if message.stop_reason == "max_tokens":
                    raise WriteBatchError(f"Claude's script was cut off at {writer.MAX_TOKENS} tokens")
                text = next((b.text for b in message.content if getattr(b, "type", "") == "text"), "")
                return "ready", (writer.apply_patch(piece.script, text) if patch_reasons else writer._parse(text))
            raise WriteBatchError("batch ended without a result for this piece")
        if clock() - start >= wait_s:
            if now() - job.get("at", 0) >= STALE_S:              # a job from before this field existed counts as stale
                piece.ids.pop("write_batch", None)
                try:
                    client.beta.messages.batches.cancel(job["id"])
                except Exception:
                    pass
                raise WriteBatchError(f"batch {job['id']} still running after {STALE_S // 3600} hours; writing directly")
            return "writing", None
        sleep(POLL_S)
