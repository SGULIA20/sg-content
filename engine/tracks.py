"""Real music under the videos, fetched by the engine itself (founder, 24 Nov 2026: "Why can't this music automised. You have everything
just do it"). YouTube's Audio Library has no way in without his login, so the tracks come from incompetech.com, where Kevin MacLeod
publishes his catalogue free under Creative Commons Attribution 4.0 with a plain download link for each piece.

content/music-tracks.json lists the tracks chosen for each channel (by the site's own feel tags). A piece takes one by its id, so the
same video always gets the same track and the days differ. The file is downloaded when the video is built and never kept in this repo
(the licence lets us use a track in a video, not hand the file out). Every video that uses one carries the credit the site asks for:
in the YouTube description, the Instagram caption and, when it fits, the Threads post. A failed download falls back to the sound made
in code (engine/sfx.py).
"""
import hashlib
import json
import urllib.parse
import urllib.request
from pathlib import Path

from .config import CONTENT_DIR

LIST = CONTENT_DIR / "music-tracks.json"
LICENCE = "Licensed under Creative Commons: By Attribution 4.0\nhttp://creativecommons.org/licenses/by/4.0/"
MIN_BYTES = 200_000                    # a real MP3 of a minute and a half is well over this; an error page is not


def load(path: Path = LIST) -> dict:
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return {}


def pick(piece, tracks: dict | None = None) -> dict | None:
    """The track for this piece, or None when the channel has none listed."""
    tracks = load() if tracks is None else tracks
    mine = tracks.get(getattr(piece, "channel", "")) or []
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
