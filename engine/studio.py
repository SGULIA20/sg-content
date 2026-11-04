"""The Studio bot (founder, 4 Nov 2026: "create separate bot for all this and X-rays"): everything creative the founder sends, apart from
the operations bot. A GitHub workflow polls it every few minutes.

  video or file captioned "intro <piece id>"   -> inbox/intro/<piece id>.mp4, pushed; the intro sweep merges it (engine/intro.py)
  photo or image file captioned "thumb <piece id>" -> inbox/thumb/<piece id>.jpg, pushed; set as the piece's YouTube thumbnail when it is uploaded
  any other video                               -> a Reel X-ray (engine/xray.py), the breakdown saved under logs/xray/
  /help, /start                                 -> the list above

Secrets: TELEGRAM_STUDIO_TOKEN (the new bot), TELEGRAM_CHAT_ID (the founder's own chat: a private chat id is the same for every bot).
Only that chat is obeyed."""
import json
import re
import sys
import urllib.request
from pathlib import Path

from . import gitsync, pieces, secrets, telegram, xray, youtube
from .config import ROOT

INTRO_RE = re.compile(r"^\s*intro\s+(\d{4}-\d{2}-\d{2}-(?:sglearning|arthvan)-(?:short|long))\s*$", re.I)
THUMB_RE = re.compile(r"^\s*thumb\s+(\d{4}-\d{2}-\d{2}-(?:sglearning|arthvan)-(?:short|long))\s*$", re.I)
HELP = ("🎬 SG Studio. Send me:\n"
        "• your 10-second intro as a FILE (paperclip → File, so Telegram keeps 1080p) with the caption: intro <piece id>\n"
        "• a thumbnail image with the caption: thumb <piece id>\n"
        "• any other Reel's video (under 20 MB): a Reel X-ray, why it works and what to copy\n"
        "Piece ids look like 2026-11-07-sglearning-short. Answers can take 5-10 minutes: I check every few minutes.")


def config(env=None) -> dict:
    try:
        return {"token": secrets.get("TELEGRAM_STUDIO_TOKEN", env), "chat_id": secrets.get("TELEGRAM_CHAT_ID", env)}
    except secrets.MissingSecret:
        return {}


def _call(token: str, method: str, body: dict) -> dict:
    req = urllib.request.Request(f"{telegram.API.split('/bot')[0]}/bot{token}/{method}", data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120, context=secrets.ssl_context()) as r:
        return json.loads(r.read())


def send(cfg: dict, text: str, call=_call) -> None:
    call(cfg["token"], "sendMessage", {"chat_id": cfg["chat_id"], "text": secrets.scrub(text)[:4000], "disable_web_page_preview": True})


def download(cfg: dict, file_id: str, out: Path, call=_call) -> Path:
    path = call(cfg["token"], "getFile", {"file_id": file_id})["result"]["file_path"]
    base = telegram.API.split("/bot")[0]
    with urllib.request.urlopen(f"{base}/file/bot{cfg['token']}/{path}", timeout=180, context=secrets.ssl_context()) as r:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(r.read())
    return out


def intro_reply(cfg: dict, message: dict, pid: str, root: Path, *, call=_call, fetch=download, commit=gitsync.commit) -> str:
    v = xray.video_of(message)
    if (v.get("file_size") or 0) > xray.MAX_BYTES:
        return "🎬 That intro is over 20 MB, the most a bot can download. Export at 1080x1920 but a lower bitrate, or send it as a normal video."
    out = Path(root) / "inbox" / "intro" / f"{pid}.mp4"
    fetch(cfg, v["file_id"], out, call)
    try:
        commit(root, f"intro clip for {pid}", paths=["inbox/intro"])
    except Exception as e:
        return f"🎬 Intro for {pid} downloaded but could not be saved: {secrets.scrub(str(e))[:160]}. Send it again in a few minutes."
    secs = v.get("duration")
    known = pieces.load(pid, root)
    state = f" The piece is {known.status}." if known else " (No piece with that id yet: it will be used when the piece is made.)"
    return f"🎬 Intro for {pid} saved ({out.stat().st_size / 1e6:.1f} MB{f', {secs} s' if secs else ''}).{state} It is merged on the next sweep."


