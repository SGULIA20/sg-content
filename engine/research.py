"""Grounded research: one Gemini call with Google Search returns a fact sheet; clean() keeps only sourced, labelled, fresh facts (spec §3 step 2)."""
import json
import re
import urllib.error
from datetime import date, timedelta
from pathlib import Path

from . import gemini
from .config import CONTENT_DIR

MODEL = "gemini-3.8-flash"
MYTH_LABELS = {"scripture", "archaeology", "disputed", "legend"}
FINANCE_LABELS = {"reported", "official", "analyst-view"}
NEWS_MAX_AGE_DAYS = 7
MAX_OUTPUT_TOKENS = 20000
FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


class ResearchError(Exception):
    pass


def _prompt(channel: str, topic: dict, today: date, root: Path = CONTENT_DIR) -> str:
    name = "research-finance.txt" if channel == "sglearning" else "research-myth.txt"
    tpl = (Path(root) / "prompts" / name).read_text()
    fields = {"today": today.isoformat(), "title": topic.get("title") or topic.get("title_hi", ""), "link": topic.get("link", ""),
              "summary": topic.get("summary", ""), "place": topic.get("place", ""), "hooks": "; ".join(topic.get("hooks", [])),
              "notes": topic.get("notes", ""), "allowed_sources": ", ".join(str(s) for s in topic.get("allowed_sources", []))}
    return tpl.format(**fields)


def _parse(raw: str) -> dict:
    raw = FENCE.sub("", (raw or "").strip())
    if not raw:
        raise ResearchError("empty reply from the research model")
    try:
        data = json.loads(raw)
    except ValueError:
        start, end = raw.find("{"), raw.rfind("}")          # the model wrapped the JSON in prose
        if start < 0 or end <= start:
            raise ResearchError("no JSON object in the research reply: " + raw[:120])
        data = json.loads(raw[start:end + 1])
    return {"facts": list(data.get("facts") or []), "summary": str(data.get("summary") or "")}


def fact_sheet(topic: dict, channel: str, *, key: str | None = None, ask=gemini.generate, today: date | None = None, root: Path = CONTENT_DIR) -> dict:
    today = today or date.today()
    body = {"contents": [{"parts": [{"text": _prompt(channel, topic, today, root)}]}],
            "tools": [{"google_search": {}}],
            "generationConfig": {"temperature": 0, "maxOutputTokens": MAX_OUTPUT_TOKENS}}   # no JSON mode: with google_search it returns an empty candidate
    raw = ""
    for _attempt in range(2):                                   # the model's own thinking can eat the budget and leave no text; one retry
        raw = gemini.text(ask(MODEL, body, key))
        if raw.strip():
            break
    try:
        sheet = _parse(raw)
    except (ValueError, ResearchError):
        sheet = _repair(raw, key, ask)
    return clean(sheet, channel, today, news=(channel == "sglearning" and bool(topic.get("link"))))


def _status(url: str) -> int:
    import urllib.request
    from . import secrets
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "Mozilla/5.0 (sg-content fact check)"})
    try:
        with urllib.request.urlopen(req, timeout=15, context=secrets.ssl_context()) as r:
            return r.status
    except urllib.error.HTTPError as e:
        if e.code in (403, 405):                                # some sites refuse HEAD; try a GET of the first bytes
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (sg-content fact check)", "Range": "bytes=0-512"})
                with urllib.request.urlopen(req, timeout=15, context=secrets.ssl_context()) as r:
                    return r.status
            except Exception:
                return e.code
        return e.code
    except Exception:
        return 0


def verify_urls(sheet: dict, fetch=_status) -> dict:
    """Drops facts whose source URL does not answer 2xx/3xx: an invented or dead link never reaches the writer."""
    cache, kept = {}, []
    for f in sheet.get("facts", []):
        url = f.get("source_url", "")
        if url not in cache:
            cache[url] = fetch(url)
        if 200 <= int(cache[url] or 0) < 400:
            kept.append(f)
        else:
            print(f"dropped fact with unreachable source ({cache[url]}): {url}", flush=True)
    return {**sheet, "facts": kept}


def _repair(raw: str, key, ask) -> dict:
    """A grounded reply that is not valid JSON is converted by a plain JSON-mode call; every URL and number must survive."""
    if not (raw or "").strip():
        raise ResearchError("empty reply from the research model")
    prompt = ("Convert the research notes below into valid JSON with exactly this shape and nothing else: "
              '{"facts": [{"text": str, "number": number or null, "unit": str, "source_url": str, "source_name": str, "source_date": "YYYY-MM-DD", '
              '"quote": str, "label": str}], "summary": str}. Keep every fact, URL, date and number unchanged; fix only the syntax.\n\nNOTES:\n' + raw)
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0, "responseMimeType": "application/json", "maxOutputTokens": 8000}}
    return _parse(gemini.text(ask(MODEL, body, key)))


def _date(s) -> date | None:
    try:
        return date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


def clean(sheet: dict, channel: str, today: date, news: bool = False) -> dict:
    kept = []
    for f in sheet.get("facts", []):
        url = str(f.get("source_url") or "")
        if not url.startswith("http"):
            continue
        label = str(f.get("label") or "").strip().lower()
        if channel == "arthvan":
            if label not in MYTH_LABELS:
                continue
        else:
            if label not in FINANCE_LABELS:
                label = "reported"
            if news:
                d = _date(f.get("source_date"))
                if d is None or today - d > timedelta(days=NEWS_MAX_AGE_DAYS):
                    continue
        number = f.get("number")
        try:
            number = float(number) if number not in (None, "", "null") else None
        except (TypeError, ValueError):
            number = None
        kept.append({**f, "label": label, "number": number, "source_url": url})
    return {"facts": kept, "summary": sheet.get("summary", "")}
