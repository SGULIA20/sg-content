"""Threads API: one Reel as a video post (spec §3 step 11)."""
import json
import time
import urllib.error
import urllib.parse
import urllib.request

from . import secrets

API = "https://graph.threads.net/v1.0"
REFRESH_URL = "https://graph.threads.net/refresh_access_token"
MAX_TEXT = 500


class ThreadsError(Exception):
    pass


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
        raise ThreadsError(secrets.scrub(f"HTTP {e.code}: {e.read().decode(errors='replace')[:500]}")) from None
    except Exception as e:
        raise ThreadsError(secrets.scrub(f"{type(e).__name__}: {e}")) from None


def _wait(cid: str, token: str, label: str, sleep, call, max_polls: int, poll_s: float) -> None:
    for _ in range(max_polls):
        s = call("GET", f"/{cid}", token, {"fields": "status,error_message"})
        if s.get("status") == "FINISHED":
            return
        if s.get("status") in ("ERROR", "EXPIRED"):
            raise ThreadsError(f"{label} container failed: {s.get('error_message') or s.get('status')}")
        sleep(poll_s)
    raise ThreadsError(f"{label} container never finished")


def text_for(threads_caption: dict) -> str:
    text = (threads_caption or {}).get("text", "").strip()
    tags = " ".join((threads_caption or {}).get("hashtags", [])[:2])
    return f"{text}\n\n{tags}".strip() if tags else text


def post_video(uid: str, token: str, video_url: str, text: str, call=call, sleep=time.sleep, max_polls: int = 60, poll_s: float = 10) -> str:
    """One Reel as a Threads video post (9:16, up to five minutes). The URL must be public."""
    if len(text) > MAX_TEXT:
        raise ThreadsError(f"text is {len(text)} characters, Threads allows {MAX_TEXT}")
    cid = call("POST", f"/{uid}/threads", token, {"media_type": "VIDEO", "video_url": video_url, "text": text})["id"]
    _wait(cid, token, "video", sleep, call, max_polls, poll_s)
    return call("POST", f"/{uid}/threads_publish", token, {"creation_id": cid})["id"]


def refresh_token(token: str, call=call) -> dict:
    return call("GET", REFRESH_URL, token, {"grant_type": "th_refresh_token", "access_token": token})
