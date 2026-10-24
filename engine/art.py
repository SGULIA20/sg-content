"""Pictures: painted scenes, the founder's avatar library, and licensed real-site photos from Wikimedia Commons (spec §3 step 6, §5).

python -m engine.art --avatar-library        generates every pose in content/avatar-library.yaml that is not yet in assets/avatar/
"""
import argparse
import base64
import hashlib
import json
import re
import sys
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

import yaml

from . import gemini, secrets
from .config import ASSETS_DIR, BUDGETS, CACHE_DIR, CONTENT_DIR, LOGS_DIR, today_ist, today_pacific

MODEL = "gemini-3.1-flash-lite-image"
INR_PER_IMAGE = {"gemini-3.1-flash-lite-image": 3.0, "gemini-3.1-flash-image": 6.0, "gemini-2.5-flash-image": 3.5}
SPEND_FILE = LOGS_DIR / "image-spend.json"
LIBRARY_FILE = CONTENT_DIR / "avatar-library.yaml"
FREE_LICENCES = ("CC0", "CC BY 4.0", "CC BY-SA 4.0", "CC BY 3.0", "CC BY-SA 3.0", "CC BY 2.0", "CC BY-SA 2.0", "Public domain")
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
MIME = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}


class ImageError(Exception):
    pass


class ImageBudget(ImageError):
    pass


def _read(path: Path) -> dict:
    try:
        return json.loads(Path(path).read_text())
    except (FileNotFoundError, ValueError):
        return {}


def spent_today(spend: Path = SPEND_FILE, today: date | None = None) -> float:
    today = today or today_pacific()
    return float(_read(spend).get(today.isoformat(), {}).get("inr", 0.0))


def spent_month(spend: Path = SPEND_FILE, today: date | None = None) -> float:
    today = today or today_pacific()
    return float(sum(v.get("inr", 0.0) for k, v in _read(spend).items() if k.startswith(today.strftime("%Y-%m"))))


def cache_tag(prompt: str, refs: list, aspect: str, model: str = MODEL) -> str:
    return hashlib.sha1(f"{model}|{aspect}|{prompt}|{'|'.join(Path(r).name for r in refs)}".encode()).hexdigest()


def _record(spend: Path, today: date, inr: float) -> None:
    data = _read(spend)
    day = data.setdefault(today.isoformat(), {"inr": 0.0, "requests": 0})
    day["inr"] = round(day["inr"] + inr, 2); day["requests"] += 1
    Path(spend).parent.mkdir(parents=True, exist_ok=True)
    Path(spend).write_text(json.dumps(data, indent=1))


def _image_from(response: dict) -> bytes | None:
    for c in response.get("candidates", []):
        for p in (c.get("content") or {}).get("parts", []):
            blob = p.get("inlineData") or p.get("inline_data")
            if blob and blob.get("data"):
                return base64.b64decode(blob["data"])
    return None


def paint(prompt: str, out: Path, *, refs: list = (), key: str | None = None, model: str = MODEL, aspect: str = "9:16",
          cache_dir: Path = CACHE_DIR / "art", spend: Path = SPEND_FILE, post=gemini._post, today: date | None = None) -> Path:
    """One picture into `out`. Cached by model, prompt, aspect and reference file names; about ₹3 a call."""
    today = today or today_pacific()
    out, cache_dir = Path(out), Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    tag = cache_tag(prompt, refs, aspect, model)
    cached = cache_dir / f"{tag}.png"
    if not cached.exists():
        if spent_today(spend, today) >= BUDGETS["image_inr_per_day"]:
            raise ImageBudget(f"image budget of ₹{BUDGETS['image_inr_per_day']} reached for {today}")
        if spent_month(spend, today) >= BUDGETS["image_inr_per_month"]:
            raise ImageBudget(f"monthly picture ceiling of ₹{BUDGETS['image_inr_per_month']} reached ({today.strftime('%B')})")
        key = key or secrets.get("GEMINI_API_KEY")
        parts = [{"inlineData": {"mimeType": MIME.get(Path(r).suffix.lower(), "image/png"), "data": base64.b64encode(Path(r).read_bytes()).decode()}} for r in refs]
        parts.append({"text": prompt})
        body = {"contents": [{"parts": parts}], "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": aspect}}}
        response = gemini.generate(model, body, key, post=post)
        image = _image_from(response)
        if not image:
            raise ImageError("no picture in the reply: " + json.dumps(response)[:200])
        _record(spend, today, INR_PER_IMAGE.get(model, 6.0))
        cached.write_bytes(image)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(cached.read_bytes())
    return out


