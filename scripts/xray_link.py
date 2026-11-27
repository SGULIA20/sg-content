"""X-ray of a YouTube video from its link, and of a channel from its handle (founder, 27 Nov 2026: "Do xray of this video ... now these
are really trending", with a video too large for the bot: Telegram bots cannot download more than 20 MB). Gemini watches the video
straight from YouTube, so nothing is uploaded and there is no size limit. For a channel, its most-viewed recent videos are watched and
Claude says what the channel does and what we can take from it. Read-only: the breakdown is saved under logs/xray/ and sent to Telegram.

    python scripts/xray_link.py --video <link or id> [--channel @handle] [--note "..."]
"""
import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import gemini, secrets, telegram, youtube, ytresearch  # noqa: E402
from engine.config import ROOT  # noqa: E402

MODEL = "gemini-3.8-flash"
DATA = "https://www.googleapis.com/youtube/v3"
TOP = 3
XRAY = """Watch this video with its sound, all of it. The owner of two small Hindi/Hinglish channels (Learning with SG: learn anything, explained
plainly; SG-MYTH-WORLD: myths of the world and the reason behind each) wants to make videos that look and move like this one, using AI
tools only. His note: {note}

Describe what you see and hear; never guess a number you cannot observe. Plain English, these headings:
1. WHAT IT IS: subject, total length, and whether it looks AI-generated (video, pictures, voice) and why you think so.
2. FIRST 5 SECONDS: exactly what is shown and said, shot by shot, and why a viewer stays.
3. SHOT LIST of the first 60 seconds: time, what is on screen, how the camera moves, how long the shot lasts.
4. HOW THE PICTURES ARE MADE: AI moving video, AI stills given movement, animation, real footage; the visual style in detail (lighting,
   colour, lens, realism or cartoon, how characters and places stay the same from shot to shot).
5. EFFECTS AND TRANSITIONS: every kind used (cuts, zooms, whip pans, speed changes, glows, particles, screen shake, text animation), and how often.
6. PACE: picture changes per 10 seconds at the start, in the middle and at the end.
7. VOICE AND WORDS: who speaks (human or synthetic), language, energy, sentence length; the opening line word for word.
8. TEXT ON SCREEN: captions and labels, size, position, colour, how they animate.
9. SOUND: music style and loudness against the voice; sound effects and what they are timed to.
10. STORY SHAPE: the beats in order with rough times; where the main payoff comes; how it ends.
11. RECREATE IT WITH AI: a style guide of 6-8 lines someone could paste into an AI video tool to get this look, then FIVE example prompts
    for 10-second clips in this style (each with 3 shots), two for a Learning with SG subject and three for an SG-MYTH-WORLD subject.
12. DO NOT COPY: anything that is another creator's own character, footage, music or catchphrase, or that would break YouTube or Instagram rules.
At most 900 words."""
BRIEF = """Watch this video with its sound and note, briefly, how it is made: pictures (AI video, AI stills, animation, real footage), picture
changes per 10 seconds, voice (human or synthetic, energy), captions, music and sound effects, total length, the opening line, and the one
thing in how it is made that most keeps a viewer watching. At most 160 words; describe only what you observe."""
CHANNEL = """You advise the owner of two small Hindi/Hinglish channels (Learning with SG: learn anything; SG-MYTH-WORLD: myths of the world and
the reason behind each). Below are notes on the most-viewed recent videos of the channel {handle} ({subs} subscribers), each watched once,
and how the owner's videos are made now. Say what this channel does again and again that he can do too with AI tools and code, without
copying its characters, footage or music, and without him appearing on camera beyond a short opening clip.

Plain English, at most 300 words: THE FORMULA (5 lines, each with how many of the watched videos show it), TAKE THESE (4 concrete changes,
most valuable first), LEAVE THESE (what not to copy and why), and one line on how far {n} videos can be trusted.

WATCHED
{notes}

OURS NOW: an 8-second opening clip of the presenter (AI video), then AI still pictures cut into framings of about 2.5 seconds, a few scenes
as AI moving clips, a synthetic Hinglish narrator, two-line captions, quiet music; 60-100 seconds for a Short, 8-14 minutes for a long."""


def video_id(text: str) -> str:
    m = re.search(r"(?:youtu\.be/|v=|shorts/|embed/)([A-Za-z0-9_-]{11})", text) or re.fullmatch(r"([A-Za-z0-9_-]{11})", text.strip())
    return m.group(1) if m else ""


