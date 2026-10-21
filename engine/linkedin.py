"""LinkedIn: each Short as a native video post on the founder's personal profile (founder, 21 Oct 2026; docs/decisions.md).

python -m engine.linkedin --auth      one-time OAuth on the Mac; prints LINKEDIN_ACCESS_TOKEN and LINKEDIN_PERSON_URN to store
"""
import argparse
import http.server
import json
import os
import re
import secrets as pysecrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

from . import secrets
from .config import ROOT
from .lint import DISCLAIMER

API = "https://api.linkedin.com/rest"
USERINFO_URL = "https://api.linkedin.com/v2/userinfo"
AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
REDIRECT = "http://localhost:8765/callback"
SCOPES = "openid profile w_member_social"
DEFAULT_VERSION = "202606"                        # LinkedIn-Version (YYYYMM); versions are retired after about a year, so LINKEDIN_VERSION overrides it
MAX_TEXT = 3000
MAX_HASHTAGS = 3
RESERVED = set("\\|{}@[]()<>#*_~")                # "little text": reserved characters are escaped with a backslash


class LinkedInError(Exception):
    pass


def version(env=None) -> str:
    return (os.environ if env is None else env).get("LINKEDIN_VERSION") or DEFAULT_VERSION


def configured(env=None) -> bool:
    try:
        secrets.get("LINKEDIN_ACCESS_TOKEN", env); secrets.get("LINKEDIN_PERSON_URN", env)
        return True
    except secrets.MissingSecret:
        return False


def call(method: str, url: str, token: str, body: dict | None = None, data: bytes | None = None, headers: dict | None = None) -> tuple:
    """One request. Returns (lower-cased response headers, parsed JSON or {}). `body` is sent as JSON, `data` as raw bytes."""
    url = url if url.startswith("http") else API + url
    h = {"Authorization": "Bearer " + token, **(headers or {})}
    if body is not None:
        data = json.dumps(body).encode()
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=120, context=secrets.ssl_context()) as r:
            raw = r.read()
            return {k.lower(): v for k, v in r.headers.items()}, (json.loads(raw) if raw.strip() else {})
    except urllib.error.HTTPError as e:
        raise LinkedInError(secrets.scrub(f"HTTP {e.code}: {e.read().decode(errors='replace')[:500]}")) from None
    except Exception as e:
        raise LinkedInError(secrets.scrub(f"{type(e).__name__}: {e}")) from None


def _rest(ver: str) -> dict:
    return {"LinkedIn-Version": ver, "X-Restli-Protocol-Version": "2.0.0"}


def upload_video(person_urn: str, token: str, video_path: Path, call=call, sleep=time.sleep, ver: str = DEFAULT_VERSION,
                 max_polls: int = 36, poll_s: float = 5) -> str:
    """Initialize, PUT each part, finalize with the parts' ETags, then wait (at most max_polls * poll_s) for AVAILABLE. Returns the video URN."""
    blob = Path(video_path).read_bytes()
    _, init = call("POST", "/videos?action=initializeUpload", token, body={"initializeUploadRequest": {
        "owner": person_urn, "fileSizeBytes": len(blob), "uploadCaptions": False, "uploadThumbnail": False}}, headers=_rest(ver))
    value = init.get("value", {})
    video, parts = value.get("video"), value.get("uploadInstructions") or []
    if not video or not parts:
        raise LinkedInError(f"initializeUpload returned no video or upload instructions: {str(init)[:200]}")
    etags = []
    for part in parts:
        chunk = blob[int(part["firstByte"]):int(part["lastByte"]) + 1]
        hdrs, _ = call("PUT", part["uploadUrl"], token, data=chunk, headers={"Content-Type": "application/octet-stream"})
        if not hdrs.get("etag"):
            raise LinkedInError(f"upload of bytes {part['firstByte']}-{part['lastByte']} returned no ETag")
        etags.append(hdrs["etag"])
    call("POST", "/videos?action=finalizeUpload", token, body={"finalizeUploadRequest": {
        "video": video, "uploadToken": value.get("uploadToken", ""), "uploadedPartIds": etags}}, headers=_rest(ver))
    for _ in range(max_polls):
        _, s = call("GET", "/videos/" + urllib.parse.quote(video, safe=""), token, headers=_rest(ver))
        if s.get("status") == "AVAILABLE":
            return video
        if s.get("status") == "PROCESSING_FAILED":
            raise LinkedInError(f"video processing failed: {s.get('processingFailureReason') or 'no reason given'}")
        sleep(poll_s)
    raise LinkedInError(f"video {video} not AVAILABLE after {int(max_polls * poll_s)} s")


def post_video(person_urn: str, token: str, video_path: Path, text: str, title: str, call=call, sleep=time.sleep,
               ver: str | None = None, max_polls: int = 36, poll_s: float = 5) -> str:
    """Uploads the Short and posts it publicly to the member's feed. `text` must already be little-text escaped. Returns the post URN."""
    if len(text) > MAX_TEXT:
        raise LinkedInError(f"text is {len(text)} characters, LinkedIn allows {MAX_TEXT}")
    ver = ver or version()
    video = upload_video(person_urn, token, video_path, call=call, sleep=sleep, ver=ver, max_polls=max_polls, poll_s=poll_s)
    hdrs, _ = call("POST", "/posts", token, body={
        "author": person_urn, "commentary": text, "visibility": "PUBLIC",
        "distribution": {"feedDistribution": "MAIN_FEED", "targetEntities": [], "thirdPartyDistributionChannels": []},
        "content": {"media": {"title": title[:200], "id": video}},
        "lifecycleState": "PUBLISHED", "isReshareDisabledByAuthor": False}, headers=_rest(ver))
    post = hdrs.get("x-restli-id")
    if not post:
        raise LinkedInError("post created but LinkedIn returned no x-restli-id")
    return post


