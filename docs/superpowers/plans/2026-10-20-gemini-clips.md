# Gemini Presenter Clips Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Turn each approved script into a Gemini prompt pack, file the founder's downloaded clips, check and confirm them, build the video with overlays, captions and music, and upload it, with the automatic path as fallback.

**Spec:** docs/spec-gemini-clips.md (addendum to docs/spec.md).

**Global constraints:** as the main plan, plus: narration per part ≤ 18 words; Gemini clips are 720×1280 (or 1280×720), 24 fps, ~10 s, AAC stereo; no logos or real-company marks in visual prompts; Mac job must never block on a missing clip.

## Tasks
1. `engine/promptpack.py` — `write(piece, client=None) -> list[dict]` (Claude writes parts from the script: `{part, scene, narration, prompt}`), `render(piece, parts) -> str` (the pack text in the founder's format), `send(piece, text)` (Telegram + Packs file). Tests: narration ≤ 18 words enforced, locked line present once, every part carries the watermark line and the aspect, no logo words.
2. `engine/inbox.py` — `new_downloads(since, state) -> list[Path]`, `file_clips(piece, clips) -> int`, `check_clip(clip, narration, transcribe) -> list[str]` (similarity + repeated 3-gram), `contact_sheet(piece) -> Path`, `tick()`; statuses `awaiting-clips`, `awaiting-confirm`. Tests with fake transcribe and tmp dirs.
3. Telegram commands `ok`, `swap`, `redo` in `engine/telegram.poll_commands` via a command hook. Tests.
4. `engine/clipbuild.py` — `normalise(clip, size) -> Path`, `build(piece, parts, clips) -> Path` (overlays, captions from narration, music, concat), `thumbnail_from(clip)`. Slow tests with synthetic clips.
5. `engine/inbox.py` build+upload on `ok`: Short vs long, `out/<id>/`, `gitsync` when `SG_PUSH_FROM_MAC=1`; fallback deadline in `produce`. Tests.
6. launchd plist `com.sgcontent.inbox.plist` (every 2 min) and `com.sgcontent.packs.plist` (07:00 Lagos: produce `--mode pack`), installed; README section.
