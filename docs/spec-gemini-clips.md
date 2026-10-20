# Addendum: presenter clips from the Gemini app ("paste and drop"), 20 Oct 2026

Approved in chat by the founder on 20 Oct 2026 ("build it"). Extends docs/spec.md; nothing in the automatic path is removed, it becomes the fallback.

## Why
The founder's Gemini app renders his own avatar (face and voice) as the presenter "SG", speaking Hinglish, with gestures and scenes. The API cannot do this (no real-person likeness, no own voice). The first test clip (20 Oct, Jio IPO Part 1) confirmed the look and the Hinglish; it also showed two quirks: narration over ~18 words gets cut, and the model sometimes repeats a phrase to fill 10 seconds.

## Flow
1. **Pack.** When a piece's script passes the gates, the pipeline writes a *prompt pack*: one part per scene, in the founder's locked format (locked character line "SG [locked]", mood, 9:16 for Shorts / 16:9 for longs, "@SGLearning watermark top right, white, bold, 80% opacity", bottom 25 % clear for captions, no logos, no real-company marks in visuals, narration ≤ 18 words). The pack goes to Telegram and to `Desktop/SG-Content-Project/Packs/<piece id>.txt`. Piece status: `awaiting-clips`. Every scene is a Gemini part, so the whole video has one voice; number cards, source strips and label chips become overlays on the clips.
2. **Drop.** The founder generates the parts in order in the Gemini app; files land in `~/Downloads` as `gemini_generated_video_*.mp4`.
3. **File.** A launchd job on the Mac runs `python -m engine.inbox --tick` every 2 minutes: new clips in Downloads (newer than the pack) move, in arrival order, into `Desktop/SG-Content-Project/Inbox/<piece id>/partNN.mp4` for the oldest piece still awaiting clips. Each clip is transcribed (Gemini) and compared with its narration: missing words (similarity < 0.6) or a repeated 3-word run is flagged on Telegram with the part number ("redo 3"). When all parts are present and clean, a contact sheet (first frame of each part) goes to Telegram; status `awaiting-confirm`.
4. **Confirm.** Telegram commands: `ok <id>` builds; `swap <id> 2 5` reorders; `redo <id> 3` deletes a part and waits for a new clip. (One confirmation per video is the founder's choice for this path; the automatic path stays approval-free.)
5. **Build.** Each clip: scale to 1080×1920 (or 1920×1080), 30 fps, trim leading/trailing silence, loudnorm; overlays by scene (number chip for scenes with card data, source strip for finance facts, label chip for mythology claims); captions from the part narration; synthesised music bed under everything; concat with 0.3 s cross-fades; QA (duration, loudness, decode, black start); thumbnail from the pipeline's template using the first frame of Part 1 as the picture.
6. **Upload and post.** ≤ 60 s → YouTube Short (scheduled as before); longer → normal video with chapters. The Short is written to `out/<id>/` and, when `SG_PUSH_FROM_MAC=1`, committed and pushed by `engine.gitsync` so the cloud publish job (or `engine.publish` on the Mac) can post it to Instagram and Threads. Without the flag the Short waits for a push by the founder.
7. **Fallback.** If a piece is still `awaiting-clips` or `awaiting-confirm` three hours before its slot, the automatic path renders it (stills + cloned voice) so the day is not missed; the pack is cancelled with a Telegram note.

## Not changed
Gates, claims, budgets, buffer, YouTube/Instagram/Threads modules, the cloud workflows.
