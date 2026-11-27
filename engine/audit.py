"""The full audit of a finished video, with its sound (founder, 27 Nov 2026: "This could be standard for us so we need perfection from
visual to narration to script to everything. Before uploading we need to do audit").

The picture review (engine/watch.py) looks at still frames. This one WATCHES the finished file from start to end with its sound, the
way a viewer does, holding the script beside it: is every line spoken clearly and correctly, does the picture at each moment show
what is being said, do the captions match the voice, is the voice ever buried by the music, do faces, hands or movement glitch, does the
hero stay the same person, does the opening earn the first three seconds, does it end cleanly. It returns a score, a verdict and a list
of faults with their time and a fix. A contact sheet of the video (one frame every two seconds, time printed on each) is saved beside
the report so a person can check the same things by eye.

Report only: it never changes or stops a video by itself.
"""
import json
import re
import subprocess
from pathlib import Path

from . import secrets, xray

PASS_MARK = 8
PROMPT = """You are the final quality check before a short video is published on a Hindi/Hinglish channel. Watch ALL of it with the sound
on, as a first-time viewer on a phone. The script it was made from is below, one line per scene.

Check each of these and report only what you actually see and hear, with the time in seconds:
1. NARRATION: every script line is spoken, in order, clearly; any word mispronounced, swallowed, repeated, cut off or spoken in the wrong
   language; any place the voice sounds robotic, rushed or flat; any gap of silence longer than a second.
2. PICTURE AGAINST WORDS: at each line, does the picture on screen show what is being said then? Name every moment where the picture is
   about something else, comes too early or too late, or repeats.
3. CAPTIONS: do the words on screen match the spoken words; any spelling mistake, wrong word, text cut off at an edge, text over a face.
4. SOUND: is the voice ever hard to hear under the music; any click, jump in loudness or sudden silence; does the music suit the story.
5. PICTURE QUALITY: warped faces, extra or missing fingers or limbs, objects that melt or pop, jerky or ghosted movement, slow motion
   that looks dragged, a person who changes face, age or clothes between shots, blur, black frames.
6. OPENING: what the first 3 seconds show and say; would a stranger keep watching, and why or why not.
7. ENDING: does the last line land, or is it cut short or left hanging by accident.
8. RESPECT AND RULES: anything disrespectful to a faith or a people, gore, a real person's likeness, a brand or a copyrighted character.

Be strict: this video sets the standard for the channel. Do not praise. Reply with JSON only:
{{"score": 0-10, "verdict": "publish | fix first | remake",
 "faults": [{{"at": seconds, "kind": "narration | picture-words | captions | sound | quality | opening | ending | respect", "what": "plain words", "fix": "what to change"}}],
 "strongest": "the best moment and why, one sentence", "weakest": "the worst moment and why, one sentence",
 "lines_heard": how many of the {n} script lines you heard spoken}}
At most 14 faults, the most serious first.

SCRIPT
{script}"""


def sheet(video: Path, out: Path, every: float = 2.0, cols: int = 8) -> Path:
    """One frame every `every` seconds, the time printed on each, tiled into one picture."""
    out.parent.mkdir(parents=True, exist_ok=True)
    seconds = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(video)],
                                   capture_output=True, text=True, check=True).stdout.strip() or 0)
    n = max(1, int(seconds // every) + 1)
    rows = (n + cols - 1) // cols
    stamp = f"drawtext=text='%{{eif\\:t\\:d}}s':x=6:y=6:fontsize=22:fontcolor=white:box=1:boxcolor=black@0.6"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(video), "-vf", f"fps=1/{every},scale=216:-2,{stamp},tile={cols}x{rows}",
                    "-frames:v", "1", "-q:v", "4", str(out)], check=True, capture_output=True)
    return out


def watch(video: Path, piece, *, key: str | None = None, req=xray._req) -> dict:
    """The audit itself: {"score", "verdict", "faults", ...}. Raises when the video cannot be watched."""
    key = secrets.get("GEMINI_API_KEY") if key is None else key
    scenes = (piece.script or {}).get("scenes") or []
    script = "\n".join(f"{i + 1}. {sc.get('vo', '')}" for i, sc in enumerate(scenes))
    f = xray.upload(video, key, req=req)
    body = {"contents": [{"parts": [{"file_data": {"mime_type": f.get("mimeType", "video/mp4"), "file_uri": f["uri"]}},
                                    {"text": PROMPT.format(n=len(scenes), script=script)}]}],
            "generationConfig": {"maxOutputTokens": 8000, "temperature": 0.1}}
    _h, raw = req(f"{xray.BASE}/v1beta/models/{xray.MODEL}:generateContent", method="POST", data=json.dumps(body).encode(),
                  headers={"Content-Type": "application/json", "x-goog-api-key": key}, timeout=600)
    text = "".join(p.get("text", "") for p in json.loads(raw)["candidates"][0]["content"]["parts"])
    return json.loads(re.search(r"\{.*\}", text, re.S).group(0))


def report(piece_id: str, r: dict) -> str:
    """The audit in plain words, for Telegram and the log."""
    ok = r.get("verdict") == "publish" and (r.get("score") or 0) >= PASS_MARK
    lines = [f"{'✅' if ok else '🔎'} Audit of {piece_id}: {r.get('score', '?')}/10, {r.get('verdict', '?')}"
             f" ({r.get('lines_heard', '?')} script lines heard)"]
    for f in (r.get("faults") or [])[:14]:
        lines.append(f"• {f.get('at', '?')}s [{f.get('kind', '')}] {f.get('what', '')} → {f.get('fix', '')}")
    if r.get("strongest"):
        lines.append(f"Best: {r['strongest']}")
    if r.get("weakest"):
        lines.append(f"Weakest: {r['weakest']}")
    return "\n".join(lines)


def run(video: Path, piece, out_dir: Path, notify=None) -> dict | None:
    """Sheet, audit, report; saved as <out_dir>/sheet.jpg and audit.json. Never raises: a failed audit is printed, the video is untouched."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        sheet(video, out_dir / "sheet.jpg")
    except Exception as e:                                    # noqa: BLE001
        print(f"audit: no contact sheet ({type(e).__name__}: {str(e)[:120]})", flush=True)
    try:
        r = watch(video, piece)
    except Exception as e:                                    # noqa: BLE001
        print(f"audit: the video could not be watched ({type(e).__name__}: {secrets.scrub(str(e))[:160]})", flush=True)
        return None
    (out_dir / "audit.json").write_text(json.dumps(r, indent=1, ensure_ascii=False) + "\n")
    text = report(piece.id, r)
    print(text, flush=True)
    if notify:
        notify(text[:3900])
    return r
