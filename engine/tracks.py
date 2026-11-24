"""Real music under the videos, fetched by the engine itself (founder, 24 Nov 2026: "Why can't this music automised. You have everything
just do it"). YouTube's Audio Library has no way in without his login, so the tracks come from incompetech.com, where Kevin MacLeod
publishes his catalogue free under Creative Commons Attribution 4.0 with a plain download link for each piece.

content/music-tracks.json lists the tracks chosen for each channel (by the site's own feel tags). A piece takes one by its id, so the
same video always gets the same track and the days differ. The file is downloaded when the video is built and never kept in this repo
(the licence lets us use a track in a video, not hand the file out). Every video that uses one carries the credit the site asks for:
in the YouTube description, the Instagram caption and, when it fits, the Threads post. A failed download falls back to the plain pad.
"""
import hashlib
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

from .config import CONTENT_DIR

LIST = CONTENT_DIR / "music-tracks.json"
LICENCE = "Licensed under Creative Commons: By Attribution 4.0\nhttp://creativecommons.org/licenses/by/4.0/"
MIN_BYTES = 200_000                    # a real MP3 of a minute and a half is well over this; an error page is not


def on(root: Path | None = None) -> bool:
    """content/sound.json {"music": false} goes back to the plain pad; SG_MUSIC=0 does the same for a run (the tests never download)."""
    import os
    if os.environ.get("SG_MUSIC") == "0":
        return False
    try:
        return bool(json.loads(((Path(root) / "content" if root else CONTENT_DIR) / "sound.json").read_text()).get("music", True))
    except (OSError, ValueError):
        return True


def load(path: Path = LIST) -> dict:
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return {}


SOBER = re.compile(r"\b(tragedy|disaster|crash|accident|gas leak|bhopal|haadsa|hadsa|trasadi|maut|mare gaye|mrityu|died|death|dead|killed|"
                   r"hatya|blast|earthquake|bhukamp|flood|baadh|tsunami|riot|massacre|war|yudh|famine|akaal)\b", re.I)


def sober(piece) -> bool:
    """A video about a disaster, an accident or a death: its music is quiet and plain, never cheerful. Learning with SG only: on
    SG-MYTH-WORLD a war or a death is part of an old epic, and its tracks are already dark."""
    if getattr(piece, "channel", "") != "sglearning":
        return False
    t = getattr(piece, "topic", None) or {}
    s = getattr(piece, "script", None) or {}
    return bool(SOBER.search(" ".join(str(x or "") for x in (t.get("title"), t.get("summary"), s.get("title")))))


def pick(piece, tracks: dict | None = None) -> dict | None:
    """The track for this piece, or None when the channel has none listed."""
    tracks = load() if tracks is None else tracks
    mine = (tracks.get("sober") if sober(piece) else None) or tracks.get(getattr(piece, "channel", "")) or []
    if not mine:
        return None
    n = int(hashlib.sha256(str(piece.id).encode()).hexdigest(), 16)
    return {**mine[n % len(mine)], "source": tracks.get("source", "")}


def url(track: dict) -> str:
    return str(track.get("source") or "") + urllib.parse.quote(str(track["filename"]))


def fetch(track: dict, out: Path, get=None) -> Path | None:
    """Downloads the track to `out`; None when it cannot be had (the caller falls back to the code-made sound)."""
    def _get(u):
        req = urllib.request.Request(u, headers={"User-Agent": "video-engine"})
        with urllib.request.urlopen(req, timeout=90) as r:
            return r.read()
    try:
        data = (get or _get)(url(track))
    except Exception as e:
        print(f"music: '{track.get('title')}' not downloaded ({type(e).__name__}: {str(e)[:100]})", flush=True)
        return None
    if len(data) < MIN_BYTES:
        print(f"music: '{track.get('title')}' came back too small ({len(data)} bytes)", flush=True)
        return None
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_bytes(data)
    return Path(out)


def credit(music: dict | None, short: bool = False) -> str:
    """The credit the licence requires, as the site words it; '' when the piece used no track. `short` is one line for a tight caption."""
    if not music or not music.get("title"):
        return ""
    if short:
        return f"Music: \"{music['title']}\" Kevin MacLeod (incompetech.com), CC BY 4.0"
    return f"Music: \"{music['title']}\"\nKevin MacLeod (incompetech.com)\n{LICENCE}"
