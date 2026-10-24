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
WINDOW = timedelta(days=3)
MAX_DRAFTS = 12
PROMPT = """You reply as SG, the creator of the YouTube channel "{channel}" ({about}), to one viewer comment.
Write ONE short reply (at most 2 sentences) in the same language and script the viewer used (Hinglish stays Hinglish).
Warm, specific to what they said, never salesy. Never give personal financial advice or promise returns; for a money question,
point them to the video's idea and suggest checking with an adviser. Never mention any app. No hashtags.
If the comment is spam, abuse, only an emoji, or needs no answer, reply exactly SKIP.

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
    msg = client.messages.create(model=MODEL, max_tokens=300, messages=[{"role": "user", "content": PROMPT.format(
        channel=CHANNELS[channel].display_name, about=ABOUT[channel], title=title, author=comment["author"], text=comment["text"])}])
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()
    return None if not text or text.upper().startswith("SKIP") else text[:500]


def post_reply(token: str, parent_id: str, text: str, call=youtube.call) -> str:
    status, _h, body = call("POST", f"{API}/comments?part=snippet", token, json_body={"snippet": {"parentId": parent_id, "textOriginal": text}})
    if status != 200:
        raise youtube.YouTubeError(f"reply {status}: {secrets.scrub(str(body))[:160]}")
    return body.get("id", "")


def run(env=None, now: datetime | None = None, root: Path = ROOT, state_path: Path = STATE, call=youtube.call, client=None,
        sync=command_center.replies_sync, token_for=youtube.access_token) -> dict:
    now = now or datetime.now(timezone.utc)
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
            if text:
                drafts.append({**c, "channel": ch, "draft": text})
    if drafts or posted or failed:
        sync(drafts, posted, failed, root=root, env=env)
    cutoff = (now - timedelta(days=14)).isoformat()
    state["seen"] = {k: v for k, v in seen.items() if v >= cutoff}
    Path(state_path).parent.mkdir(parents=True, exist_ok=True)
    Path(state_path).write_text(json.dumps(state, indent=1))
    return {"posted": len(posted), "failed": len(failed), "drafts": len(drafts)}


def main(argv=None) -> int:
    try:
        print(run())
    except Exception as e:
        print("yt replies failed:", secrets.scrub(str(e))[:200])
    return 0


if __name__ == "__main__":
    sys.exit(main())
