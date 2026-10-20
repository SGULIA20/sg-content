"""The project's own Telegram bot: digests and alerts out, /pause /resume /status in (spec §3 step 12, §7).

python -m engine.telegram --find-chat     prints the chat id of whoever messaged the bot last (run once, put it in .env)
python -m engine.telegram --poll          handles pending commands (the workflows call this before every run)
"""
import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from . import secrets
from .config import ROOT

API = "https://api.telegram.org/bot{token}/{method}"


def _post(url: str, body: dict) -> dict:
    req = urllib.request.Request(url, data=urllib.parse.urlencode(body).encode(), method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30, context=secrets.ssl_context()) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"ok": False, "description": e.read().decode(errors="replace")[:200]}
    except Exception as e:
        return {"ok": False, "description": f"{type(e).__name__}"}


def _get(url: str) -> dict:
    try:
        with urllib.request.urlopen(url, timeout=30, context=secrets.ssl_context()) as r:
            return json.loads(r.read())
    except Exception as e:
        return {"ok": False, "result": [], "description": f"{type(e).__name__}"}


def _config(env) -> tuple:
    try:
        return secrets.get("TELEGRAM_BOT_TOKEN", env), secrets.get("TELEGRAM_CHAT_ID", env)
    except secrets.MissingSecret:
        return "", ""


def send(text: str, env=None, post=_post) -> bool:
    token, chat = _config(env)
    if not token or not chat:
        return False
    out = post(API.format(token=token, method="sendMessage"), {"chat_id": chat, "text": secrets.scrub(text)[:4000], "disable_web_page_preview": "true"})
    return bool(out.get("ok"))


def send_file(path: Path, caption: str = "", env=None) -> bool:
    """A small file (a preview Short) as a document; multipart by hand, stdlib only."""
    token, chat = _config(env)
    if not token or not chat:
        return False
    boundary = "----sgcontent"
    data = Path(path).read_bytes()
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"chat_id\"\r\n\r\n{chat}\r\n"
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"caption\"\r\n\r\n{secrets.scrub(caption)[:1000]}\r\n"
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"document\"; filename=\"{Path(path).name}\"\r\n"
            f"Content-Type: application/octet-stream\r\n\r\n").encode() + data + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(API.format(token=token, method="sendDocument"), data=body, method="POST",
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        with urllib.request.urlopen(req, timeout=120, context=secrets.ssl_context()) as r:
            return bool(json.loads(r.read()).get("ok"))
    except Exception:
        return False


def pause_file(root: Path = ROOT) -> Path:
    return Path(root) / "logs" / "pause.json"


def paused(root: Path = ROOT) -> bool:
    return pause_file(root).exists()


def set_paused(flag: bool, root: Path = ROOT) -> None:
    f = pause_file(root)
    if flag:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps({"paused": True}))
    elif f.exists():
        f.unlink()


def poll_commands(env=None, state: Path = ROOT / "logs" / "tg-offset.json", get=_get, post=_post, root: Path = ROOT, status_fn=None, handler=None) -> list:
    """Reads new messages from the founder's chat and applies /pause, /resume, /status. Returns the commands handled."""
    token, chat = _config(env)
    if not token:
        return []
    try:
        offset = int(json.loads(Path(state).read_text()).get("offset", 0))
    except (FileNotFoundError, ValueError):
        offset = 0
    data = get(API.format(token=token, method="getUpdates") + f"?offset={offset}&timeout=0")
    handled, last = [], offset
    for u in data.get("result", []):
        last = max(last, int(u.get("update_id", 0)) + 1)
        msg = u.get("message") or {}
        if str((msg.get("chat") or {}).get("id")) != str(chat):
            continue                                                       # only the founder's chat may steer the bot
        text = (msg.get("text") or "").strip().split()[0].lower() if msg.get("text") else ""
        if text == "/pause":
            set_paused(True, root); handled.append("/pause")
            post(API.format(token=token, method="sendMessage"), {"chat_id": chat, "text": "Paused. Nothing will be made or posted until /resume."})
        elif text == "/resume":
            set_paused(False, root); handled.append("/resume")
            post(API.format(token=token, method="sendMessage"), {"chat_id": chat, "text": "Resumed. The next run carries on."})
        elif text == "/status":
            handled.append("/status")
            line = status_fn() if status_fn else ("paused" if paused(root) else "running")
            post(API.format(token=token, method="sendMessage"), {"chat_id": chat, "text": secrets.scrub(line)})
        elif handler and msg.get("text"):
            reply = handler(msg["text"].strip())
            if reply:
                handled.append(msg["text"].strip())
                post(API.format(token=token, method="sendMessage"), {"chat_id": chat, "text": secrets.scrub(reply)[:4000]})
    Path(state).parent.mkdir(parents=True, exist_ok=True)
    Path(state).write_text(json.dumps({"offset": last}))
    return handled


def find_chat(env=None, get=_get) -> str:
    token = secrets.get("TELEGRAM_BOT_TOKEN", env)
    data = get(API.format(token=token, method="getUpdates"))
    chats = [str(u["message"]["chat"]["id"]) for u in data.get("result", []) if "message" in u]
    return chats[-1] if chats else ""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--find-chat", action="store_true")
    ap.add_argument("--poll", action="store_true")
    ap.add_argument("--send", metavar="TEXT")
    a = ap.parse_args(argv)
    if a.find_chat:
        chat = find_chat()
        print(f"TELEGRAM_CHAT_ID={chat}" if chat else "no message found: send the bot any message first")
        return 0 if chat else 1
    if a.poll:
        from . import digest
        print("handled:", poll_commands(status_fn=lambda: digest.status_line(ROOT)))
        return 0
    if a.send:
        return 0 if send(a.send) else 1
    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