LOOKS = (("claymation", "claymation"), ("indian comic", "indian-comic"), ("doodle", "doodle"))


def look(channel: str, root: Path = CONTENT_DIR) -> str:
    """Short name of the channel's current picture style, stamped on each piece so the weekly report can compare looks."""
    style = (Path(root) / "prompts" / f"style-{channel}.txt").read_text().lower()
    return next((name for word, name in LOOKS if word in style), "other")


def style_prompt(channel: str, scene_prompt: str, root: Path = CONTENT_DIR) -> str:
    style = (Path(root) / "prompts" / f"style-{channel}.txt").read_text().strip()
    return f"{scene_prompt.strip()}. {style}"


def load_library(path: Path = LIBRARY_FILE) -> dict:
    return yaml.safe_load(Path(path).read_text()) or {}


def avatar(pose_key: str, *, assets: Path = ASSETS_DIR, library: Path = LIBRARY_FILE, root: Path = CONTENT_DIR, **kw) -> Path:
    """The founder's likeness in one pose, generated once into assets/avatar/<pose>.png and reused forever."""
    lib = load_library(library)
    if pose_key not in lib:
        raise KeyError(f"unknown avatar pose {pose_key!r}; known: {', '.join(sorted(lib))}")
    out = Path(assets) / "avatar" / f"{pose_key}.png"
    if out.exists():
        return out
    spec = lib[pose_key]
    refs = [Path(assets) / "reference" / r for r in spec["refs"]]
    tpl_path = Path(root) / "prompts" / "avatar.txt"
    tpl = tpl_path.read_text() if tpl_path.exists() else "Photorealistic portrait of the same man as the reference photos. Pose: {pose}."
    prompt = tpl.replace("{pose}", spec["prompt"]).strip()
    kw.setdefault("cache_dir", Path(assets) / "avatar" / ".cache")
    return paint(prompt, out, refs=refs, aspect="3:4", **kw)


def _strip_tags(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s or "").strip()


def commons_photo(query: str, out_dir: Path, fetch=None) -> dict | None:
    """First freely licensed photo on Wikimedia Commons for the query: {path, credit, title, url} or None."""
    fetch = fetch or (lambda u: urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "sg-content/1.0 (contact via GitHub SGULIA20)"}),
                                                       timeout=60, context=secrets.ssl_context()).read())
    params = {"action": "query", "format": "json", "generator": "search", "gsrsearch": f"filetype:bitmap {query}", "gsrnamespace": "6",
              "gsrlimit": "10", "prop": "imageinfo", "iiprop": "url|extmetadata", "iiurlwidth": "1920"}
    data = json.loads(fetch(f"{COMMONS_API}?{urllib.parse.urlencode(params)}").decode())
    for page in (data.get("query") or {}).get("pages", {}).values():
        info = (page.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata") or {}
        licence = _strip_tags((meta.get("LicenseShortName") or {}).get("value", ""))
        if not any(licence.lower().startswith(ok.lower()) for ok in FREE_LICENCES):
            continue
        url = info.get("thumburl") or info.get("url")
        if not url:
            continue
        out = Path(out_dir) / (hashlib.sha1(url.encode()).hexdigest() + Path(urllib.parse.urlparse(url).path).suffix.lower())
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(fetch(url))
        artist = _strip_tags((meta.get("Artist") or {}).get("value", "")) or "Wikimedia Commons contributor"
        return {"path": out, "credit": f"{artist}, {licence}, Wikimedia Commons", "title": page.get("title", ""), "url": url}
    return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--avatar-library", action="store_true", help="generate every missing pose")
    a = ap.parse_args(argv)
    if a.avatar_library:
        made = 0
        for pose in load_library():
            before = (ASSETS_DIR / "avatar" / f"{pose}.png").exists()
            avatar(pose)
            made += 0 if before else 1
            print(("kept " if before else "made ") + pose, flush=True)
        print(f"{made} new pictures, ₹{spent_today():.0f} spent today")
        return 0
    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
