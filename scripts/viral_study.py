"""What the week's most-viewed short videos do in the BODY that ours do not (founder, 27 Nov 2026: "if you have better ideas on painted
pictures and the AI narrator for the body of the video then suggest, advise from YouTube search viral reels").

Read-only study. For each channel it takes the most-viewed videos of up to three minutes that the planner already found this week
(content/weekly-plan.json "viral") plus the top results of a few short-video searches, has Gemini WATCH each one from its YouTube
address, and writes down how the body is made: what is on screen, how often it changes, who speaks, the sound. Claude then sets those
notes beside how our own videos are made and names the changes most worth trying. Nothing in the engine is changed.
Result: logs/viral-study.json.

    python scripts/viral_study.py
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import gemini, secrets, youtube, ytresearch  # noqa: E402
from engine.config import ROOT  # noqa: E402

MODEL = "gemini-3.8-flash"
PER_CHANNEL = 6
MAX_SECONDS = 180
SEARCHES = {"sglearning": ["facts in hindi shorts", "kya aap jante hain shorts", "explained in hindi shorts"],
            "arthvan": ["mythology facts hindi shorts", "history mystery hindi shorts", "ramayan mahabharat facts shorts"]}
WATCH = """Watch this short video with its sound. Describe only HOW IT IS MADE, in plain English, under these headings, briefly:
1. PICTURES: what is on screen through the body of the video: real camera footage, film or news clips, stock footage, a person talking to camera,
   screen recordings, animation, AI-generated moving video, AI-generated still pictures with a slow zoom, drawn cartoons, text cards. Give rough shares.
2. CHANGES: about how many times the picture changes in every 10 seconds, and what kind of change (hard cut, zoom, new clip).
3. MOTION: does anything inside the picture move (people, objects, camera), or are they stills?
4. VOICE: a real human voice or a synthetic one, male or female, its energy, and whether the speaker is ever seen.
5. TEXT: captions and words on screen: how big, where, one word at a time or full lines, colours.
6. SOUND: music, sound effects, silence.
7. LENGTH: total seconds, and in how many seconds the first surprising thing is shown.
8. ONE LINE: the single thing in how it is made that most keeps a viewer watching.
At most 220 words. Describe what you see and hear; do not guess numbers you cannot observe."""
OURS = """HOW OUR OWN VIDEOS ARE MADE NOW: a 6-12 second opening clip of the presenter (an AI-generated video of the founder walking toward the
camera, speaking the hook); then the body: one AI-painted or photoreal STILL picture per scene with a slow zoom or a small parallax movement,
9-13 scenes, each on screen 5-9 seconds; a synthetic (AI) Hindi/Hinglish narrator voice; two-line captions at the bottom with one word
highlighted; a quiet music track; 60-105 seconds for a Short, 8-14 minutes for a long. No real footage, no person on screen after the opening."""
ADVISE = """You advise a one-person Hindi/Hinglish YouTube and Instagram channel. Below are notes on how this week's most-viewed short videos
in its field are made (each was watched), then how the channel's own videos are made. The owner asks what to change in the BODY of his
videos: the pictures and the narrator.

Say only what the notes support, and say how many of the watched videos each point rests on. Everything proposed must be doable by one
person with AI tools and code (no film crew), must not copy another creator's footage, and must not need the owner on camera for more
than a short clip he already records.

Reply with JSON only:
{{"what_they_do": ["3-5 short lines: the patterns in how the watched videos' bodies are made, each with a count like '5 of 6'"],
 "gap": "2 sentences: the biggest difference between those and ours",
 "changes": [{{"change": "one concrete change to our body", "why": "which notes support it", "effort": "small | medium | large", "risk": "what could go wrong"}}],
 "do_not": ["things seen in the viral videos that this channel should NOT copy, and why"],
 "caveat": "one sentence on how far this small sample can be trusted"}}
At most 5 changes, the most promising first.

CHANNEL: {channel}

WATCHED VIDEOS
{notes}

{ours}"""


def candidates(channel: str, token: str, plan: dict) -> list:
    rows = {v["id"]: {"id": v["id"], "title": v.get("title", ""), "views": int(v.get("views") or 0)} for v in (plan.get("viral") or {}).get(channel, []) if v.get("id")}
    since = datetime.now(timezone.utc) - timedelta(days=14)
    for q in SEARCHES[channel]:
        for r in ytresearch.search(token, q, since, duration="short") or []:
            if not r.get("error") and r.get("id"):
                rows.setdefault(r["id"], {"id": r["id"], "title": r.get("title", ""), "views": int(r.get("views") or 0), "seconds": r.get("seconds")})
    ids = [i for i, r in rows.items() if "seconds" not in r]
    for i in range(0, len(ids), 50):
        status, _h, body = youtube.call("GET", f"https://www.googleapis.com/youtube/v3/videos?part=contentDetails&id={','.join(ids[i:i + 50])}", token)
        for v in (body.get("items") or []) if status == 200 else []:
            rows[v["id"]]["seconds"] = ytresearch._seconds(v["contentDetails"].get("duration", ""))
    short = [r for r in rows.values() if 0 < (r.get("seconds") or 0) <= MAX_SECONDS]
    return sorted(short, key=lambda r: -r["views"])[:PER_CHANNEL]


def watch(video_id: str) -> str:
    body = {"contents": [{"parts": [{"file_data": {"file_uri": f"https://www.youtube.com/watch?v={video_id}"}}, {"text": WATCH}]}],
            "generationConfig": {"maxOutputTokens": 3000, "temperature": 0.2}}
    return gemini.text(gemini.generate(MODEL, body)).strip()


def advise(channel: str, notes: list) -> dict:
    import re
    import anthropic
    client = anthropic.Anthropic(api_key=secrets.get("ANTHROPIC_API_KEY"))
    text = "\n\n".join(f"[{n['views']:,} views, {n.get('seconds')} s] {n['title']}\n{n['notes']}" for n in notes)
    r = client.messages.create(model="claude-opus-5-5", max_tokens=12000,
                               messages=[{"role": "user", "content": ADVISE.format(channel=channel, notes=text, ours=OURS)}])
    raw = "".join(getattr(b, "text", "") for b in r.content)
    return json.loads(re.search(r"\{.*\}", raw, re.S).group(0))


def main() -> int:
    plan = json.loads((ROOT / "content" / "weekly-plan.json").read_text())
    out = {"made": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    for channel in ("sglearning", "arthvan"):
        notes = []
        for v in candidates(channel, youtube.access_token(channel), plan):
            try:
                notes.append({**v, "notes": watch(v["id"])})
                print(f"{channel}: watched {v['id']} ({v['views']:,} views) {v['title'][:60]}", flush=True)
            except Exception as e:                            # noqa: BLE001  a video Gemini cannot open is skipped, the study goes on
                print(f"{channel}: could not watch {v['id']}: {type(e).__name__}: {secrets.scrub(str(e))[:160]}", flush=True)
        out[channel] = {"watched": notes}
        if len(notes) >= 3:
            try:
                out[channel]["advice"] = advise(channel, notes)
            except Exception as e:                            # noqa: BLE001
                out[channel]["advice_error"] = f"{type(e).__name__}: {secrets.scrub(str(e))[:200]}"
    (ROOT / "logs" / "viral-study.json").write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    print(json.dumps({ch: out[ch].get("advice") or out[ch].get("advice_error") or f"only {len(out[ch]['watched'])} watched" for ch in ("sglearning", "arthvan")}, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
