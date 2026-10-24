"""The script writer: Claude Opus 5.5 with a fixed output schema; Gemini writes when Claude refuses, fails or the day's budget is spent (spec §3 step 3)."""
import json
import re
from datetime import date
from pathlib import Path

from . import gemini, schema, secrets
from .config import BUDGETS, CONTENT_DIR, LOGS_DIR, today_ist, today_pacific
from .pieces import Piece

MODEL = "claude-opus-5-5"
GEMINI_MODEL = "gemini-3.8-flash"
USD_PER_M_IN, USD_PER_M_OUT = 4.0, 20.0
SPEND_FILE = LOGS_DIR / "claude-spend.json"
WRITER_FOR = {"short": "claude", "long": "claude"}      # Claude writes everything; Gemini only as the fallback (founder, 20 Oct: the free model wrote weak stories)
MAX_TOKENS = 64000
GEMINI_MAX_TOKENS = 32000
FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


class WriterError(Exception):
    pass


def system_prompt(channel: str, root: Path = CONTENT_DIR) -> str:
    base = (Path(root) / "prompts" / "writer-system.txt").read_text()
    formula = (Path(root) / "prompts" / f"formula-{channel}.txt").read_text()
    return base.replace("{formula}", formula)


def _user_message(piece: Piece, sheet: dict, library: list, hashtags: dict) -> str:
    return json.dumps({
        "piece": {"id": piece.id, "channel": piece.channel, "kind": piece.kind, "publish_day": piece.publish_day.isoformat(),
                  "target_minutes": piece.topic.get("target_minutes"), "topic": piece.topic},
        "FACT_SHEET": sheet,
        "CLAIMS_LIBRARY": [{"text": e.get("text"), "number": e.get("number"), "unit": e.get("unit"), "source": e.get("source_url")} for e in library],
        "ALLOWED_HASHTAGS": hashtags.get(piece.channel, {}),
        "REVISION": (f"Your previous draft was rejected: {piece.topic['revise']}. Rewrite the same piece, same facts, trimmed to the middle of the allowed range "
                     f"(count the words in `vo` yourself before answering).") if piece.topic.get("revise") else "",
    }, ensure_ascii=False, indent=1, default=lambda o: o.isoformat() if hasattr(o, "isoformat") else str(o))


def _read_spend(path: Path) -> dict:
    try:
        return json.loads(Path(path).read_text())
    except (FileNotFoundError, ValueError):
        return {}


def spent_today(path: Path = SPEND_FILE, today: date | None = None) -> float:
    today = today or today_pacific()
    return float(_read_spend(path).get(today.isoformat(), {}).get("usd", 0.0))


def spent_month(path: Path = SPEND_FILE, today: date | None = None) -> float:
    today = today or today_pacific()
    return float(sum(v.get("usd", 0.0) for k, v in _read_spend(path).items() if k.startswith(today.strftime("%Y-%m"))))


def cost_usd(usage) -> float:
    return getattr(usage, "input_tokens", 0) * USD_PER_M_IN / 1e6 + getattr(usage, "output_tokens", 0) * USD_PER_M_OUT / 1e6


def record_spend(usage, path: Path = SPEND_FILE, today: date | None = None, factor: float = 1.0) -> float:
    today = today or today_pacific()
    data = _read_spend(path)
    day = data.setdefault(today.isoformat(), {"usd": 0.0, "requests": 0})
    day["usd"] = round(day["usd"] + cost_usd(usage) * factor, 6)
    day["requests"] += 1
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, indent=1))
    return day["usd"]


def _parse(raw: str) -> dict:
    try:
        data = json.loads(FENCE.sub("", (raw or "").strip()))
    except ValueError as e:                                       # cut-off or malformed reply: a failed piece, never a crashed run
        raise WriterError(f"script reply is not valid JSON ({e}); {len(raw or '')} characters received") from e
    problems = schema.validate(data)
    if problems:
        raise WriterError("script does not match the schema: " + "; ".join(problems[:5]))
    return data