def escape(text: str) -> str:
    return "".join("\\" + c if c in RESERVED else c for c in text)


def _hashtag(tag: str) -> str:
    word = re.sub(r"\W", "", tag.lstrip("#"))
    return "{hashtag|\\#|" + word + "}" if word else ""


def title_for(piece) -> str:
    caps = (piece.script or {}).get("captions", {})
    return (caps.get("youtube", {}).get("title") or (piece.script or {}).get("title") or piece.id).strip()


def text_for(piece) -> str:
    """Little-text commentary: YouTube title, the Threads text without its hashtags, the disclaimer (finance), the YouTube link, up to 3 hashtags."""
    caps = (piece.script or {}).get("captions", {})
    body = re.sub(r"(?<!\w)#\w+", "", caps.get("threads", {}).get("text", ""))
    body = re.sub(r"[ \t]+", " ", body).strip()
    tail = []
    carried = " ".join([caps.get("instagram", {}).get("caption", ""), caps.get("threads", {}).get("text", "")]).lower()
    if piece.channel == "sglearning" and DISCLAIMER.lower() in carried and DISCLAIMER.lower() not in body.lower():
        tail.append(DISCLAIMER + ".")
    yt = (piece.ids or {}).get("yt_id")
    if yt:
        tail.append(f"Watch the full video on YouTube: https://youtu.be/{yt}")
    tags = " ".join(t for t in (_hashtag(h) for h in caps.get("instagram", {}).get("hashtags", [])[:MAX_HASHTAGS]) if t)
    head = escape(title_for(piece))
    rest = "\n\n".join(escape(t) for t in tail) + ("\n\n" + tags if tags else "")
    room = MAX_TEXT - len(head) - len(rest) - 4
    eb = escape(body)
    if len(eb) > room:                                                              # cut on a whole escaped character, never between "\" and its char
        cut = ""
        for c in body:
            if len(cut) + len(escape(c)) + 1 > room:
                break
            cut += escape(c)
        eb = cut.rstrip() + "…"
    return "\n\n".join(p for p in (head, eb, rest) if p)[:MAX_TEXT]


def record_expiry(expires_in: int, root: Path = ROOT, today: date | None = None) -> str:
    """Writes linkedin_expires to logs/tokens.json (beside the Instagram/Threads dates) so the digest warns 7 days ahead."""
    path = Path(root) / "logs" / "tokens.json"
    try:
        data = json.loads(path.read_text())
    except (FileNotFoundError, ValueError):
        data = {}
    data["linkedin_expires"] = ((today or date.today()) + timedelta(seconds=int(expires_in))).isoformat()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1))
    return data["linkedin_expires"]


def _form(url: str, params: dict) -> dict:
    req = urllib.request.Request(url, data=urllib.parse.urlencode(params).encode(), method="POST",
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=60, context=secrets.ssl_context()) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise LinkedInError(secrets.scrub(f"HTTP {e.code}: {e.read().decode(errors='replace')[:500]}")) from None


def _catch_code(state: str, port: int = 8765) -> str:
    """Serves one request on localhost and returns the ?code= LinkedIn redirected with."""
    got = {}

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            got.update({k: v[0] for k, v in q.items()})
            self.send_response(200); self.send_header("Content-Type", "text/plain"); self.end_headers()
            self.wfile.write(b"sg-content: LinkedIn authorised, you can close this tab.")

        def log_message(self, *a):
            pass

    with http.server.HTTPServer(("localhost", port), H) as srv:
        while "code" not in got and "error" not in got:
            srv.handle_request()
    if got.get("error"):
        raise LinkedInError(f"authorisation refused: {got.get('error')}: {got.get('error_description', '')}")
    if got.get("state") != state:
        raise LinkedInError("state mismatch on the OAuth callback")
    return got["code"]


def auth(env=None, root: Path = ROOT) -> int:
    cid, csecret = secrets.get("LINKEDIN_CLIENT_ID", env), secrets.get("LINKEDIN_CLIENT_SECRET", env)
    state = pysecrets.token_urlsafe(16)
    url = AUTH_URL + "?" + urllib.parse.urlencode({"response_type": "code", "client_id": cid, "redirect_uri": REDIRECT,
                                                     "state": state, "scope": SCOPES})
    print(f"Open this URL, sign in as the founder and allow access:\n\n{url}\n\nWaiting on {REDIRECT} ...", flush=True)
    code = _catch_code(state)
    tok = _form(TOKEN_URL, {"grant_type": "authorization_code", "code": code, "client_id": cid, "client_secret": csecret, "redirect_uri": REDIRECT})
    token = tok["access_token"]
    secrets.remember(token)
    _, me = call("GET", USERINFO_URL, token)
    expires = record_expiry(int(tok.get("expires_in", 60 * 86400)), root)
    print(f"\nStore these (in .env and as GitHub secrets):\nLINKEDIN_ACCESS_TOKEN={token}\nLINKEDIN_PERSON_URN=urn:li:person:{me['sub']}\n"
          f"\nSigned in as {me.get('name', '?')}. The token expires {expires}; logs/tokens.json now holds that date "
          f"(commit and push it so the digest warns 7 days before). Re-run --auth before then.")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--auth", action="store_true")
    a = ap.parse_args(argv)
    if not a.auth:
        ap.print_help(); return 1
    return auth()


if __name__ == "__main__":
    sys.exit(main())