def thumb_reply(cfg: dict, message: dict, pid: str, root: Path, env=None, *, call=_call, fetch=download, commit=gitsync.commit,
                token_for=youtube.access_token, set_thumb=youtube.set_thumbnail) -> str:
    img = xray.image_of(message)
    out = Path(root) / "inbox" / "thumb" / f"{pid}.jpg"
    fetch(cfg, img["file_id"], out, call)
    try:
        commit(root, f"thumbnail for {pid}", paths=["inbox/thumb"])
    except Exception as e:
        return f"🖼 Thumbnail for {pid} downloaded but could not be saved: {secrets.scrub(str(e))[:160]}."
    piece = pieces.load(pid, root)
    if piece and piece.ids.get("yt_id"):
        ok = set_thumb(token_for(piece.channel, env), piece.ids["yt_id"], out)
        return f"🖼 Thumbnail for {pid} saved and {'set on YouTube' if ok else 'saved, but YouTube refused it (JPG under 2 MB?)'}."
    return f"🖼 Thumbnail for {pid} saved; it is set on YouTube once the piece is uploaded."


def xray_reply(cfg: dict, message: dict, root: Path, *, call=_call, fetch=download, analyse=xray.analyse, commit=gitsync.commit) -> str:
    import tempfile
    v = xray.video_of(message)
    note = (message.get("caption") or "").replace("/xray", "").strip()
    if (v.get("file_size") or 0) > xray.MAX_BYTES:
        return "🎬 That video is over 20 MB, the most a bot can download. Send it as a normal video (Telegram compresses it), or trim it."
    with tempfile.TemporaryDirectory() as tmp:
        path = fetch(cfg, v["file_id"], Path(tmp) / "reel.mp4", call)
        try:
            text = analyse(path, note)
        except Exception as e:
            return f"🎬 Reel X-ray failed: {secrets.scrub(str(e))[:200]}. Send the video again in a few minutes."
    saved = xray.save(root, note, text)
    try:
        commit(root, "Reel X-ray from the Studio bot", paths=["logs/xray"])
    except Exception as e:
        print(f"could not save the X-ray to git: {e}")
    return "🎬 Reel X-ray\n\n" + text[:3900]


def poll(cfg: dict, root: Path = ROOT, env=None, *, call=_call, send_fn=None, intro_fn=intro_reply, thumb_fn=thumb_reply, xray_fn=xray_reply) -> list:
    """Answers every waiting message from the founder's chat, confirming each so it is handled once. Returns [(kind, piece id or "")]."""
    say = send_fn or (lambda text: send(cfg, text, call))
    updates = call(cfg["token"], "getUpdates", {"timeout": 0, "allowed_updates": ["message"]}).get("result", [])
    done = []
    for u in updates:
        m = u.get("message") or {}
        call(cfg["token"], "getUpdates", {"offset": u["update_id"] + 1, "timeout": 0})      # confirmed first: never handled twice
        if str((m.get("chat") or {}).get("id")) != str(cfg["chat_id"]):
            continue
        caption = m.get("caption") or ""
        text = (m.get("text") or "").strip()
        mi, mt = INTRO_RE.match(caption), THUMB_RE.match(caption)
        if xray.video_of(m) and mi:
            say(intro_fn(cfg, m, mi.group(1).lower(), root, call=call)); done.append(("intro", mi.group(1).lower()))
        elif xray.image_of(m) and mt:
            say(thumb_fn(cfg, m, mt.group(1).lower(), root, env, call=call)); done.append(("thumb", mt.group(1).lower()))
        elif xray.video_of(m):
            say("🎬 Got the Reel. Watching it now, the X-ray comes in a minute or two.")
            say(xray_fn(cfg, m, root, call=call)); done.append(("xray", ""))
        elif text.startswith("/"):
            say(HELP); done.append(("help", ""))
        elif text:
            say("I only take intros, thumbnails and Reel videos here. /help lists the captions."); done.append(("text", ""))
    return done


def main() -> int:
    cfg = config()
    if not cfg:
        print("the Studio bot is not set up (TELEGRAM_STUDIO_TOKEN / TELEGRAM_CHAT_ID)")
        return 0
    done = poll(cfg)
    for kind, pid in done:
        print(f"handled {kind} {pid}".strip())
    print(f"handled {len(done)} message(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
