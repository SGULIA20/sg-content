"""One door to Gemini generateContent with retries. Key: GEMINI_API_KEY from engine.secrets."""
import http.client
import json
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from . import secrets
from .config import LOGS_DIR

API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
TRIES = 3
WAIT_S = 60
LOG_FILE = LOGS_DIR / "gemini-calls.jsonl"     # 3 Nov 2026: one line per Gemini request, so the cost can be read per step


class GeminiError(Exception):
    pass


def _post(url: str, body: dict, key: str) -> tuple:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "x-goog-api-key": key})
    try:
        with urllib.request.urlopen(req, timeout=300, context=secrets.ssl_context()) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        raw = e.read().decode(errors="replace")
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, {"error": {"message": raw[:300]}}
    except (http.client.HTTPException, ConnectionError, TimeoutError, urllib.error.URLError, OSError) as e:
        return 599, {"error": {"message": f"connection interrupted: {type(e).__name__}"}}


def _caller() -> str:
    """The engine step that asked, e.g. "research.fact_sheet", so the log says which step spent the credit."""
    f = sys._getframe(2)
    while f is not None:
        name = f.f_globals.get("__name__", "")
        if name and name != __name__:
            return f"{name.split('.')[-1]}.{f.f_code.co_name}"
        f = f.f_back
    return "?"


def entry(model: str, caller: str, status: int, attempt: int, data: dict, body: dict) -> dict:
    """One request's record: tokens, whether Google Search ran and how many queries it made (search is billed per query)."""
    usage = (data or {}).get("usageMetadata") or {}
    cands = (data or {}).get("candidates") or []
    grounding = (cands[0].get("groundingMetadata") or {}) if cands else {}
    tools = body.get("tools") or []
    return {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "model": model, "caller": caller, "status": status,
            "attempt": attempt, "in": usage.get("promptTokenCount", 0), "out": usage.get("candidatesTokenCount", 0),
            "thought": usage.get("thoughtsTokenCount", 0), "search": any(isinstance(t, dict) and "google_search" in t for t in tools),
            "search_queries": len(grounding.get("webSearchQueries") or []),
            "modalities": (body.get("generationConfig") or {}).get("responseModalities") or []}


def write(record: dict, path: Path | None = None) -> None:
    """Appends one line. Logging never stops a generation: a disk error is ignored."""
    try:
        path = Path(path or LOG_FILE)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        pass


def usage_summary(day: str, path: Path | None = None) -> str:
    """Per step for one UTC day: requests, failed attempts, tokens in and out, search queries."""
    rows = []
    try:
        for line in Path(path or LOG_FILE).read_text().splitlines():
            if line.strip():
                rows.append(json.loads(line))
    except (OSError, ValueError):
        return f"no Gemini log for {day}"
    rows = [r for r in rows if str(r.get("at", "")).startswith(day)]
    if not rows:
        return f"no Gemini calls on {day}"
    calls, fails, tin, tout, searches = Counter(), Counter(), Counter(), Counter(), Counter()
    for r in rows:
        c = r.get("caller", "?")
        calls[c] += 1
        if r.get("status") != 200:
            fails[c] += 1
        tin[c] += r.get("in", 0) or 0
        tout[c] += (r.get("out", 0) or 0) + (r.get("thought", 0) or 0)
        searches[c] += r.get("search_queries", 0) or 0
    lines = [f"Gemini calls on {day} (UTC): {len(rows)} requests, {sum(fails.values())} failed attempts"]
    for c, n in calls.most_common():
        lines.append(f"  {c}: {n} requests ({fails[c]} failed), tokens in {tin[c]:,} out {tout[c]:,}, search queries {searches[c]}")
    return "\n".join(lines)


def generate(model: str, body: dict, key: str | None = None, post=_post) -> dict:
    key = key or secrets.get("GEMINI_API_KEY")
    url = API.format(model=model)
    last = ""
    caller = _caller()
    for attempt in range(TRIES):
        status, data = post(url, body, key)
        if post is _post:                      # fake posts in tests are not logged
            write(entry(model, caller, status, attempt, data, body))
        if status == 200:
            return data
        last = secrets.scrub(str((data.get("error") or {}).get("message", ""))[:300])
        if status in (429, 500, 503, 599) and attempt < TRIES - 1:
            time.sleep(WAIT_S if status in (429, 503) else 5)
            continue
        break
    raise GeminiError(f"{model} failed ({status}): {last}")


def text(response: dict) -> str:
    for cand in response.get("candidates", []):
        for part in (cand.get("content") or {}).get("parts", []):
            if "text" in part:
                return part["text"]
    return ""


if __name__ == "__main__":                     # python -m engine.gemini 2026-11-03  (UTC day; default today)
    from datetime import date
    print(usage_summary(sys.argv[1] if len(sys.argv) > 1 else date.today().isoformat()))
