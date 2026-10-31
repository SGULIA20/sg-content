"""The script writer: Claude Opus 5.5 with a fixed output schema; Gemini writes when Claude refuses, fails or the day's budget is spent (spec §3 step 3)."""
import json
import re
from datetime import date
from pathlib import Path

from . import costs, gemini, schema, secrets
from .config import BUDGETS, CONTENT_DIR, LOGS_DIR, today_ist, today_pacific
from .pieces import Piece

MODEL = "claude-opus-5-5"
SONNET = "claude-sonnet-5-5"     # first draft of an extra, news or Top 10 Reel (founder, 31 Oct 2026: "use sonnet for extras and news, quality should not deteriorate")
GEMINI_MODEL = "gemini-3.8-flash"
USD_PER_M_IN, USD_PER_M_OUT = 4.0, 20.0
SONNET_VS_OPUS = 0.5       # Sonnet 5.5 is $2 / $10 per million tokens against Opus 5.5's $4 / $20 (checked 24 Oct 2026), so the same meter at half the factor
SPEND_FILE = LOGS_DIR / "claude-spend.json"
WRITER_FOR = {"short": "claude", "long": "claude"}      # Claude writes everything; Gemini only as the fallback (founder, 20 Oct: the free model wrote weak stories)
MAX_TOKENS = 64000
GEMINI_MAX_TOKENS = 32000
PATCH_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["scenes"],
    "properties": {
        "scenes": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["index", "vo"],
                                              "properties": {"index": {"type": "integer"}, "vo": {"type": "string"}, "label": {"type": "string"},
                                                             "card_big_number": {"type": "string"}, "card_line": {"type": "string"}}}},
        "fields": {"type": "object", "additionalProperties": False,
                   "properties": {"title": {"type": "string"}, "hook": {"type": "string"}, "end_question": {"type": "string"},
                                  "youtube_title": {"type": "string"}, "youtube_description": {"type": "string"},
                                  "instagram_caption": {"type": "string"}, "threads_text": {"type": "string"}}},
    },
}
PATCH_TRIES = 2          # patch attempts per topic before a full rewrite


def model_for(piece) -> str:
    """Sonnet writes only the FIRST draft of a Learning with SG extra, news or Top 10 Reel; every later draft and every patch of it is Opus,
    so a draft that fails any check (numbers, jargon, length, hook) is redone by the stronger model and quality never drops below today's."""
    t = {**((piece.topic or {}).get("preset") or {}), **(piece.topic or {})}
    news_like = piece.channel == "sglearning" and piece.kind == "short" and bool(t.get("news") or t.get("extra") or t.get("roundup"))
    return SONNET if news_like and not piece.ids.get("drafts") and not piece.topic.get("revise") else MODEL


def price_factor(params: dict) -> float:
    return SONNET_VS_OPUS if params.get("model") == SONNET else 1.0


def patchable(reasons: list) -> bool:
    """True when every failed check can be fixed by rewriting a few scenes: an unsourced number, banned wording, a missing label, or a script
    that is OVER its word limit. Too short, a wrong format or a copied script still gets a full rewrite."""
    if not reasons:
        return False
    for r in reasons:
        if r.startswith(("numbers without a source", "advice", "label", "card", "figures", "jargon")):
            continue
        m = re.match(r"length: (\d+) words, allowed (\d+)-(\d+)", r)
        if m and int(m.group(1)) > int(m.group(3)):
            continue
        return False
    return True


def _numbered(script: dict) -> dict:
    """The draft with each scene's 0-based index written on it, so the model names the right scene (a live test patched scene 3 instead of 2)."""
    import copy
    out = copy.deepcopy(script)
    out["scenes"] = [{"index": i, **sc} for i, sc in enumerate(out.get("scenes", []))]
    return out