def handle_of(text: str) -> str:
    m = re.search(r"@([A-Za-z0-9._-]+)", text)
    return "@" + m.group(1) if m else ""


def watch(vid: str, prompt: str, tokens: int = 6000) -> str:
    body = {"contents": [{"parts": [{"file_data": {"file_uri": f"https://www.youtube.com/watch?v={vid}"}}, {"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": tokens, "temperature": 0.2}}
    return gemini.text(gemini.generate(MODEL, body)).strip()


def top_videos(handle: str, token: str, call=youtube.call) -> tuple:
    """(subscribers, [{"id", "title", "views", "seconds"}]) : the channel's most-viewed videos among its last 50 uploads."""
    status, _h, body = call("GET", f"{DATA}/channels?part=contentDetails,statistics&forHandle={handle}", token)
    items = (body.get("items") or []) if status == 200 else []
    if not items:
        return 0, []
    uploads = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
    status, _h, body = call("GET", f"{DATA}/playlistItems?part=contentDetails&maxResults=50&playlistId={uploads}", token)
    ids = [i["contentDetails"]["videoId"] for i in (body.get("items") or [])] if status == 200 else []
    status, _h, body = call("GET", f"{DATA}/videos?part=snippet,statistics,contentDetails&id={','.join(ids)}", token)
    rows = [{"id": v["id"], "title": v["snippet"]["title"], "views": int(v["statistics"].get("viewCount", 0)),
             "seconds": ytresearch._seconds(v["contentDetails"].get("duration", "")), "published": v["snippet"]["publishedAt"][:10]}
            for v in (body.get("items") or [])] if status == 200 else []
    return int(items[0]["statistics"].get("subscriberCount", 0)), sorted(rows, key=lambda r: -r["views"])


def ask_claude(prompt: str) -> str:
    import anthropic
    client = anthropic.Anthropic(api_key=secrets.get("ANTHROPIC_API_KEY"))
    r = client.messages.create(model="claude-opus-5-5", max_tokens=8000, messages=[{"role": "user", "content": prompt}])
    return "".join(getattr(b, "text", "") for b in r.content).strip()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", default=""); ap.add_argument("--channel", default=""); ap.add_argument("--note", default="")
    a = ap.parse_args(argv)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M%S")
    out_dir = ROOT / "logs" / "xray"
    out_dir.mkdir(parents=True, exist_ok=True)
    vid = video_id(a.video)
    if vid:
        text = watch(vid, XRAY.format(note=a.note or "none"))
        (out_dir / f"{stamp}-{vid}.md").write_text(f"# Video X-ray from a link, {stamp[:10]}\n\nhttps://youtu.be/{vid}\nNote: {a.note or '-'}\n\n{text}\n")
        print(text, flush=True)
        for i in range(0, min(len(text), 11000), 3800):
            telegram.send(("🎬 Video X-ray (from your link)\n\n" if i == 0 else "") + text[i:i + 3800])
    handle = handle_of(a.channel)
    if handle:
        subs, rows = top_videos(handle, youtube.access_token("sglearning"))
        notes = []
        for r in rows[:TOP]:
            try:
                notes.append(f"[{r['views']:,} views, {r['seconds']} s, {r['published']}] {r['title']}\n{watch(r['id'], BRIEF, 2500)}")
            except Exception as e:                            # noqa: BLE001
                print(f"could not watch {r['id']}: {type(e).__name__}: {secrets.scrub(str(e))[:160]}", flush=True)
        listing = "\n".join(f"{r['views']:>12,}  {r['seconds']:>5} s  {r['published']}  {r['title'][:70]}" for r in rows[:12])
        advice = ask_claude(CHANNEL.format(handle=handle, subs=f"{subs:,}", n=len(notes), notes="\n\n".join(notes))) if notes else "No video of this channel could be watched."
        text = f"Channel {handle}: {subs:,} subscribers. Most-viewed of its last {len(rows)} uploads:\n{listing}\n\n{advice}"
        (out_dir / f"{stamp}-{handle[1:]}.md").write_text(f"# Channel X-ray, {stamp[:10]}\n\n{text}\n\n## Notes on the watched videos\n\n" + "\n\n".join(notes) + "\n")
        print(text, flush=True)
        telegram.send("📺 Channel X-ray " + handle + "\n\n" + advice[:3700])
    if not vid and not handle:
        print("nothing to do: give --video and/or --channel")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
