"""Instagram Graph API: Reel, Story and (when flagged) carousel from the files committed under out/<id>/ (spec §3 step 11, §7).

Each platform id is written to the piece record as soon as it exists, so a crash between the Reel and the Story never posts the Reel twice.
"""
import json
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from . import pieces, secrets
from .config import ROOT
from .pieces import Piece

API = "https://graph.instagram.com/v25.0"          # Instagram API with Instagram Login (same tokens as arthvan-media)
REFRESH_URL = "https://graph.instagram.com/refresh_access_token"
DEFAULT_REPO = "SGULIA20/sg-content"
THUMB_OFFSET_MS = 2000
STORY_MAX_S = 60.0                 # Instagram refuses a Story video over 60 s


def _too_long_for_story(video: Path, max_s: float = STORY_MAX_S) -> bool:
    """True when the Story file runs over 60 s. Pieces made before 22 Oct 2026 carry a full-length story.mp4 that Instagram rejects
    (status ERROR) on every run; those get no Story, the same rule as new pieces. An unreadable file (a test stub) counts as fitting."""
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(video)],
                             capture_output=True, text=True, check=True).stdout.strip()
        return float(out) > max_s
    except (subprocess.CalledProcessError, ValueError, OSError):
        return False


class InstagramError(Exception):
    pass


class PartialPublish(InstagramError):
    """Some items went live before a later one failed; the piece record already holds their ids."""


def call(method: str, path: str, token: str, params: dict | None = None) -> dict:
    url = path if path.startswith("http") else API + path
    data = None
    if method == "GET" and params:
        url += "?" + urllib.parse.urlencode(params)
    elif params:
        data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(url, data=data, method=method, headers={"Authorization": "Bearer " + token})
    try:
        with urllib.request.urlopen(req, timeout=60, context=secrets.ssl_context()) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise InstagramError(secrets.scrub(f"HTTP {e.code}: {e.read().decode(errors='replace')[:500]}")) from None
    except Exception as e:
        raise InstagramError(secrets.scrub(f"{type(e).__name__}: {e}")) from None


def _wait(cid: str, token: str, label: str, sleep=time.sleep, call=call, max_polls: int = 90, poll_s: float = 4) -> None:
    for _ in range(max_polls):
        status = call("GET", f"/{cid}", token, {"fields": "status_code"}).get("status_code")
        if status == "FINISHED":
            return
        if status in ("ERROR", "EXPIRED"):
            raise InstagramError(f"{label} container failed with status {status}")
        sleep(poll_s)
    raise InstagramError(f"{label} container never finished")


def _serves(url: str, head=None) -> bool:
    try:
        req = urllib.request.Request(url, method="HEAD")
        with (head or (lambda r: urllib.request.urlopen(r, timeout=20, context=secrets.ssl_context())))(req) as r:
            return r.status == 200
    except Exception:
        return False


def media_url(piece: Piece, name: str, repo: str) -> str:
    sha = piece.ids.get("out_sha")
    if not sha:
        raise InstagramError(f"{piece.id} has no out_sha: the Short was not committed yet, so Instagram cannot fetch it")
    return f"https://raw.githubusercontent.com/{repo}/{sha}/out/{piece.id}/{name}"


def resolved_media_url(piece: Piece, name: str, repo: str, head=None) -> str:
    """media_url, checked: the recorded commit first; if GitHub does not serve the file there (a rebased commit, 22 Oct 2026),
    the branch head, where the file lives for two weeks."""
    url = media_url(piece, name, repo)
    sha = piece.ids["out_sha"]
    if _serves(url, head):
        return url
    alt = f"https://raw.githubusercontent.com/{repo}/main/out/{piece.id}/{name}"
    if _serves(alt, head):
        print(f"{piece.id}: {name} is not at {sha[:8]}; using the branch head", flush=True)
        return alt
    raise InstagramError(f"{piece.id}: {name} is served neither at {sha[:8]} nor on main")