def patch_params(piece, sheet, library, hashtags, previous: dict, reasons: list, formula=None) -> dict:
    """The same writer rules and fact sheet as the full draft, plus the failed draft and the checks it failed: the model returns only what changes."""
    base = claude_params(piece, sheet, library, hashtags, formula)
    note = ("\n\nPATCH MODE. Your previous draft is below. It failed these automatic checks:\n- " + "\n- ".join(reasons) +
            "\n\nReturn ONLY the scenes whose narration must change (by index, with the corrected `vo`; add `label` only if a label was missing; "
            "for a scene drawn as a news card also return `card_big_number` (a figure the new `vo` says, written the same way, or \"\" for none) and, "
            "if it must change, `card_line`) and, in `fields`, "
            "any other text that must change. Fix the problems named above and nothing else. Do not add or remove scenes, keep the story, tone and facts, "
            "use only numbers that appear in the FACT_SHEET, and when trimming for length cut the weakest sentences, never the twist or the closing question.\n"
            "Scene `index` is 0-based and shown on every scene below.\nPREVIOUS DRAFT:\n" + json.dumps(_numbered(previous), ensure_ascii=False))
    base["messages"] = [{"role": "user", "content": base["messages"][0]["content"] + note}]
    base["max_tokens"] = 8000
    base["output_config"] = {"effort": "medium", "format": {"type": "json_schema", "schema": schema.api_schema(PATCH_SCHEMA)}}
    return base


def apply_patch(previous: dict, raw: str) -> dict:
    """The previous draft with the returned scenes and fields replaced; validated against the full schema."""
    import copy
    try:
        data = json.loads(FENCE.sub("", (raw or "").strip()))
    except ValueError as e:
        raise WriterError(f"patch reply is not valid JSON ({e})") from e
    problems = schema.validate(data, PATCH_SCHEMA)
    if problems:
        raise WriterError("patch does not match its schema: " + "; ".join(problems[:3]))
    out = copy.deepcopy(previous)
    n = len(out.get("scenes", []))
    for fix in data["scenes"]:
        if not 0 <= fix["index"] < n:
            raise WriterError(f"patch names scene {fix['index']} of {n}")
        out["scenes"][fix["index"]]["vo"] = fix["vo"]
        if fix.get("label"):
            out["scenes"][fix["index"]]["label"] = fix["label"]
        card = (out["scenes"][fix["index"]].get("visual") or {}).get("card")
        if card is not None:                                     # a news card follows its corrected line (31 Oct 2026)
            if "card_big_number" in fix:
                card["big_number"] = fix["card_big_number"]
            if fix.get("card_line"):
                card["line"] = fix["card_line"]
    f = data.get("fields") or {}
    caps = out.setdefault("captions", {})
    for key, setter in (("title", lambda v: out.__setitem__("title", v)), ("hook", lambda v: out.__setitem__("hook", v)),
                        ("end_question", lambda v: out.__setitem__("end_question", v)),
                        ("youtube_title", lambda v: caps["youtube"].__setitem__("title", v)), ("youtube_description", lambda v: caps["youtube"].__setitem__("description", v)),
                        ("instagram_caption", lambda v: caps["instagram"].__setitem__("caption", v)), ("threads_text", lambda v: caps["threads"].__setitem__("text", v))):
        if f.get(key):
            setter(f[key])
    problems = schema.validate(out)
    if problems:
        raise WriterError("patched script does not match the schema: " + "; ".join(problems[:3]))
    return out


FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


class WriterError(Exception):
    pass


def system_prompt(channel: str, root: Path = CONTENT_DIR) -> str:
    base = (Path(root) / "prompts" / "writer-system.txt").read_text()
    formula = (Path(root) / "prompts" / f"formula-{channel}.txt").read_text()
    return base.replace("{formula}", formula)


def hook_lessons(channel: str, path: Path | None = None) -> dict:
    """Last month's best and worst openings on this channel with their Instagram numbers (engine/whatworks.py, weekly), as examples
    of what made people stay or swipe away in the first 3 seconds. Data, not instructions; empty until there are enough Shorts."""
    try:
        data = json.loads(Path(path or LOGS_DIR / "hook-lessons.json").read_text())
    except (FileNotFoundError, ValueError):
        return {}
    got = data.get(channel) or {}
    return {"note": "Openings of our own recent Shorts with their Instagram views and the share who swiped away in the first 3 seconds. "
                    "Learn from what made people stay; never copy a line.", **got} if got else {}


