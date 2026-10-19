"""YouTube Data API v3: scheduled private upload (publishAt), thumbnails, metadata with sources, chapters and the synthetic-media flag (spec §3 step 10)."""
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

from . import assemble, secrets
from .config import CHANNELS
from .lint import DISCLAIMER
from .pieces import Piece

TOKEN_URL = "https://oauth2.googleapis.com/token"
UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status"
THUMB_URL = "https://www.googleapis.com/upload/youtube/v3/thumbnails/set?videoId={vid}&uploadType=media"
MAX_TITLE = 60
MAX_TAGS = 15
SHORTS_SUFFIX = " #Shorts"


class YouTubeError(Exception):
    pass


def call(method: str, url: str, token: str, json_body=None, data=None, headers=None):
    hdrs = {"Authorization": "Bearer " + token}
    hdrs.update(headers or {})
    if json_body is not None:
        data = json.dumps(json_body).encode(); hdrs["Content-Type"] = "application/json; charset=UTF-8"
    req = urllib.request.Request(url, data=data, method=method, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=900, context=secrets.ssl_context()) as r:
            raw = r.read()
            return r.status, {k.lower(): v for k, v in r.headers.items()}, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:400]
        try:
            return e.code, {}, json.loads(body)
        except ValueError:
            return e.code, {}, {"error": secrets.scrub(body)}


def _post_form(url: str, form: dict) -> dict:
    req = urllib.request.Request(url, data=urllib.parse.urlencode(form).encode(), method="POST",
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=60, context=secrets.ssl_context()) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}", "error_description": e.read().decode(errors="replace")[:200]}


def access_token(channel: str, env=None, post=_post_form) -> str:
    ch = CHANNELS[channel]
    form = {"client_id": secrets.get("YT_CLIENT_ID", env), "client_secret": secrets.get("YT_CLIENT_SECRET", env),
            "refresh_token": secrets.get(ch.youtube_env_token, env), "grant_type": "refresh_token"}
    out = post(TOKEN_URL, form)
    if "access_token" not in out:
        raise YouTubeError(f"token refresh failed for {channel}: {out.get('error_description') or out.get('error')}")
    secrets.remember(out["access_token"])
    return out["access_token"]


def _sources(piece: Piece) -> list:
    used = sorted({i for sc in (piece.script or {}).get("scenes", []) for i in sc.get("facts_used", [])})
    seen, lines = set(), []
    for i in used:
        if i >= len(piece.facts):
            continue
        f = piece.facts[i]
        key = f.get("source_url")
        if key in seen:
            continue
        seen.add(key)
        lines.append(f"{f.get('source_name', 'Source')}, {f.get('source_date', '')}, {f.get('source_url', '')}".replace(", ,", ","))
    return lines


def metadata(piece: Piece, publish_at_utc: datetime, env=None) -> dict:
    env = {} if env is None else env
    yt = (piece.script or {}).get("captions", {}).get("youtube", {})
    title = yt.get("title", piece.script.get("hook", piece.id) if piece.script else piece.id).strip()
    if piece.kind == "short":
        title = title[: MAX_TITLE - len(SHORTS_SUFFIX)].rstrip() + SHORTS_SUFFIX
    else:
        title = title[:MAX_TITLE].rstrip()
    parts = [(piece.script or {}).get("hook", "").strip(), yt.get("description", "").strip()]
    if piece.kind == "long":
        chapters = assemble.chapters(piece)
        if chapters:
            parts.append("\n".join(chapters))
    sources = _sources(piece)
    if sources:
        parts.append("Sources:\n" + "\n".join(sources))
    if piece.channel == "sglearning":
        parts.append(f"{DISCLAIMER}. Yeh video sirf samjhaane ke liye hai; koi bhi faisla apne advisor se pooch kar lijiye.")
    parts.append(" ".join(f"#{t.lstrip('#')}" for t in yt.get("tags", [])[:5]))
    description = "\n\n".join(p for p in parts if p)
    tags = [t.lstrip("#") for t in yt.get("tags", [])][:MAX_TAGS]
    status = {"privacyStatus": "private", "publishAt": publish_at_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
              "selfDeclaredMadeForKids": False, "containsSyntheticMedia": True}
    if env.get("UNLISTED_DAY1") == "1":
        status = {"privacyStatus": "unlisted", "selfDeclaredMadeForKids": False, "containsSyntheticMedia": True}
    return {"snippet": {"title": title, "description": description[:5000], "tags": tags, "categoryId": CHANNELS[piece.channel].youtube_category,
                        "defaultLanguage": "hi", "defaultAudioLanguage": "hi"},
            "status": status}


def upload(token: str, path: Path, meta: dict, call=call) -> str:
    data = Path(path).read_bytes()
    status, headers, _ = call("POST", UPLOAD_URL, token, json_body=meta,
                              headers={"X-Upload-Content-Length": str(len(data)), "X-Upload-Content-Type": "video/mp4"})
    if "location" not in headers:
        raise YouTubeError(f"resumable session not created ({status})")
    status, _, body = call("PUT", headers["location"], token, data=data, headers={"Content-Type": "video/mp4"})
    if status not in (200, 201) or "id" not in body:
        raise YouTubeError(f"upload returned {status} without a video id: {secrets.scrub(json.dumps(body))[:200]}")
    return body["id"]


def set_thumbnail(token: str, video_id: str, jpg: Path, call=call) -> bool:
    status, _, body = call("POST", THUMB_URL.format(vid=video_id), token, data=Path(jpg).read_bytes(), headers={"Content-Type": "image/jpeg"})
    if status in (200, 201):
        return True
    print(f"thumbnail not set for {video_id} ({status}): {secrets.scrub(json.dumps(body))[:120]}", flush=True)
    return False
