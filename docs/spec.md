# SG Content pipeline: design spec (19 Oct 2026)

Status: design approved in chat by the founder on 19 Oct 2026 (with corrections below). This file is the written spec for review before the implementation plan is written. Nothing is built yet.

## 1. Purpose and success

Two YouTube channels, one Instagram account and one Threads account get original Hinglish content every day with no per-post approval, in the founder's own cloned voice, with his photoreal likeness only where it helps. Everything runs in the cloud; the Mac's lid does not matter.

| | Learning with SG (YouTube `sglearning`) | SG-MYTH-WORLD (YouTube `arthvan`) |
|---|---|---|
| Niche | "Paise ki khabar, seedhi baat": one money-news item a day, explained | "Sabut ke saath": Indian mythology and history with evidence |
| Short (9:16, 45-60 s) | daily | Mon, Wed, Fri (cut from the week's long) |
| Long (16:9) | Sunday 19:00 IST, 12-18 min, "mistakes / traps / how it really works" built from the week's news | Saturday 19:00 IST, 15-25 min, one place / figure / event as a mystery with evidence |
| Day-90 targets (Plan-v4 §E) | +500 subs, best Short 100K, long avg 3,000 views at 40 % watched | +1,000 subs, best Short 300K, long avg 10,000 views at 40 % watched |

Every Short also goes to Instagram (Reel + Story) and Threads on `sanjeev_gulia`. An Instagram carousel post is added only when the piece has at least three number cards worth reading as slides (the script marks them); never daily by rule.

Standing rules (CLAUDE.md): founder's cloned voice; fully automatic with checks; real audience only; never copy other channels' videos, scripts or thumbnails; no secrets in output; every fact labelled and sourced. The arthvan-media job is never touched from this repo.

## 2. Corrections taken in on 19 Oct 2026 (chat)
- Instagram Reels, Stories and posts, and Threads, are in scope (earlier plan said YouTube only).
- No face on camera. A photoreal likeness of the founder (from the 22 photos in `Reference/`) appears only where it earns its place: hook (first 3 s), the "what it means for you" moment, end card; longs add it at chapter turns. No lip-sync, no talking head. The app Reels' cartoon character is not used.
- Scripts: Claude writes (script, hook, titles, captions). Gemini researches with Google Search grounding, extracts numbers with sources, draws pictures, speaks. Claude failure → Gemini writes, piece marked `writer: gemini` in the log.
- Voice: `voice_9c6x5lerrbm4` (Hinglish-trained, consent + 15 s Hinglish; founder approved the test audio). Fallback `voice_7w9h8qkiqz03`. Both live in the current Gemini project; they are recreated in this project's own Gemini project from the same clips (`Voice/`).
- Runs on GitHub Actions like the app job. Own repo, own `.env`, own Telegram bot.
- Carousel only when relevant.

## 3. Architecture

```
GitHub repo SGULIA20/sg-content (PUBLIC, like arthvan-media, because Instagram and Threads fetch video from raw.githubusercontent.com)
├── engine/            Python 3.12, stdlib + numpy + playwright + pyyaml + pytest (same footprint as arthvan-media)
│   ├── config.py      channels, slots, budgets, paths
│   ├── topics.py      finance: RSS + press pages → scored candidates; mythology: topic bank rotation
│   ├── research.py    Gemini (grounded) → fact sheet JSON with source URL, date, quote, label
│   ├── writer.py      Claude → piece JSON (scenes, voice lines, cards, captions); Gemini fallback
│   ├── lint.py        every gate in §6; pure functions, fully unit-tested
│   ├── claims.py      standing facts library (content/claims.yaml) and the "every number has a source" check
│   ├── voice.py       Gemini TTS with the replicated voice; per-line cache; daily request budget
│   ├── art.py         Gemini image: scene paintings, avatar stills from Reference/ photos, cached by prompt hash
│   ├── cards.py       Playwright renders HTML templates → PNG (hook card, number card, source strip, end card, thumbnail)
│   ├── assemble.py    ffmpeg: Ken Burns on stills, ASS captions (Noto Sans Devanagari), music bed, loudness, 9:16 and 16:9
│   ├── qa.py          duration, loudness, decode errors, black/frozen frames, caption coverage
│   ├── youtube.py     resumable upload, privacy private + publishAt, thumbnail set, description with chapters
│   ├── instagram.py   Reel, Story, optional carousel (adapted from arthvan-media, same Graph API calls)
│   ├── threads.py     video post
│   ├── telegram.py    digest, alerts, /pause /resume /status
│   ├── buffer.py      what exists, what is due, what to make next (7 days of Shorts ahead; longs 3 days ahead)
│   ├── produce.py     CLI: make N pieces (default: whatever the buffer needs, max 3 per run)
│   └── publish.py     CLI: post what is due in this slot
├── content/
│   ├── claims.yaml            standing facts with sources (tax slabs, GST, SEBI/RBI rules, dates)
│   ├── myth-topics.yaml       ~40 topics, each with allowed source list and the four-label guidance
│   ├── banned.yaml            politics names, communal terms, buy/sell/return-promise phrases
│   ├── hashtags.yaml          per channel, per platform
│   └── prompts/               writer, research, art style, avatar style (text files, versioned)
├── templates/                 HTML for cards and thumbnails (Playwright)
├── assets/                    fonts (Noto Sans Devanagari, Inter), music beds (licensed, 3 tracks), avatar library (generated once)
├── pieces/YYYY-MM-DD-<channel>-<kind>.json   the piece record: script, claims, timings, status, ids (committed)
├── out/<piece id>/            Short mp4 + story mp4 + carousel jpgs + thumbnail (committed for 14 days, then untracked; longs are never committed)
├── logs/                      run log jsonl, spend meters (committed)
├── tests/
└── .github/workflows/         produce.yml, publish.yml, weekly-report.yml, refresh-tokens.yml
```

Local: `~/sg-content` with `.env` (gitignored). Cloud: GitHub Actions secrets with the same names.

### Data flow of one piece
1. `topics` picks: finance = highest-scored RSS item of the last 24 h (ET Markets, Mint, Business Standard, RBI press, SEBI press, BSE announcements) not used in the last 30 days; score = has a number + concerns households (EMI, petrol, tax, salary, SIP, prices) + source rank. Mythology = next topic in `myth-topics.yaml` by rotation; the three Shorts are re-rendered in 9:16 from three evidence scenes of that week's long (same voice lines and pictures, their own hook card and captions).
2. `research` (Gemini, Google Search grounding, temperature 0): fact sheet `{facts:[{text, number, unit, source_url, source_name, source_date, quote, label}], summary}`. Finance labels: `reported` / `official` / `analyst-view`. Mythology labels: `scripture` / `archaeology` / `disputed` / `legend`. A fact without a URL is dropped.
3. `writer` (Claude, `claude-opus-5-5` via the official `anthropic` SDK with structured output and the server-side refusal fallback): prompt = channel formula (Plan-v4 §C) + fact sheet + claims library + banned list + output schema. Output piece JSON: `hook`, `scenes[] {vo, visual {type: avatar|art|card|photo, prompt|card}, facts_used[]}`, `end_question`, `cards[] {big_number, line, source}`, `captions {youtube {title, description, tags, chapters}, instagram {caption, hashtags}, threads {text}}`, `carousel: bool`.
4. `lint` (§6). Fail → the piece is written to `pieces/` with `status: rejected` and the reasons; the run tries the next topic (max 3 tries per slot).
5. `voice`: one TTS request per scene line (so scene timing is exact and retries are small), cached by sha1(voice, text). Budget: 80 requests a day on this project's key; when reached, production stops for the day and Telegram says so.
6. `art`: scene paintings (prompt + fixed style suffix per channel, 1024², ₹3 each, cached). Avatar: a library of ~30 stills generated once from `Reference/` photos (front, three-quarter, expressions: explaining, surprised, thinking, pointing, end-card smile) and reused; a per-piece avatar still is generated only when the scene needs a prop. Mythology real-site photos: only Wikimedia Commons (licence checked via API: CC0/CC-BY/CC-BY-SA, credit burned into the frame) or government/ASI releases; otherwise a painting.
7. `cards`: PNG per card from HTML templates (hook, number, source strip, label chips, end card, thumbnail 1280×720 with 2-4 huge words and one number).
8. `assemble`: ffmpeg concat of per-scene clips (zoompan on stills, 30 fps, 1080×1920 or 1920×1080), ASS captions timed per scene and split per phrase (proportional to syllables), source strip at the bottom of finance scenes, label chip at the top-right of mythology claims, music bed at −22 LUFS under voice at −16 LUFS, "Not investment advice" card 2 s before the end card on finance. Story cut = same video; Short = same as Reel. Long: chapters from scene groups.
9. `qa`: duration in range (Short 40-59 s; long within ±20 % of target), integrated loudness −16 ± 1.5 LUFS, 0 decode errors, no frozen >3 s, caption coverage ≥ 95 % of voiced time, first frame is not black.
10. `youtube`: upload private with `publishAt` at the slot (Shorts 20:00 IST daily; longs as in §1), thumbnail set (if the channel refuses custom thumbnails, log and continue), description = hook + so-what + sources (URL + date) + "not investment advice" (finance) + hashtags; tags ≤ 15; `selfDeclaredMadeForKids: false`; chapters for longs; `containsSyntheticMedia` disclosure flag set to true (the voice is synthetic).
11. Short only: `out/<id>/` committed by the Actions run (reel.mp4, story.mp4, cards/*.jpg, thumb.jpg). `publish` later posts the Reel + Story (+ carousel if `carousel: true`) and the Threads video from the raw.githubusercontent.com URL of that commit.
12. Telegram digest after every run: made / rejected (with reason) / posted / buffer days / spend / quota.

### Schedules (all cron in UTC; IST = UTC+5:30; Lagos = UTC+1)
| Workflow | When | Does |
|---|---|---|
| produce.yml | 02:00 UTC daily (+ 03:00 safety) | fills the buffer: Shorts to 7 days ahead, long ≥ 3 days ahead; max 3 pieces per run; 120-min timeout; commits `pieces/`, `out/`, `logs/` |
| publish.yml | 07:30 UTC (13:00 IST): finance Reel + Story + Threads; 16:00 UTC (21:30 IST): mythology Reel + Story + Threads on Mon/Wed/Fri | Instagram and Threads cannot be scheduled by API, so this run posts at the slot. YouTube needs nothing here (scheduled at upload) |
| weekly-report.yml | Monday 05:00 UTC | YouTube Analytics + Instagram insights for the last 7 days → Telegram, and `logs/weekly.json` |
| refresh-tokens.yml | 1st of the month | Instagram and Threads long-lived token refresh (60-day tokens) |

The app job posts to the same Instagram at about 20:07 IST; this project never posts within 60 minutes of that slot. Instagram API content-publishing limit is 100 posts per 24 h; this project uses ≤ 4.

## 4. Platform packaging rules (lint-enforced)
- YouTube title ≤ 60 chars, a question or contradiction, Hindi words first, one number where possible; Shorts title ends with `#Shorts`; mythology Shorts may carry one of 😱 🤯, never both.
- Description: hook line, two-sentence so-what, "Sources:" list (name, date, URL), finance disclaimer, 3-5 hashtags.
- Instagram caption ≤ 2,200 chars: hook line, 2-3 lines, question, then 5-8 hashtags from `hashtags.yaml` (never more than 10). Story: no caption. Carousel: cards as 1080×1350 slides, first slide = hook card, last slide = end question + handle.
- Threads ≤ 500 chars: hook + question + 2 hashtags.
- Every finance piece: "Yeh investment advice nahi hai" spoken once and shown once.
- Every mythology claim shown on screen carries its label chip.

## 5. Avatar policy
- Source: `Reference/founder-01..22.jpg` (studio photos, 1024²). The image model is given 3 references per call (front, three-quarter, the needed expression) and a fixed style line ("photoreal, same man, studio light, blue striped shirt unless the scene says otherwise").
- Where: hook (0-3 s), the so-what moment, end card; longs also at chapter turns. Never more than 25 % of a piece's screen time. A lint counts avatar scenes and fails above the cap.
- Never: a likeness saying something the voice does not say; any pose implying endorsement of a product; the likeness on mythology scenes depicting deities (the avatar appears only on presenter cards there).
- YouTube's synthetic media disclosure is set because voice and likeness are generated.

## 6. Gates (a piece that fails any gate is not posted)
1. Numbers: every digit group and Hindi number word in the script maps to a fact in the fact sheet or to `claims.yaml`. Unmatched → reject.
2. Sources: every fact used has URL + date; finance dates within 7 days for news pieces.
3. Banned phrases (`banned.yaml`): party or politician names, communal terms, "kharid lo / bech do / target / guaranteed / pakka return / 100 % safe", stock tips phrased as advice.
4. Mythology labels: every claim sentence tagged; no "science proves god", no debunking of faith, no comparisons between religions.
5. Originality: script similarity to any script in `pieces/` < 0.6 (token Jaccard); titles unique for 365 days.
6. Length: Short 110-170 words of voice; long by target minutes × 140 words ± 20 %.
7. Avatar share ≤ 25 %.
8. Captions: hashtag counts, char limits, disclaimer present, no secrets or emails or phone numbers.
9. QA on the rendered file (§3 step 9).
10. Budget: voice requests ≤ 80 per day, images ≤ ₹150 per day, Claude ≤ $1 per day; past a cap the run stops and reports, nothing is posted half-made.

## 7. Error handling
- Every external call: 3 tries with backoff; 429/503 from Gemini wait 60 s then retry once; a failed step leaves the piece `status: failed-<step>` with the error and the run continues with the next piece.
- Produce runs are idempotent: a piece id is date + channel + kind; an existing `done` piece is never remade. A crashed run resumes from the cached voice lines and pictures.
- Publish is idempotent per platform: `pieces/<id>.json` records `yt_id`, `ig_reel_id`, `ig_story_id`, `ig_post_id`, `threads_id`; a platform with an id is skipped.
- Instagram "media not ready" is polled up to 6 minutes as in arthvan-media; a partial publish (Reel done, Story failed) is recorded and retried at the next slot, never duplicated.
- Buffer below 2 days or two consecutive failed runs → Telegram alert (also on the founder's phone via the bot's silent-off message).
- `/pause` in Telegram writes `logs/pause.json`; publish and produce exit early while it exists; `/resume` removes it.
- Token expiry (Instagram, Threads, YouTube refresh token revoked) → alert with the exact fix step.

## 8. Testing and rollout
- Unit tests (pytest, run in every workflow before the job): lint gates with Hindi and Hinglish fixtures, number matching, claims lookup, caption builders, schedule maths (IST/UTC), buffer decisions, budget meters, idempotent publish state, metadata builders, QA thresholds on tiny synthetic clips.
- Integration (local, `python -m engine.produce --dry-run`): one finance Short and one 3-minute mythology long rendered end to end with real APIs; the founder watches both before anything is uploaded.
- Day 1 live: uploads as `unlisted` (YouTube) and Instagram/Threads skipped; founder watches; Day 2 onward public and all platforms.
- Day 30 check (weekly report): if Shorts average < 200 views, the hook formula changes before volume rises (Plan-v4 §E).

## 9. Budgets and quotas (per month, both channels)
| Item | Volume | Cost |
|---|---|---|
| Voice (Gemini 3.8 Flash TTS, this project's key) | ~180 min audio, ~1,500 requests | < ₹300 |
| Images (gemini-3.1-flash-lite-image) | ~300 paintings + avatar library once | ~₹1,000 |
| Claude (Opus 5.5) scripts, captions | ~45 pieces, ~10K tokens each | ~$5-8 (₹450-700) |
| Gemini research (3.8 Flash, grounded) | ~45 fact sheets | < ₹100 |
| GitHub Actions (public repo) | ~600 min | free |
| YouTube Data API | ~1,700 units/day of 10,000 | free |
Total about ₹2,000-2,500 a month, inside the Plan-v4 estimate. Requests per day on the TTS model are capped (100 on Tier 1); the design uses its own key and project, stays under 80, and the founder requests the Tier 2 upgrade in AI Studio when the project qualifies.

## 10. Out of scope (for now)
- YouTube thumbnail A/B test (not available in the Data API); the pipeline uploads one thumbnail and stores the second for manual use.
- Comment replies (no automated replies; the weekly report lists top comments for the founder).
- Languages other than Hindi/Hinglish; multi-language audio tracks.
- Changing the app Shorts routing in arthvan-media (separate repo, separate yes).
- Facebook, LinkedIn, WhatsApp.

## 11. Founder actions before build
1. Anthropic API key with prepaid credits (console.anthropic.com → Billing → add $20; → API keys → create "sg-content"). Save as `~/Desktop/SG-Content-Project/keys/anthropic.key` (one line).
2. Gemini API key from a new project (aistudio.google.com → Get API key → Create API key in **new** project "sg-content"; link the billing account so the project is Tier 1 with a spend cap of about $10/month). Save as `keys/gemini.key`.
3. Telegram: create a new bot with @BotFather, save the token as `keys/telegram.key`, and send the bot one message so it can find the chat id.
4. Create the empty public GitHub repo `SGULIA20/sg-content` (no README) and tell me when it exists; pushes stay yours.
The `keys/` folder is moved into the repo's `.env` and the Actions secrets by me and then deleted; keys are never committed.
