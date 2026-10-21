# sg-content

Automated Hinglish videos for two YouTube channels (Learning with SG: money news explained; SG-MYTH-WORLD: mythology and history with evidence), plus Instagram Reels, Stories, Threads and the founder's LinkedIn profile (optional; `python -m engine.linkedin --auth`). Fully automatic with checks, no per-post approval. Design: `docs/spec.md`. Plan: `docs/superpowers/plans/`. Settled founder decisions: `docs/decisions.md` (read before asking).

## Run locally
```
python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt && python -m playwright install chromium
cp .env.example .env                      # fill in; names and sources in docs/secrets.md
python -m pytest -q -m "not slow"          # fast suite (network-free)
python -m pytest -q                        # everything, needs ffmpeg and Chromium
python -m engine.produce --dry-run --max 1 # make one piece, stop before upload; files in out/<id>/
python -m engine.produce                   # make what the buffer needs and schedule the uploads
python -m engine.publish --channel sglearning
python -m engine.report
```
Needs `ffmpeg` and `ffprobe` on PATH. Captions are rendered by Chromium, so ffmpeg does not need libass.

## One-time setup
1. `python -m engine.voice --enrol <sample.wav> <consent.wav>` creates the replicated voice in this project's Gemini project (needs a **paid Tier 1** project) and writes `content/voice.json`.
2. `python -m engine.art --avatar-library` draws the 30 avatar poses once (about ₹90) into `assets/avatar/`.
3. Message the Telegram bot once, then `python -m engine.telegram --find-chat` prints `TELEGRAM_CHAT_ID`.
4. First live day: run with `UNLISTED_DAY1=1` so uploads are unlisted and nothing goes to Instagram or Threads; watch, then let the cron run public.

## How a piece is made
topic (RSS or the mythology topic bank) → grounded research (Gemini + Google Search, every fact with a URL and date) → script (Claude Opus 5.5, strict schema; Gemini if Claude fails) → gates (banned phrases, labels, numbers traced to a source, length, avatar share, captions) → voice (the founder's replicated voice, one request per line, cached, 80 a day) → pictures (Gemini image, avatar library, Wikimedia Commons with licence check) → cards (Chromium) → ffmpeg assembly with caption cues and a synthesised music bed → QA (duration, loudness, decode, freeze, black start, caption coverage) → YouTube upload, private, scheduled → Shorts committed under `out/` so Instagram and Threads can fetch them at their slot.

A piece that fails a gate is written to `pieces/<id>.json` with its reasons and never posted. A run that hits a budget stops and says so on Telegram; the next run resumes from the saved script and cached voice lines.

## Rules that the code enforces
Founder's own cloned voice; original scripts only; every number traced to a source; finance disclaimer on every finance piece; mythology claims labelled scripture / archaeology / disputed / legend; no politics, no communal content, no buy or sell calls; a piece that fails any check is never posted.

## Telegram commands
`/pause` stops making and posting until `/resume`; `/status` shows the buffer per channel.
