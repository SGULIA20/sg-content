"""The founder's control room (a private claude.ai page backed by the sg-command Supabase function): status out, pause flag in.

python -m engine.command_center --report produce-start    one status snapshot (the workflows call this at start and end)
python -m engine.command_center --paused                  prints the shared pause flag
python -m engine.command_center --telegram on|off         switches the bot's buttons on (webhook to the control room) or back off

Best effort everywhere: no key, no network or a slow reply never stops or breaks a run. The pause flag is cached in
logs/remote-pause.json so a run that cannot reach the control room still obeys the last answer it got.
Remote calls happen only for the real project root, so tests on a tmp root never touch the network.
"""
import argparse
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from . import pieces, secrets
from .config import ROOT, today_ist

URL = os.environ.get("SG_COMMAND_URL", "https://xiidltxcsetevaverqkx.supabase.co/functions/v1/sg-command")
TIMEOUT = 8
RUNS_SHOWN = 12
PIECES_SHOWN = 30


def _key(env=None) -> str:
    try:
        return secrets.get("SG_COMMAND_KEY", env)
    except secrets.MissingSecret:
        return ""


def _live(root: Path) -> bool:
    return Path(root).resolve() == ROOT.resolve()


def _call(method: str, route: str, key: str, body: dict | None = None, opener=urllib.request.urlopen) -> dict | None:
    data = json.dumps(body, ensure_ascii=False, default=str).encode() if body is not None else None
    req = urllib.request.Request(f"{URL}/{route}", data=data, method=method,
                                 headers={"x-sg-key": key, "content-type": "application/json"})
    try:
        with opener(req, timeout=TIMEOUT, context=secrets.ssl_context()) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"command centre unreachable ({type(e).__name__}); carrying on", flush=True)
        return None


def _cache(root: Path) -> Path:
    return Path(root) / "logs" / "remote-pause.json"


def _remember(root: Path, paused: bool) -> None:
    f = _cache(root)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"paused": paused, "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}))


def cached_paused(root: Path = ROOT) -> bool:
    try:
        return json.loads(_cache(root).read_text()).get("paused") is True
    except (FileNotFoundError, ValueError):
        return False


def remote_paused(root: Path = ROOT, env=None, call=_call) -> bool:
    """The shared pause flag set from the control page; the cached answer when the control room cannot be reached."""
    key = _key(env)
    if not key or not _live(root):
        return cached_paused(root)
    out = call("GET", "control", key)
    if out is None or "paused" not in out:
        return cached_paused(root)
    _remember(root, out["paused"] is True)
    return out["paused"] is True


def set_remote_paused(flag: bool, root: Path = ROOT, env=None, call=_call) -> None:
    """Telegram /pause and /resume keep the page's flag in step."""
    _remember(root, flag)
    key = _key(env)
    if key and _live(root):
        call("POST", "pause", key, {"paused": flag})


def telegram_setup(on: bool, env=None, call=_call) -> dict | None:
    """On: hands the bot token and chat id to the control room, which keeps them in Vault and points the bot's webhook at
    itself (buttons work without the Mac). Off: removes the webhook, so getUpdates polling works again as before."""
    key = _key(env)
    if not key:
        return None
    body = {"on": False}
    if on:
        try:
            body = {"on": True, "token": secrets.get("TELEGRAM_BOT_TOKEN", env), "chat_id": secrets.get("TELEGRAM_CHAT_ID", env)}
        except secrets.MissingSecret:
            return None
    return call("POST", "telegram-setup", key, body)


def telegram_inbox(root: Path = ROOT, env=None, call=_call) -> list | None:
    """With the webhook on, the messages the bot got that are not control-room commands (clip confirmations for the
    Mac inbox), oldest first, each handed out once. None when the webhook is off or the control room is unreachable."""
    key = _key(env)
    if not key or not _live(root):
        return None
    out = call("POST", "telegram-inbox", key, {})
    if not out or not out.get("webhook"):
        return None
    return [str(m) for m in out.get("messages", [])]


def _json(path: Path):
    try:
        return json.loads(Path(path).read_text())
    except (FileNotFoundError, ValueError):
        return {}


def _tail(d: dict, n: int = 3) -> dict:
    return {k: d[k] for k in sorted(d)[-n:]} if isinstance(d, dict) else {}


def snapshot(root: Path = ROOT, phase: str = "") -> dict:
    """What the page shows for sg-content: pieces, recent runs, spend, pause state and the run that sent it."""
    ps = sorted((p for p in pieces.list_all(root) if p and not p.id.startswith("preview-")), key=lambda p: p.id, reverse=True)
    runs = []
    log = Path(root) / "logs" / "runs.jsonl"
    if log.exists():
        for line in log.read_text().splitlines()[-RUNS_SHOWN:]:
            try:
                runs.append(json.loads(line))
            except ValueError:
                continue
    gh_run = ""
    if os.environ.get("GITHUB_RUN_ID"):
        gh_run = f"{os.environ.get('GITHUB_SERVER_URL', 'https://github.com')}/{os.environ.get('GITHUB_REPOSITORY', '')}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
    logs = Path(root) / "logs"
    snap = {
        "phase": phase,
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "today_ist": today_ist().isoformat(),
        "github_run": gh_run,
        "local_paused": (logs / "pause.json").exists(),
        "pieces": [{"id": p.id, "channel": p.channel, "kind": p.kind, "status": p.status, "publish_day": p.publish_day.isoformat(),
                    "reasons": [r[:240] for r in p.reasons[-3:]], "yt_id": p.ids.get("yt_id", ""), "updated": p.updated}
                   for p in ps[:PIECES_SHOWN]],
        "runs": list(reversed(runs)),
        "spend": {"voice_requests": _tail(_json(logs / "voice-budget.json")), "claude": _tail(_json(logs / "claude-spend.json")),
                  "images": _tail(_json(logs / "image-spend.json"))},
    }
    return json.loads(secrets.scrub(json.dumps(snap, ensure_ascii=False, default=str)))


def report(root: Path = ROOT, phase: str = "", env=None, call=_call) -> bool:
    key = _key(env)
    if not key or not _live(root):
        return False
    events = [{"kind": "run", "message": f"sg-content {phase}"}] if phase else []
    out = call("POST", "ingest", key, {"source": "sg-content", "key": "snapshot", "payload": snapshot(root, phase), "events": events})
    if out is not None and "paused" in out:
        _remember(root, out["paused"] is True)
    return out is not None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--report", metavar="PHASE", help="send one status snapshot, e.g. produce-start, publish-end")
    ap.add_argument("--paused", action="store_true", help="print the shared pause flag")
    ap.add_argument("--telegram", choices=["on", "off"], help="switch the bot's control-room buttons on or off")
    a = ap.parse_args(argv)
    if a.telegram:
        out = telegram_setup(a.telegram == "on")
        print(f"telegram buttons: {out}" if out else "telegram buttons: not changed (no SG_COMMAND_KEY, no bot token, or unreachable)")
        return 0 if out and "error" not in out else 1
    if a.report:
        print("reported" if report(ROOT, a.report) else "not reported (no key or unreachable)")
    if a.paused:
        print("paused" if remote_paused(ROOT) else "running")
    return 0                                                   # never fails a workflow


if __name__ == "__main__":
    sys.exit(main())
