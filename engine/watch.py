"""The finished video is looked at before it goes up (founder, 24 Nov 2026: "yes, run the test": the unused part of the monthly API
credit is spent on what loses viewers). Until now only the file was checked (length, loudness, frozen frames); nobody looked at the
pictures. The 21 Nov trailer gap, a banner emoji drawn as a box and an app screen that did not match its line were all found by hand.

Claude sees one frame of every scene (the opening scenes always, then an even spread) beside the line spoken over it, and answers:
does the first second stop the thumb, does each picture show what its line says, is any frame dark, dull, garbled or a repeat. The
answer is stored on the piece (ids.watch) and sent to the founder only when something is wrong. REPORT ONLY in this first version:
nothing is re-made and no upload is held back; a week of reports decides which findings are worth an automatic redo.

python -m engine.watch <piece id>      # look at a made piece again (out/<id>/reel.mp4 or long.mp4)
"""
import base64
import json
import re
import subprocess
import sys
from pathlib import Path

from . import pieces, secrets
from .config import CHANNELS, ROOT

MODEL = "claude-opus-5-5"
FRAMES_SHORT, FRAMES_LONG = 12, 20       # a Short has 8-13 scenes; a long is sampled, with its first half-minute in full
OPENING = 4                              # the first scenes are always looked at: that is where viewers leave
WIDTH = 480                              # frames are shrunk: enough to read a caption, cheap to send
PASS_MARK = 7                            # opening score out of 10 below which the founder is told
PROMPT = """You are the last check before a {kind} goes up on the YouTube channel "{channel}" ({about}). Viewers decide in the first
second whether to stay. Below are frames of the finished video in order, each followed by the second it was taken at and the line
spoken over it. The title is: {title}

Judge it as a viewer who is scrolling, not as its maker:
1. OPENING (0-10): would the first frame and the first line stop a scrolling thumb? 10 = cannot look away, 5 = fine but skippable.
2. For every frame, a problem only if a viewer would notice it: the picture does not show what the line says; it is dark, grey or
   empty; text in it is garbled, boxed or cut off; a face or hand is deformed; it is nearly the same picture as the one before;
   the caption covers the subject.
3. The one change that would most help this video hold viewers.

Reply with JSON only:
{{"opening": <0-10>, "opening_why": "<one short sentence>",
  "issues": [{{"frame": <number>, "second": <number>, "problem": "<what a viewer sees>", "fix": "<what to change>"}}],
  "best_change": "<one sentence>", "verdict": "<good | fix>"}}
An empty issues list is a fine answer; do not invent problems."""
ABOUT = {"sglearning": "money explained for Indian families", "arthvan": "Indian mythology and history, with the evidence"}


def moments(timings: list, duration: float, kind: str) -> list:
    """(scene index, second) for the frames to look at: the first OPENING scenes, then an even spread, each a little after its scene starts."""
    limit = FRAMES_SHORT if kind == "short" else FRAMES_LONG
    starts = [float(t) for t in timings] or [duration * i / limit for i in range(limit)]
    idx = list(range(len(starts)))
    if len(idx) > limit:
        rest = idx[OPENING:]
        step = len(rest) / (limit - OPENING)
        idx = idx[:OPENING] + [rest[int(i * step)] for i in range(limit - OPENING)]
    out = []
    for i in idx:
        end = starts[i + 1] if i + 1 < len(starts) else duration
        out.append((i, round(min(duration - 0.1, starts[i] + min(1.0, max(0.2, (end - starts[i]) / 3))), 2)))
    return out


def frame(video: Path, second: float, out: Path) -> Path:
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{second:.2f}", "-i", str(video), "-frames:v", "1", "-vf", f"scale={WIDTH}:-2",
                    "-q:v", "5", str(out)], check=True, capture_output=True)
    return out


def _ask(content: list) -> str:
    import anthropic
    client = anthropic.Anthropic(api_key=secrets.get("ANTHROPIC_API_KEY"))
    r = client.messages.create(model=MODEL, max_tokens=8000, messages=[{"role": "user", "content": content}])
    try:
        from . import writer
        writer.record_spend(r.usage, writer.SPEND_FILE, None)
    except Exception:
        pass
    if r.stop_reason == "refusal":
        raise RuntimeError("the review was declined")
    return "".join(getattr(b, "text", "") for b in r.content).strip()


