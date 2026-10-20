"""Paste-and-drop: file the founder's Gemini clips from ~/Downloads, check them against the pack, ask for one confirmation, build and upload
(docs/spec-gemini-clips.md §3-6).

python -m engine.inbox --tick          every 2 minutes from launchd
python -m engine.inbox --cmd "ok <id>" apply a Telegram command by hand
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import digest, lint, pieces, qa, slots, telegram
from .config import ROOT

DOWNLOADS = Path.home() / "Downloads"
INBOX = Path.home() / "Desktop" / "SG-Content-Project" / "Inbox"
STATE = ROOT / "logs" / "inbox-state.json"
CLIP_GLOB = "gemini_generated_video_*.mp4"
SIMILARITY_MIN = 0.6


# ---------- Downloads ----------
def _state(state: Path) -> dict:
    try:
        return json.loads(Path(state).read_text())
    except (FileNotFoundError, ValueError):
        return {"seen": []}


def new_downloads(downloads: Path = DOWNLOADS, state: Path = STATE) -> list:
    """Gemini clips in Downloads not filed yet, oldest first."""
    seen = set(_state(state).get("seen", []))
    files = [p for p in Path(downloads).glob(CLIP_GLOB) if p.name not in seen]
    return sorted(files, key=lambda p: p.stat().st_mtime)


def mark_seen(files: list, state: Path = STATE) -> None:
    d = _state(state)
    d["seen"] = (d.get("seen", []) + [Path(f).name for f in files])[-500:]
    Path(state).parent.mkdir(parents=True, exist_ok=True)
    Path(state).write_text(json.dumps(d))


# ---------- parts ----------
def have_parts(piece, inbox_dir: Path = INBOX) -> list:
    d = Path(inbox_dir) / piece.id
    return sorted(int(m.group(1)) for f in d.glob("part*.mp4") for m in [re.match(r"part(\d+)\.mp4", f.name)] if m) if d.exists() else []


def file_clips(piece, clips: list, inbox_dir: Path = INBOX) -> int:
    """Moves clips into Inbox/<id>/partNN.mp4 filling the lowest missing part numbers first. Returns how many were filed."""
    d = Path(inbox_dir) / piece.id
    d.mkdir(parents=True, exist_ok=True)
    total = len(piece.topic.get("pack", []))
    have = set(have_parts(piece, inbox_dir))
    n = 0
    for clip in clips:
        slot = next((i for i in range(1, total + 1) if i not in have), None)
        if slot is None:
            break
        shutil.move(str(clip), str(d / f"part{slot:02d}.mp4"))
        have.add(slot); n += 1
    return n


def transcribe(clip: Path) -> str:
    """Gemini transcription of a clip's speech (Hinglish), via a temp WAV."""
    import base64
    from . import gemini, secrets
    wav = Path(clip).with_suffix(".wav")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(clip), "-vn", "-ac", "1", "-ar", "16000", "-sample_fmt", "s16", str(wav)], check=True)
    body = {"contents": [{"parts": [{"text": "Transcribe this Hinglish speech exactly, word for word, in Latin script. Output only the words."},
                                    {"inline_data": {"mime_type": "audio/wav", "data": base64.b64encode(wav.read_bytes()).decode()}}]}],
            "generationConfig": {"temperature": 0}}
    out = gemini.text(gemini.generate("gemini-3.8-flash", body, secrets.get("GEMINI_API_KEY")))
    wav.unlink(missing_ok=True)
    return out.strip()


def _tokens(text: str) -> list:
    return re.findall(r"[\wऀ-ॿ]+", text.lower())


def similarity(a: str, b: str) -> float:
    ta, tb = set(_tokens(a)), set(_tokens(b))
    return len(ta & tb) / len(ta | tb) if ta and tb else 0.0


def _repeated_run(text: str, n: int = 3) -> str:
    toks = _tokens(text)
    seen = {}
    for i in range(len(toks) - n + 1):
        gram = " ".join(toks[i:i + n])
        if gram in seen and i - seen[gram] >= n:
            return gram
        seen.setdefault(gram, i)
    return ""


def check_clip(clip, narration: str, transcribe=transcribe, similarity=similarity) -> list:
    """Empty list = the clip says its narration. Otherwise reasons: 'missing words' (low overlap) or 'repeated phrase'."""
    try:
        heard = transcribe(clip)
    except Exception as e:
        return [f"transcription failed: {type(e).__name__}"]
    reasons = []
    s = similarity(narration, heard)
    if s < SIMILARITY_MIN:
        reasons.append(f"missing words (only {s:.0%} of the narration heard): \"{heard[:120]}\"")
    rep = _repeated_run(heard)
    if rep and not _repeated_run(narration):
        reasons.append(f"repeated phrase: \"{rep}\"")
    return reasons


def contact_sheet(piece, inbox_dir: Path = INBOX) -> Path:
    d = Path(inbox_dir) / piece.id
    frames = []
    for n in have_parts(piece, inbox_dir):
        png = d / f"frame{n:02d}.png"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "1", "-i", str(d / f"part{n:02d}.mp4"), "-frames:v", "1", "-vf", "scale=270:-2", str(png)], check=True)
        frames.append(png)
    out = d / "contact-sheet.jpg"
    inputs = []
    for f in frames:
        inputs += ["-i", str(f)]
    cols = min(len(frames), 4) or 1
    layout = "|".join(f"{(i % cols) * 270}_{(i // cols) * 480}" for i in range(len(frames)))
    if len(frames) == 1:
        subprocess.run(["ffmpeg", "-v", "error", "-y", *inputs, str(out)], check=True)
    else:
        subprocess.run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", f"xstack=inputs={len(frames)}:layout={layout}:fill=black", str(out)], check=True)
    return out