def caption_text(piece: Piece) -> str:
    from .config import YOUTUBE_URLS
    ig = (piece.script or {}).get("captions", {}).get("instagram", {})
    link = YOUTUBE_URLS.get(piece.channel)
    parts = [ig.get("caption", "").strip()] + ([f"▶ Poori videos YouTube par: {link}"] if link else []) + [" ".join(ig.get("hashtags", []))]
    return "\n\n".join(p for p in parts if p).strip()


def _create_and_publish(ig_id: str, token: str, params: dict, label: str, call, sleep) -> str:
    cid = call("POST", f"/{ig_id}/media", token, params)["id"]
    _wait(cid, token, label, sleep=sleep, call=call)
    return call("POST", f"/{ig_id}/media_publish", token, {"creation_id": cid})["id"]


def publish_piece(piece: Piece, env=None, call=call, sleep=time.sleep, root: Path = ROOT, check_media: bool = False) -> Piece:
    """Posts whatever is still missing for this piece: Reel, Story, then the carousel if the script asked for one.
    check_media=True (production) verifies each media URL on GitHub first and falls back to the branch head."""
    token = secrets.get("IG_ACCESS_TOKEN", env)
    ig_id = secrets.get("IG_USER_ID", env)
    repo = (env or {}).get("GITHUB_REPOSITORY") or DEFAULT_REPO
    media_url = resolved_media_url if check_media else globals()["media_url"]
    caption = caption_text(piece)
    done = []
    try:
        if not piece.ids.get("ig_reel_id"):
            params = {"media_type": "REELS", "video_url": media_url(piece, "reel.mp4", repo), "caption": caption, "share_to_feed": "true"}
            if (Path(root) / "out" / piece.id / "cover.jpg").exists():
                params["cover_url"] = media_url(piece, "cover.jpg", repo)       # the drawn reaction cover, same as the YouTube thumbnail
            else:
                params["thumb_offset"] = str(THUMB_OFFSET_MS)
            piece.ids["ig_reel_id"] = _create_and_publish(ig_id, token, params, "reel", call, sleep)
            pieces.save(piece, root); done.append("reel")
        out_dir = Path(root) / "out" / piece.id
        if not piece.ids.get("ig_story_id") and out_dir.exists() and (not (out_dir / "story.mp4").exists() or _too_long_for_story(out_dir / "story.mp4")):
            piece.ids["ig_story_id"] = "skipped: Reel over 60 s"             # founder, 22 Oct 2026: no trimmed Story; the Reel keeps its full length
            pieces.save(piece, root)
        if not piece.ids.get("ig_story_id"):
            piece.ids["ig_story_id"] = _create_and_publish(ig_id, token, {
                "media_type": "STORIES", "video_url": media_url(piece, "story.mp4", repo)}, "story", call, sleep)
            pieces.save(piece, root); done.append("story")
        if (piece.script or {}).get("carousel") and not piece.ids.get("ig_post_id"):
            n = len((piece.script or {}).get("cards", []))
            children = []
            for i in range(1, n + 1):
                cid = call("POST", f"/{ig_id}/media", token, {"image_url": media_url(piece, f"slide{i:02d}.jpg", repo), "is_carousel_item": "true"})["id"]
                _wait(cid, token, f"slide {i}", sleep=sleep, call=call)
                children.append(cid)
            piece.ids["ig_post_id"] = _create_and_publish(ig_id, token, {
                "media_type": "CAROUSEL", "children": ",".join(children), "caption": caption}, "carousel", call, sleep)
            pieces.save(piece, root); done.append("carousel")
    except InstagramError as e:
        raise PartialPublish(f"{piece.id}: {e} (already live: {done or 'nothing'})") from None
    return piece


def refresh_token(token: str, call=call) -> dict:
    return call("GET", REFRESH_URL, token, {"grant_type": "ig_refresh_token", "access_token": token})