def _user_message(piece: Piece, sheet: dict, library: list, hashtags: dict) -> str:
    return json.dumps({
        "piece": {"id": piece.id, "channel": piece.channel, "kind": piece.kind, "publish_day": piece.publish_day.isoformat(),
                  "target_minutes": piece.topic.get("target_minutes"), "topic": piece.topic},
        "FACT_SHEET": sheet,
        "CLAIMS_LIBRARY": [{"text": e.get("text"), "number": e.get("number"), "unit": e.get("unit"), "source": e.get("source_url")} for e in library],
        "ALLOWED_HASHTAGS": hashtags.get(piece.channel, {}),
        "OPENINGS_THAT_WORKED": hook_lessons(piece.channel),
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
    costs.add(usd=cost_usd(usage) * factor)
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
    return {"model": model_for(piece), "max_tokens": MAX_TOKENS,
            "output_config": {"effort": "high", "format": {"type": "json_schema", "schema": schema.api_schema(schema.PIECE_SCHEMA)}},
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            "messages": [{"role": "user", "content": _user_message(piece, sheet, library, hashtags)}]}


def _claude(piece, sheet, library, hashtags, formula, client, spend, today) -> dict:
    import anthropic
    client = client or anthropic.Anthropic(api_key=secrets.get("ANTHROPIC_API_KEY"))
    params = claude_params(piece, sheet, library, hashtags, formula)
    with client.beta.messages.stream(                              # streamed: a 12-14 minute long needs more than 16k tokens
        **params, betas=["server-side-fallback-2026-07-01"], fallbacks="default",
    ) as stream:
        response = stream.get_final_message()
    record_spend(response.usage, spend, today, factor=price_factor(params))
    if response.stop_reason == "refusal":
        raise WriterError("Claude refused the request")
    if response.stop_reason == "max_tokens":
        raise WriterError(f"Claude's script was cut off at {MAX_TOKENS} tokens")
    text = next((b.text for b in response.content if getattr(b, "type", "") == "text"), "")
    return _parse(text)


def _claude_patch(piece, sheet, library, hashtags, formula, client, spend, today, reasons) -> dict:
    import anthropic
    client = client or anthropic.Anthropic(api_key=secrets.get("ANTHROPIC_API_KEY"))
    params = patch_params(piece, sheet, library, hashtags, piece.script, reasons, formula)
    with client.beta.messages.stream(**params, betas=["server-side-fallback-2026-07-01"], fallbacks="default") as stream:
        response = stream.get_final_message()
    record_spend(response.usage, spend, today, factor=price_factor(params))
    if response.stop_reason in ("refusal", "max_tokens"):
        raise WriterError(f"patch ended with {response.stop_reason}")
    text = next((b.text for b in response.content if getattr(b, "type", "") == "text"), "")
    return apply_patch(piece.script, text)


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
        reasons = (piece.topic.get("revise") or "").split("; ") if piece.topic.get("revise") else []
        if piece.script and patchable(reasons) and piece.topic.get("patch_tries", 0) < PATCH_TRIES:
            try:
                if batch_fn is not None:
                    state, script = batch_fn(piece, sheet, library, hashtags, formula, client=client, spend=spend, today=today, patch_reasons=reasons)
                    if state == "writing":
                        return {"script": None, "writer": "claude", "note": "", "state": "writing"}
                else:
                    script = _claude_patch(piece, sheet, library, hashtags, formula, client, spend, today, reasons)
                piece.topic["patch_tries"] = piece.topic.get("patch_tries", 0) + 1
                return {"script": script, "writer": "claude", "note": "patched: " + "; ".join(reasons)[:120], "state": "ready"}
            except Exception as e:                                # a patch is an optimisation: the full rewrite is next
                print(f"patch failed ({type(e).__name__}: {secrets.scrub(str(e))[:120]}); rewriting the whole script", flush=True)
                piece.topic["patch_tries"] = PATCH_TRIES
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
