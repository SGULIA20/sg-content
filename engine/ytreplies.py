"""YouTube comment replies (founder, 24 Oct 2026). Every few hours: new comments on both channels get a short reply drafted by
Claude in the commenter's language; each draft goes to the founder's Telegram with Post / Skip buttons (through the control room).
Approved drafts are posted on the next run, which the Post button starts at once. Spam, abuse and comments that need no answer
get no draft. Each comment is drafted once (logs/yt-replies.json). After two weeks the founder may let friendly replies go
automatically; until then every reply waits for a tap.

python -m engine.ytreplies
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import command_center, secrets, youtube
from .config import CHANNELS, ROOT

API = "https://www.googleapis.com/youtube/v3"
STATE = ROOT / "logs" / "yt-replies.json"
MODEL = "claude-haiku-5-5"
WINDOW = timedelta(days=10)          # 24 Nov 2026: was 3 days; comments from 18-21 Nov sat unanswered and are picked up once more
AUTO_FILE = ROOT / "content" / "replies.json"   # {"auto": true}: friendly replies are posted at once (founder, 24 Nov 2026)
MAX_DRAFTS = 12
PROMPT = """You reply as SG, the creator of the YouTube channel "{channel}" ({about}), to one viewer comment.
Write ONE short reply (at most 2 sentences) in the same language and script the viewer used (Hinglish stays Hinglish).
Warm, specific to what they said, never salesy. Never give personal financial advice or promise returns; for a money question,
point them to the video's idea and suggest checking with an adviser. Never mention any app. No hashtags.
A short praise, a greeting, a devotional line ("Jai Shri Ram") or only an emoji still gets a brief warm thank-you in the viewer's script.
Only if the comment is spam, an advertisement or abuse, reply exactly SKIP.

Video title: {title}
Comment by {author}: {text}"""
ABOUT = {"sglearning": "money stories for Indian families", "arthvan": "Indian history and mythology, with the evidence"}


def _when(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def new_comments(token: str, now: datetime, seen: dict, call=youtube.call) -> list:
    """Top-level comments from the last three days that are not the channel's own and were not drafted before."""
    status, _h, me = call("GET", f"{API}/channels?part=id&mine=true", token)
    if status != 200 or not me.get("items"):
        raise youtube.YouTubeError(f"channel not readable ({status})")
    own = me["items"][0]["id"]
    status, _h, body = call("GET", f"{API}/commentThreads?part=snippet&allThreadsRelatedToChannelId={own}&maxResults=50&order=time", token)
    if status != 200:
        raise youtube.YouTubeError(f"comments not readable ({status}): {secrets.scrub(str(body))[:160]}")
    out = []
    for item in body.get("items", []):
        top = item["snippet"]["topLevelComment"]
        s = top["snippet"]
        if top["id"] in seen or (s.get("authorChannelId") or {}).get("value") == own or now - _when(s["publishedAt"]) > WINDOW:
            continue
        if int(item["snippet"].get("totalReplyCount") or 0) > 0:        # already answered (by him in the app, or an earlier run)
            continue
        out.append({"comment_id": top["id"], "video_id": s.get("videoId", ""), "author": s.get("authorDisplayName", ""),
                    "text": (s.get("textOriginal") or "")[:1000]})
    return out


def video_title(token: str, video_id: str, call=youtube.call) -> str:
    status, _h, body = call("GET", f"{API}/videos?part=snippet&id={video_id}", token)
    items = body.get("items") or []
    return items[0]["snippet"]["title"] if status == 200 and items else ""


def draft(channel: str, comment: dict, title: str, client=None) -> str | None:
    import anthropic
    client = client or anthropic.Anthropic(api_key=secrets.get("ANTHROPIC_API_KEY"))
    # 24 Nov 2026: the first automatic run read four comments and wrote no reply to any. 300 tokens leaves no room once the model thinks
    # first, and an empty answer was taken for SKIP. An empty answer is now an error (the comment is tried again next run).
    msg = client.messages.create(model=MODEL, max_tokens=2000, messages=[{"role": "user", "content": PROMPT.format(
        channel=CHANNELS[channel].display_name, about=ABOUT[channel], title=title, author=comment["author"], text=comment["text"])}])
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()
    if not text:
        raise RuntimeError(f"no reply text (stop: {getattr(msg, 'stop_reason', '?')})")
    skip = text.upper().startswith("SKIP")
    print(f"comment by {comment['author'][:20]}: \"{comment['text'][:60]}\" -> {'SKIP' if skip else 'reply'}", flush=True)
    return None if skip else text[:500]


