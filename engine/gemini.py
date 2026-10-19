"""One door to Gemini generateContent with retries. Key: GEMINI_API_KEY from engine.secrets."""
import http.client
import json
import time
import urllib.error
import urllib.request

from . import secrets

API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
TRIES = 3
WAIT_S = 60


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


def generate(model: str, body: dict, key: str | None = None, post=_post) -> dict:
    key = key or secrets.get("GEMINI_API_KEY")
    url = API.format(model=model)
    last = ""
    for attempt in range(TRIES):
        status, data = post(url, body, key)
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