def claude_params(piece, sheet, library, hashtags, formula=None) -> dict:
    """The one Opus request both lanes send: the synchronous stream and the half-price batch."""
    system = system_prompt(piece.channel) if formula is None else system_prompt(piece.channel).replace(
        (CONTENT_DIR / "prompts" / f"formula-{piece.channel}.txt").read_text(), formula)
    return {"model": MODEL, "max_tokens": MAX_TOKENS,
            "output_config": {"effort": "high", "format": {"type": "json_schema", "schema": schema.api_schema(schema.PIECE_SCHEMA)}},
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            "messages": [{"role": "user", "content": _user_message(piece, sheet, library, hashtags)}]}


def _claude(piece, sheet, library, hashtags, formula, client, spend, today) -> dict:
    import anthropic
    client = client or anthropic.Anthropic(api_key=secrets.get("ANTHROPIC_API_KEY"))
    with client.beta.messages.stream(                              # streamed: a 12-14 minute long needs more than 16k tokens
        **claude_params(piece, sheet, library, hashtags, formula), betas=["server-side-fallback-2026-07-01"], fallbacks="default",
    ) as stream:
        response = stream.get_final_message()
    record_spend(response.usage, spend, today)
    if response.stop_reason == "refusal":
        raise WriterError("Claude refused the request")
    if response.stop_reason == "max_tokens":
        raise WriterError(f"Claude's script was cut off at {MAX_TOKENS} tokens")
    text = next((b.text for b in response.content if getattr(b, "type", "") == "text"), "")
    return _parse(text)


def _gemini(piece, sheet, library, hashtags, formula, ask) -> dict:
    prompt = system_prompt(piece.channel) + "\n\nSCHEMA (return exactly this shape):\n" + json.dumps(schema.PIECE_SCHEMA) + \
        "\n\nINPUT:\n" + _user_message(piece, sheet, library, hashtags)
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.7, "responseMimeType": "application/json", "maxOutputTokens": GEMINI_MAX_TOKENS}}
    return _parse(gemini.text(ask(GEMINI_MODEL, body, None)))


def write(piece: Piece, sheet: dict, library: list, hashtags: dict, formula: str | None = None, client=None,
          gemini_ask=gemini.generate, spend: Path = SPEND_FILE, today: date | None = None, batch_fn=None) -> dict:
    """Returns {"script": <piece JSON>, "writer": "claude" | "gemini", "note": str}; with a batch lane, {"state": "writing"} while the
    draft is still cooking (the caller parks the piece and comes back)."""
    today = today or today_pacific()
    note = ""
    if WRITER_FOR.get(piece.kind) == "gemini":
        note = "shorts are written by the free Gemini model (founder, 20 Oct 2026)"
    elif spent_month(spend, today) >= BUDGETS["claude_usd_per_month"]:
        note = f"Claude's monthly ceiling of ${BUDGETS['claude_usd_per_month']:.0f} is reached; Gemini writes until next month"
    elif spent_today(spend, today) >= BUDGETS["claude_usd_per_day"]:
        note = "claude budget spent for the day"
    else:
        if batch_fn is not None:
            try:
                state, script = batch_fn(piece, sheet, library, hashtags, formula, client=client, spend=spend, today=today)
                if state == "writing":
                    return {"script": None, "writer": "claude", "note": "", "state": "writing"}
                return {"script": script, "writer": "claude", "note": "", "state": "ready"}
            except Exception as e:                                # the batch lane is an optimisation: the synchronous request is next
                print(f"claude batch lane failed ({type(e).__name__}: {secrets.scrub(str(e))[:120]}); writing synchronously", flush=True)
        try:
            return {"script": _claude(piece, sheet, library, hashtags, formula, client, spend, today), "writer": "claude", "note": ""}
        except Exception as e:                                    # refusal, API error after SDK retries, schema mismatch
            note = f"claude failed: {type(e).__name__}: {secrets.scrub(str(e))[:200]}"
            print(note, flush=True)
    try:
        return {"script": _gemini(piece, sheet, library, hashtags, formula, gemini_ask), "writer": "gemini", "note": note}
    except Exception as e:                                        # both writers failed: the caller records it on the piece
        raise WriterError(f"{note + '; ' if note else ''}gemini failed: {type(e).__name__}: {secrets.scrub(str(e))[:200]}") from e