def post_reply(token: str, parent_id: str, text: str, call=youtube.call) -> str:
    status, _h, body = call("POST", f"{API}/comments?part=snippet", token, json_body={"snippet": {"parentId": parent_id, "textOriginal": text}})
    if status != 200:
        raise youtube.YouTubeError(f"reply {status}: {secrets.scrub(str(body))[:160]}")
    return body.get("id", "")


def auto_on(path: Path = AUTO_FILE) -> bool:
    try:
        return bool(json.loads(Path(path).read_text()).get("auto"))
    except (OSError, ValueError):
        return False


def run(env=None, now: datetime | None = None, root: Path = ROOT, state_path: Path = STATE, call=youtube.call, client=None,
        sync=command_center.replies_sync, token_for=youtube.access_token, auto: bool | None = None, notify=None) -> dict:
    """auto (founder, 24 Nov 2026: "why automated reply on reels and videos not on ... 4-5 comments so far but no revert"): each drafted
    reply is posted at once and he is told what was said; a reply YouTube refuses stays a draft for his tap. The drafts had been going to
    the control room, which answers nothing when it is not live, so no reply had ever been posted."""
    now = now or datetime.now(timezone.utc)
    auto = auto_on() if auto is None else auto
    if notify is None:
        from . import telegram
        notify = telegram.send
    sent = []
    try:
        state = json.loads(Path(state_path).read_text())
    except (FileNotFoundError, ValueError):
        state = {}
    seen = state.setdefault("seen", {})
    tokens = {}

    def token(ch):
        if ch not in tokens:
            tokens[ch] = token_for(ch, env)
        return tokens[ch]

    approved = sync([], [], root=root, env=env) or []
    posted, failed = [], []
    for a in approved:                                                   # 1: post what the founder approved
        try:
            post_reply(token(a["channel"]), a["comment_id"], a["draft"], call)
            posted.append(a["id"])
        except Exception as e:
            print(f"reply {a['id']} not posted: {str(e)[:160]}", flush=True)
            failed.append(a["id"])
    drafts = []
    for ch in CHANNELS:                                                  # 2: draft replies to new comments
        try:
            comments = new_comments(token(ch), now, seen, call)
        except Exception as e:
            print(f"{ch}: comments not read: {str(e)[:160]}", flush=True)
            continue
        for c in comments:
            if len(drafts) >= MAX_DRAFTS:
                break
            seen[c["comment_id"]] = now.isoformat(timespec="seconds")
            try:
                text = draft(ch, c, video_title(token(ch), c["video_id"], call), client)
            except Exception as e:
                print(f"draft failed: {str(e)[:160]}", flush=True)
                del seen[c["comment_id"]]                              # try again next run
                continue
            if text and auto:
                try:
                    post_reply(token(ch), c["comment_id"], text, call)
                    sent.append(f"{CHANNELS[ch].display_name}, {c['author']}: \"{c['text'][:80]}\"\n   ↳ {text}")
                    continue
                except Exception as e:
                    print(f"auto reply not posted: {str(e)[:160]}", flush=True)
            if text:
                drafts.append({**c, "channel": ch, "draft": text})
    if drafts or posted or failed:
        sync(drafts, posted, failed, root=root, env=env)
    if sent:
        notify("💬 Replied on YouTube for you:\n\n" + "\n\n".join(sent[:10]))
    cutoff = (now - timedelta(days=14)).isoformat()
    state["seen"] = {k: v for k, v in seen.items() if v >= cutoff}
    Path(state_path).parent.mkdir(parents=True, exist_ok=True)
    Path(state_path).write_text(json.dumps(state, indent=1))
    return {"posted": len(posted), "failed": len(failed), "drafts": len(drafts), "auto": len(sent)}


def main(argv=None) -> int:
    try:
        print(run())
    except Exception as e:
        print("yt replies failed:", secrets.scrub(str(e))[:200])
    return 0


if __name__ == "__main__":
    sys.exit(main())
