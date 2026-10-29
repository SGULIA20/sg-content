"""YouTube Data API v3: scheduled private upload (publishAt), thumbnails, metadata with sources, chapters and the synthetic-media flag (spec §3 step 10)."""
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
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


LEAD_HASHTAGS, MAX_HASHTAGS = 3, 15                        # YouTube shows the first three above the title; more than 15 and it ignores all
SUBSCRIBE = {"sglearning": "Subscribe karo: har hafte paise ki ek nayi kahani, seedhi baat mein.",
             "arthvan": "Subscribe karo: har hafte itihaas aur mythology ki ek nayi kahani, sabut ke saath."}


def _allowed_hashtags(channel: str, kind: str = "short") -> list:
    try:
        from .lint import load_lists
        tags = list(load_lists()[1].get(channel, {}).get("youtube", []))
    except Exception:
        return []
    if kind != "short":
        tags = [t for t in tags if t.lower() != "#shorts"]
    return tags[:MAX_HASHTAGS]


APP_LINE = {"sglearning": ("scoremybiz", "📱 Dukaan ka hisaab aur business score: ScoreMyBiz app (30 din free)"),
            "arthvan": ("waypoint", "📱 Waypoint app")}


def app_line(piece: Piece) -> str:
    """The channel's app with a Play link tagged for this video (Play Console then shows installs from YouTube descriptions)."""
    from urllib.parse import quote
    from .commentdm import PLAY
    app, label = APP_LINE[piece.channel]
    ref = quote(f"utm_source=youtube&utm_medium=description&utm_campaign={piece.id}", safe="")
    return f"{label}: {PLAY[app]}&referrer={ref}"


def metadata(piece: Piece, publish_at_utc: datetime, env=None) -> dict:
    env = {} if env is None else env
    yt = (piece.script or {}).get("captions", {}).get("youtube", {})
    title = yt.get("title", piece.script.get("hook", piece.id) if piece.script else piece.id).strip()
    if piece.kind == "short":
        title = title[: MAX_TITLE - len(SHORTS_SUFFIX)].rstrip() + SHORTS_SUFFIX
    else:
        title = title[:MAX_TITLE].rstrip()
    hashtags = _allowed_hashtags(piece.channel, piece.kind)
    parts = [(piece.script or {}).get("hook", "").strip(), " ".join(hashtags[:LEAD_HASHTAGS]), yt.get("description", "").strip()]
    if piece.kind == "short":
        parts.insert(2, app_line(piece))                                  # founder, 24 Oct 2026: the app rides with the content
    if piece.kind == "long":
        chapters = assemble.chapters(piece)
        if chapters:
            parts.append("\n".join(chapters))
    sources = _sources(piece)
    if sources:
        parts.append("Sources:\n" + "\n".join(sources))
    if piece.channel == "sglearning":
        parts.append(f"{DISCLAIMER}. Yeh video sirf samjhaane ke liye hai; koi bhi faisla apne advisor se pooch kar lijiye.")
    credits = sorted({sc["credit"] for sc in (piece.script or {}).get("scenes", []) if sc.get("credit")})
    if credits:
        parts.append("Photos:\n" + "\n".join(credits))
    parts.append(SUBSCRIBE.get(piece.channel, ""))
    from .config import YOUTUBE_URLS
    parts.append("Learning with SG (paise ki kahaniyan): " + YOUTUBE_URLS["sglearning"] + "\nSG-MYTH-WORLD (itihaas aur mythology, sabut ke saath): " + YOUTUBE_URLS["arthvan"])
    parts.append(" ".join(hashtags[LEAD_HASHTAGS:]))
    description = "\n\n".join(p for p in parts if p)
    tags = [t.lstrip("#") for t in yt.get("tags", [])][:MAX_TAGS]
    status = {"privacyStatus": "private", "publishAt": publish_at_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
              "selfDeclaredMadeForKids": False, "containsSyntheticMedia": True}
    from . import config
    if env.get("UNLISTED_DAY1") == "1" or piece.kind in config.UNLISTED_KINDS:
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


VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos?part=status"


def reschedule(token: str, video_id: str, when_utc, call=call) -> bool:
    """Moves a scheduled (private) video to another publish time (videos.update, part=status): the same-day news Short takes the
    day's slot and the evergreen Short it replaces moves to the end of the buffer (founder, 30 Oct 2026)."""
    at = when_utc.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    status, _h, body = call("PUT", VIDEOS_URL, token, json_body={"id": video_id, "status": {"privacyStatus": "private", "publishAt": at,
                                                                  "selfDeclaredMadeForKids": False, "containsSyntheticMedia": True}})
    if status in (200, 201):
        return True
    print(f"reschedule failed for {video_id} ({status}): {secrets.scrub(json.dumps(body))[:160]}", flush=True)
    return False


def go_public(token: str, video_id: str, call=call) -> bool:
    """Flips a first-day unlisted video to public (videos.update, part=status)."""
    status, _h, body = call("PUT", VIDEOS_URL, token, json_body={"id": video_id, "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False, "containsSyntheticMedia": True}})
    return status in (200, 201)


def main(argv=None) -> int:
    import argparse
    from . import pieces
    ap = argparse.ArgumentParser(description="python -m engine.youtube --go-public   makes every first-day unlisted video public")
    ap.add_argument("--go-public", action="store_true")
    a = ap.parse_args(argv)
    if not a.go_public:
        ap.print_help(); return 1
    done = 0
    for p in pieces.list_all():
        if p.ids.get("unlisted") and p.ids.get("yt_id"):
            if go_public(access_token(p.channel), p.ids["yt_id"]):
                p.ids.pop("unlisted"); pieces.save(p); done += 1
    print(f"{done} video(s) made public")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