def review(piece, video: Path, work: Path, ask=_ask, grab=frame, duration: float | None = None) -> dict:
    """{"opening", "opening_why", "issues", "best_change", "verdict", "frames"}; raises when the answer cannot be read."""
    scenes = (piece.script or {}).get("scenes") or []
    if duration is None:
        from . import qa
        duration = qa.probe(video)["duration"]
    work = Path(work); work.mkdir(parents=True, exist_ok=True)
    content = [{"type": "text", "text": PROMPT.format(kind="Short" if piece.kind == "short" else "long video", channel=CHANNELS[piece.channel].display_name,
                                                      about=ABOUT.get(piece.channel, ""), title=(piece.script or {}).get("title", ""))}]
    picks = moments(list(piece.timings or [])[:len(scenes)] if scenes else [], duration, piece.kind)
    for n, (i, second) in enumerate(picks, start=1):
        jpg = grab(video, second, work / f"watch{n:02d}.jpg")
        content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": base64.standard_b64encode(Path(jpg).read_bytes()).decode()}})
        line = str(scenes[i].get("vo", "")) if i < len(scenes) else ""
        content.append({"type": "text", "text": f"Frame {n}, second {second:.0f}. Line: {line[:300]}"})
    raw = ask(content)
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        raise ValueError(f"no JSON in the review (starts: {raw[:120]!r})")
    data = json.loads(m.group(0))
    issues = [i for i in (data.get("issues") or []) if isinstance(i, dict) and i.get("problem")][:8]
    return {"opening": int(data.get("opening") or 0), "opening_why": str(data.get("opening_why") or "")[:200], "issues": issues,
            "best_change": str(data.get("best_change") or "")[:240], "verdict": "fix" if str(data.get("verdict")) == "fix" else "good", "frames": len(picks)}


def message(piece, r: dict) -> str:
    """What the founder is told; '' when the video is fine (nothing is sent)."""
    if r["verdict"] == "good" and r["opening"] >= PASS_MARK and not r["issues"]:
        return ""
    lines = [f"👀 {piece.id}: looked at before upload ({r['frames']} frames). Opening {r['opening']}/10: {r['opening_why']}"]
    for i in r["issues"][:5]:
        lines.append(f"• second {i.get('second', '?')}: {str(i['problem'])[:140]} → {str(i.get('fix', ''))[:120]}")
    if r["best_change"]:
        lines.append(f"Best single change: {r['best_change']}")
    lines.append("Report only: the video goes up as made. Tell Claude if you want it re-made.")
    return "\n".join(lines)


def on(root: Path = ROOT) -> bool:
    """content/watch.json {"on": false} switches the review off without a code change."""
    try:
        return bool(json.loads((Path(root) / "content" / "watch.json").read_text()).get("on", True))
    except (OSError, ValueError):
        return True


def look(piece, video: Path, out_dir: Path, notify=None, ask=_ask, grab=frame) -> dict | None:
    """Called by the pipeline after the file checks pass. Never stops a video: a failed review is printed and forgotten."""
    if not on():
        return None
    try:
        r = review(piece, video, Path(out_dir) / "watch", ask=ask, grab=grab)
    except Exception as e:
        print(f"watch: {piece.id} not reviewed ({type(e).__name__}: {secrets.scrub(str(e))[:160]})", flush=True)
        return None
    piece.ids["watch"] = {k: r[k] for k in ("opening", "verdict", "best_change")} | {"issues": len(r["issues"])}
    text = message(piece, r)
    print(f"watch: {piece.id} opening {r['opening']}/10, {len(r['issues'])} issue(s), {r['verdict']}", flush=True)
    if text and notify:
        notify(text)
    return r


def main(argv=None) -> int:
    from . import telegram
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print(__doc__)
        return 1
    piece = pieces.load(args[0], ROOT)
    out = ROOT / "out" / args[0]
    video = next((p for p in (out / "reel.mp4", out / "long.mp4", out / "story.mp4") if p.exists()), None)
    if piece is None or video is None:
        print(f"{args[0]}: no finished video in {out}")
        return 1
    r = look(piece, video, out, notify=None if "--quiet" in args else telegram.send)
    print(json.dumps(r, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
