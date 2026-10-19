"""Grounded research: one Gemini call with Google Search returns a fact sheet; clean() keeps only sourced, labelled, fresh facts (spec §3 step 2)."""
import json
import re
from datetime import date, timedelta
from pathlib import Path

from . import gemini
from .config import CONTENT_DIR

MODEL = "gemini-3.8-flash"
MYTH_LABELS = {"scripture", "archaeology", "disputed", "legend"}
FINANCE_LABELS = {"reported", "official", "analyst-view"}
NEWS_MAX_AGE_DAYS = 7
FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def _prompt(channel: str, topic: dict, today: date, root: Path = CONTENT_DIR) -> str:
    name = "research-finance.txt" if channel == "sglearning" else "research-myth.txt"
    tpl = (Path(root) / "prompts" / name).read_text()
    fields = {"today": today.isoformat(), "title": topic.get("title") or topic.get("title_hi", ""), "link": topic.get("link", ""),
              "summary": topic.get("summary", ""), "place": topic.get("place", ""), "hooks": "; ".join(topic.get("hooks", [])),
              "notes": topic.get("notes", ""), "allowed_sources": ", ".join(str(s) for s in topic.get("allowed_sources", []))}
    return tpl.format(**fields)


def _parse(raw: str) -> dict:
    raw = FENCE.sub("", raw.strip())
    data = json.loads(raw)
    return {"facts": list(data.get("facts") or []), "summary": str(data.get("summary") or "")}


def fact_sheet(topic: dict, channel: str, *, key: str | None = None, ask=gemini.generate, today: date | None = None, root: Path = CONTENT_DIR) -> dict:
    today = today or date.today()
    body = {"contents": [{"parts": [{"text": _prompt(channel, topic, today, root)}]}],
            "tools": [{"google_search": {}}],
            "generationConfig": {"temperature": 0, "responseMimeType": "application/json", "maxOutputTokens": 8000}}
    response = ask(MODEL, body, key)
    return clean(_parse(gemini.text(response)), channel, today, news=(channel == "sglearning" and bool(topic.get("link"))))


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
