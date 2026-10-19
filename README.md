# sg-content

Automated Hinglish videos for two YouTube channels (Learning with SG: money news explained; SG-MYTH-WORLD: mythology and history with evidence), plus Instagram Reels, Stories and Threads. Fully automatic with checks, no per-post approval. Design: `docs/spec.md`. Plan: `docs/superpowers/plans/`.

## Run locally
```
python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt && python -m playwright install chromium
cp .env.example .env   # fill in the secret names listed in docs/secrets.md
python -m pytest -q -m "not slow"
python -m engine.produce --dry-run --max 1
```
Needs `ffmpeg` and `ffprobe` on PATH.

## Rules that the code enforces
Founder's own cloned voice; original scripts only; every number traced to a source; finance disclaimer on every finance piece; mythology claims labelled scripture / archaeology / disputed / legend; no politics, no communal content, no buy or sell calls; a piece that fails any check is never posted.