# ---------- the tick ----------
def awaiting(root: Path, status: str) -> list:
    return [p for p in pieces.list_all(root) if p.status == status and p.topic.get("pack")]


def tick(root: Path = ROOT, downloads: Path = DOWNLOADS, inbox_dir: Path = INBOX, state: Path = STATE, transcribe=transcribe,
         similarity=similarity, notify=telegram.send, send_file=telegram.send_file) -> list:
    """Files new clips for the oldest piece awaiting clips, checks each, asks for confirmation when complete. Returns messages sent."""
    sent = []
    clips = new_downloads(downloads, state)
    waiting = sorted(awaiting(root, "awaiting-clips"), key=lambda p: p.publish_day)
    if clips and waiting:
        piece = waiting[0]
        before = set(have_parts(piece, inbox_dir))
        filed = file_clips(piece, clips[: len(piece.topic["pack"]) - len(before)], inbox_dir)
        mark_seen(clips[:filed], state)
        parts = {p["part"]: p for p in piece.topic["pack"]}
        for n in sorted(set(have_parts(piece, inbox_dir)) - before):
            problems = check_clip(Path(inbox_dir) / piece.id / f"part{n:02d}.mp4", parts[n]["narration"], transcribe, similarity)
            if problems:
                (Path(inbox_dir) / piece.id / f"part{n:02d}.mp4").unlink()
                msg = f"{piece.id} part {n}: " + "; ".join(problems) + f"\nPlease regenerate part {n} (redo {piece.id} {n} is implied; the next clip you drop fills it)."
                notify(msg); sent.append(msg)
        have = have_parts(piece, inbox_dir)
        if len(have) == len(parts):
            sheet = contact_sheet(piece, inbox_dir)
            send_file(sheet, f"{piece.id}: all {len(parts)} parts filed in this order. Reply \"ok {piece.id}\" to build, \"swap {piece.id} 2 5\" to reorder, \"redo {piece.id} 3\" to replace a part.")
            sent.append(("file", sheet.name))
            msg = f"{piece.id}: ready. Reply ok {piece.id}"
            notify(msg); sent.append(msg)
            pieces.save(pieces.transition(piece, "awaiting-confirm"), root)
        else:
            pieces.save(piece, root)
    return sent


# ---------- commands ----------
def command(text: str, root: Path = ROOT, inbox_dir: Path = INBOX, build=None, qa=None, upload=None, thumbnail=None, env=None) -> str:
    """ok <id> | swap <id> a b | redo <id> n. Returns the reply for Telegram."""
    words = text.strip().split()
    if len(words) < 2 or words[0].lower() not in ("ok", "swap", "redo"):
        return ""
    verb, pid = words[0].lower(), words[1]
    piece = pieces.load(pid, root)
    if not piece or not piece.topic.get("pack"):
        return f"no pack for {pid}"
    d = Path(inbox_dir) / pid
    if verb == "swap" and len(words) == 4:
        a, b = int(words[2]), int(words[3])
        fa, fb, tmp = d / f"part{a:02d}.mp4", d / f"part{b:02d}.mp4", d / "swap.tmp"
        if not (fa.exists() and fb.exists()):
            return f"parts {a} and {b} are not both filed"
        fa.rename(tmp); fb.rename(fa); tmp.rename(fb)
        return f"swapped parts {a} and {b} of {pid}"
    if verb == "redo" and len(words) == 3:
        n = int(words[2])
        (d / f"part{n:02d}.mp4").unlink(missing_ok=True)
        pieces.save(pieces.transition(piece, "awaiting-clips", f"redo part {n}"), root)
        return f"waiting for a new part {n} of {pid}; drop it in Downloads"
    if verb == "ok":
        if piece.status != "awaiting-confirm":
            return f"{pid} is {piece.status}, not ready to build"
        from . import clipbuild
        build = build or clipbuild.build
        qa_fn = qa or clipbuild.check
        thumbnail = thumbnail or clipbuild.thumbnail
        upload = upload or clipbuild.upload
        parts = sorted(piece.topic["pack"], key=lambda p: p["part"])
        clips = [d / f"part{p['part']:02d}.mp4" for p in parts]
        out_dir = Path(root) / "out" / pid
        out_dir.mkdir(parents=True, exist_ok=True)
        video = build(piece, parts, clips, out_dir)
        problems = qa_fn(video, piece)
        if problems:
            pieces.save(pieces.transition(piece, "qa_failed", "; ".join(problems)), root)
            return f"{pid} failed QA: " + "; ".join(problems)
        thumb = thumbnail(piece, clips[0], out_dir / "thumb.jpg")
        if piece.kind == "short":
            shutil.copy(video, out_dir / "story.mp4")
        piece.ids["yt_id"] = upload(piece, video, thumb)
        pieces.save(pieces.transition(piece, "uploaded"), root)
        from . import gitsync
        import os
        if (env or os.environ).get("SG_PUSH_FROM_MAC") == "1":
            gitsync.safe_commit(root, f"clips: {pid}", env={"SG_COMMIT_EACH": "1"})
        return f"uploaded {pid} as YouTube id {piece.ids['yt_id']}"
    return ""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tick", action="store_true")
    ap.add_argument("--cmd")
    a = ap.parse_args(argv)
    if a.cmd:
        print(command(a.cmd)); return 0
    if a.tick:
        telegram.poll_commands(status_fn=lambda: digest.status_line(ROOT), handler=lambda text: command(text))
        for m in tick():
            print(m if isinstance(m, str) else m[1])
        return 0
    ap.print_help(); return 1


if __name__ == "__main__":
    sys.exit(main())
