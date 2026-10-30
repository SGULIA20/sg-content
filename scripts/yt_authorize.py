"""One-time per channel: get a YouTube refresh token that can also manage captions (youtube.force-ssl).

    python3 scripts/yt_authorize.py sglearning
    python3 scripts/yt_authorize.py arthvan
    python3 scripts/yt_authorize.py ads          Google Ads (founder, 30 Oct 2026): sign in with the account that owns the Ads account

It opens Google's consent page in your browser; sign in with the Google account that owns THAT channel and pick the channel.
The new refresh token is written straight into ~/sg-content/.env (YT_<CHANNEL>_REFRESH_TOKEN); nothing is printed or logged.
The old token keeps working for arthvan-media; Google allows several tokens per account."""
import http.server
import json
import secrets as pysecrets
import sys
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import secrets  # noqa: E402

SCOPES = "https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly https://www.googleapis.com/auth/youtube.force-ssl"
PORT = 8765
ENV = Path.home() / "sg-content" / ".env"
KEYS = {"sglearning": "YT_SGLEARNING_REFRESH_TOKEN", "arthvan": "YT_ARTHVAN_REFRESH_TOKEN", "ads": "ADS_REFRESH_TOKEN"}
ADS_SCOPE = "https://www.googleapis.com/auth/adwords"


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in KEYS:
        print("usage: python3 scripts/yt_authorize.py sglearning|arthvan|ads"); return 2
    channel = sys.argv[1]
    client_id, client_secret = secrets.get("YT_CLIENT_ID"), secrets.get("YT_CLIENT_SECRET")
    state = pysecrets.token_urlsafe(16)
    redirect = f"http://localhost:{PORT}/"
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode({
        "client_id": client_id, "redirect_uri": redirect, "response_type": "code", "scope": ADS_SCOPE if channel == "ads" else SCOPES,
        "access_type": "offline", "prompt": "consent", "state": state})
    got = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if q.get("state", [""])[0] == state and q.get("code"):
                got["code"] = q["code"][0]
                msg = f"Done. {channel} is authorised for captions. You can close this tab."
            else:
                msg = "Something went wrong; run the script again."
            self.send_response(200); self.send_header("Content-Type", "text/plain"); self.end_headers(); self.wfile.write(msg.encode())

        def log_message(self, *a):
            pass

    print(f"Opening the Google consent page for {channel}. Sign in with the account that owns that channel.")
    webbrowser.open(url)
    with http.server.HTTPServer(("localhost", PORT), Handler) as srv:
        while "code" not in got:
            srv.handle_request()
    form = urllib.parse.urlencode({"code": got["code"], "client_id": client_id, "client_secret": client_secret,
                                   "redirect_uri": redirect, "grant_type": "authorization_code"}).encode()
    req = urllib.request.Request("https://oauth2.googleapis.com/token", data=form, method="POST",
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, context=secrets.ssl_context()) as r:
        tok = json.loads(r.read())
    if "refresh_token" not in tok:
        print("Google did not return a refresh token (was consent skipped?). Run again."); return 1
    key = KEYS[channel]
    lines = ENV.read_text().splitlines() if ENV.exists() else []
    lines = [ln for ln in lines if not ln.startswith(key + "=")] + [f"{key}={tok['refresh_token']}"]
    ENV.write_text("\n".join(lines) + "\n")
    if channel == "ads":
        print(f"{key} saved in {ENV}. Next: grep '^{key}=' {ENV} | cut -d= -f2- | gh secret set {key} --repo SGULIA20/sg-content")
    else:
        print(f"{key} updated in {ENV}. Next: python3 -m engine.subtitles <piece-id> for any long already uploaded.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
