# SG Content Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A cloud-run pipeline in a new repo `~/sg-content` that researches, writes, voices, draws, assembles, checks and publishes original Hinglish Shorts and long videos for two YouTube channels, Instagram and Threads, with no per-post approval.

**Architecture:** One Python package `engine/` of small modules with one responsibility each, glued by two CLIs (`produce`, `publish`) that GitHub Actions runs on cron. Every external service is behind a module with an injectable transport so unit tests never touch the network. State lives in committed JSON (`pieces/`, `logs/`), finished Shorts in `out/` for 14 days; longs go straight to YouTube as scheduled uploads.

**Tech Stack:** Python 3.12, stdlib `urllib`/`json`/`xml.etree`, `numpy`, `playwright` (Chromium) for HTML→PNG cards, `ffmpeg`/`ffprobe` with libass, `anthropic` SDK (Claude Opus 5.5), Gemini REST (3.8 Flash grounded text, 3.8 Flash TTS with the replicated voice, 3.1 Flash-Lite image), YouTube Data API v3, Instagram Graph API, Threads API, Telegram Bot API, `pytest`, GitHub Actions.

**Spec:** `/Users/sanjeevgulia/Desktop/SG-Content-Project/specs/2026-10-19-sg-content-pipeline-design.md` (copied into the repo as `docs/spec.md` in Task 1).

**Reference code (read-only, copy patterns, never import):** `/Users/sanjeevgulia/arthvan-media/engine/{tts,gemini,illustrate,youtube,instagram,threads,telegram,notify,qa}.py`. Proven API request shapes for the new Gemini endpoints are in `/Users/sanjeevgulia/Desktop/SG-Content-Project/Voice/voice-ids.md` and the scratch scripts described there (voices create = `POST /v1beta/voices` with `store`, `voice.model`, `voice.type="replicated"`, `voice.replicated.{source_audio,consent_audio}` as `{mime_type, data}`; synth = `POST /v1beta/interactions` with `model`, `input[0].content[0].{type:"text",text,annotations:[{type:"speech_metadata",style}]}`, `response_format:{type:"audio"}`, `generation_config.speech_config:[{voice}]`; audio base64 in `steps[].content[].data` where `type=="audio"`, 24 kHz mono 16-bit WAV).

## Global Constraints

- Python 3.12; dependencies limited to `numpy>=2.0`, `playwright>=1.45`, `pytest>=8.0`, `pyyaml>=6.0`, `anthropic>=1.0` (requirements.txt). No other packages.
- Every HTTPS call uses `ssl.create_default_context(cafile="/etc/ssl/cert.pem")` when that file exists (macOS python.org builds fail otherwise), as in arthvan-media.
- Secrets come from `os.environ`, then `~/sg-content/.env`; never from the arthvan-social `.env`; never logged, never written to `pieces/` or `logs/`. Every log line passes through `scrub()` which blanks any value of a known secret.
- Secret names: `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `YT_CLIENT_ID`, `YT_CLIENT_SECRET`, `YT_SGLEARNING_REFRESH_TOKEN`, `YT_ARTHVAN_REFRESH_TOKEN`, `IG_ACCESS_TOKEN`, `IG_USER_ID`, `THREADS_ACCESS_TOKEN`, `THREADS_USER_ID`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `GITHUB_REPOSITORY` (set by Actions, default `SGULIA20/sg-content`).
- Channel keys are exactly `sglearning` (Learning with SG) and `arthvan` (SG-MYTH-WORLD). Kinds are `short` and `long`. Piece id = `YYYY-MM-DD-<channel>-<kind>` (publish date, IST).
- Voice ids: default `voice_9c6x5lerrbm4`, fallback `voice_7w9h8qkiqz03` until Task 9 enrols new ids in this project's Gemini project, after which `content/voice.json` holds them.
- Budgets (spec §6.10): voice ≤ 80 requests/day, images ≤ ₹150/day, Claude ≤ $1/day; past a cap the run stops and reports.
- Slots (IST): Shorts publish 20:00 daily (`sglearning`) and 20:00 Mon/Wed/Fri (`arthvan`); longs Sunday 19:00 (`sglearning`), Saturday 19:00 (`arthvan`); Instagram/Threads 13:00 (`sglearning`), 21:30 Mon/Wed/Fri (`arthvan`). Never within 60 minutes of 20:07 IST on Instagram.
- Rendering: Shorts 1080×1920, longs 1920×1080, 30 fps, H.264 yuv420p, AAC 48 kHz, voice −16 LUFS, music bed −22 LUFS, integrated loudness −16 ± 1.5 LUFS.
- Copy fixed by the spec: finance disclaimer spoken and shown as `Yeh investment advice nahi hai`; YouTube Shorts title suffix ` #Shorts`; description source header `Sources:`.
- Fonts: Noto Sans Devanagari (captions, cards), Inter (numbers). Licensed music: three beds in `assets/music/`, each with its licence file.
- Commit after every task; the founder pushes. No workflow is enabled on GitHub until Task 21's dry run passed.

## Review Focus

1. A Hinglish script whose numbers are written as words (`assi pratishat`, `do hazaar paanch sau`, `₹1.5 lakh crore`) must match the fact sheet's digits; test in Task 5 (`test_hindi_number_words_match_digits`).
2. A news item with a number but no URL in the research result must not reach the writer; test in Task 7 (`test_fact_without_url_is_dropped`).
3. A publish run that crashes after the Reel container succeeds and before the Story is posted must not post the Reel twice; test in Task 15 (`test_partial_publish_resumes_without_duplicate`).
4. The TTS daily cap reached mid-piece must leave the piece `failed-voice` with cached lines kept, and the next run must finish it without re-paying for those lines; test in Task 9 (`test_budget_hit_mid_piece_keeps_cache`).
5. IST slot maths across the UTC date boundary (a 20:00 IST Short is 14:30 UTC the same day; a 01:00 IST item is the previous UTC day); test in Task 2 (`test_slot_utc_crosses_date_boundary`).

---

### Task 1: Repository bootstrap and config

**Files:**
- Create: `~/sg-content/{.gitignore,requirements.txt,pyproject.toml,README.md,docs/spec.md,engine/__init__.py,engine/config.py,engine/secrets.py,tests/__init__.py,tests/conftest.py}`
- Test: `tests/test_config.py`, `tests/test_secrets.py`

**Interfaces:**
- Produces: `config.ROOT: Path`; `config.CHANNELS: dict[str, Channel]` with `Channel(key, youtube_env_token, display_name, niche, short_days: set[int], long_day: int, short_publish_ist: str, long_publish_ist: str, ig_slot_ist: str, hashtags_key)`; `config.BUDGETS = {"voice_requests_per_day": 80, "image_inr_per_day": 150, "claude_usd_per_day": 1.0}`; `config.VIDEO = {"short": (1080, 1920), "long": (1920, 1080), "fps": 30}`; `secrets.get(name: str, env: Mapping | None = None) -> str` (raises `MissingSecret`); `secrets.scrub(text: str) -> str`; `secrets.ssl_context() -> ssl.SSLContext`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_config.py
def test_channels_have_two_keys():
    assert set(config.CHANNELS) == {"sglearning", "arthvan"}
def test_arthvan_short_days_are_mon_wed_fri():
    assert config.CHANNELS["arthvan"].short_days == {0, 2, 4}
# tests/test_secrets.py
def test_env_wins_over_dotenv(tmp_path):
    (tmp_path / ".env").write_text("GEMINI_API_KEY=fromfile\n")
    assert secrets.get("GEMINI_API_KEY", env={"GEMINI_API_KEY": "fromenv"}, dotenv=tmp_path / ".env") == "fromenv"
def test_missing_secret_raises(tmp_path):
    with pytest.raises(secrets.MissingSecret): secrets.get("NOPE", env={}, dotenv=tmp_path / ".env")
def test_scrub_blanks_known_values():
    secrets.remember("abc123"); assert "abc123" not in secrets.scrub("token abc123 here")
```

- [ ] **Step 2: Run tests, expect ImportError**  Run: `cd ~/sg-content && python3 -m pytest -q`
- [ ] **Step 3: Create the repo** (`git init`, default branch `main`), `.gitignore` (`.env`, `out/`, `cache/`, `__pycache__`, `.playwright`), `requirements.txt` per Global Constraints, `pyproject.toml` with `[tool.pytest.ini_options] markers = ["slow"]`, `docs/spec.md` copied from the spec path, `engine/config.py` and `engine/secrets.py` with the signatures above (`secrets.get` reads `os.environ` then `ROOT/.env` key=value lines; `remember()` registers values for `scrub`).
- [ ] **Step 4: Run tests, expect 5 passed**
- [ ] **Step 5: Commit** `git add -A && git commit -m "chore: bootstrap sg-content engine, config and secrets"`

### Task 2: Slots and buffer calendar

**Files:**
- Create: `engine/slots.py`
- Test: `tests/test_slots.py`

**Interfaces:**
- Produces: `slots.ist(dt_utc: datetime) -> datetime`; `slots.utc_for(day: date, hhmm_ist: str) -> datetime` (aware UTC); `slots.publish_dates(channel: str, kind: str, start: date, days: int) -> list[date]` (IST dates on which that channel/kind publishes); `slots.piece_id(day: date, channel: str, kind: str) -> str`; `slots.ig_slot_ok(dt_ist: datetime) -> bool` (false within 60 min of 20:07).

- [ ] **Step 1: Write the failing tests**

```python
def test_slot_utc_crosses_date_boundary():
    assert slots.utc_for(date(2026,10,20), "20:00") == datetime(2026,10,20,14,30,tzinfo=timezone.utc)
    assert slots.utc_for(date(2026,10,20), "01:00") == datetime(2026,10,19,19,30,tzinfo=timezone.utc)
def test_arthvan_shorts_only_mon_wed_fri():
    days = slots.publish_dates("arthvan", "short", date(2026,10,19), 7)   # Mon 19 Oct
    assert [d.isoformat() for d in days] == ["2026-10-19","2026-10-21","2026-10-23"]
def test_sglearning_long_is_sunday():
    assert slots.publish_dates("sglearning", "long", date(2026,10,19), 7) == [date(2026,10,25)]
def test_ig_slot_blocks_app_job_window():
    assert not slots.ig_slot_ok(datetime(2026,10,20,20,30))
    assert slots.ig_slot_ok(datetime(2026,10,20,13,0))
```

- [ ] **Step 2: Run, expect failures**  - [ ] **Step 3: Implement `engine/slots.py`** (IST = UTC+5:30, no DST; weekday 0 = Monday)  - [ ] **Step 4: Run, expect pass**  - [ ] **Step 5: Commit** `feat: IST slots and publish calendar`

### Task 3: Piece records

**Files:**
- Create: `engine/pieces.py`
- Test: `tests/test_pieces.py`

**Interfaces:**
- Produces: `Piece` dataclass: `id, channel, kind, publish_day (date), status, topic (dict), facts (list), script (dict|None), timings (list), ids (dict: yt_id, ig_reel_id, ig_story_id, ig_post_id, threads_id, out_sha), writer (str), reasons (list[str]), updated (str)`; statuses: `planned, researched, written, rejected, voiced, drawn, assembled, qa_failed, uploaded, posted, failed-<step>`; `pieces.load(id, root=ROOT) -> Piece | None`; `pieces.save(p, root=ROOT) -> Path` (`pieces/<id>.json`, sorted keys, no secrets); `pieces.list_all(root) -> list[Piece]`; `pieces.transition(p, status, reason: str | None = None) -> Piece`.

- [ ] **Step 1: Tests**: `test_save_then_load_roundtrip`, `test_transition_appends_reason_on_reject`, `test_save_refuses_secret_values` (a value registered with `secrets.remember` inside the record raises `ValueError`).
- [ ] **Step 2: Run, fail**  - [ ] **Step 3: Implement**  - [ ] **Step 4: Run, pass**  - [ ] **Step 5: Commit** `feat: piece records`

### Task 4: Lint gates and content lists

**Files:**
- Create: `engine/lint.py`, `content/banned.yaml`, `content/hashtags.yaml`
- Test: `tests/test_lint.py`

**Interfaces:**
- Consumes: `Piece` (Task 3).
- Produces: `lint.check_script(piece: Piece, banned: dict, prior_scripts: list[str]) -> list[str]` (empty list = pass) covering spec §6 gates 3, 4, 5, 6, 7; `lint.check_captions(piece, hashtags: dict) -> list[str]` (gate 8); `lint.similarity(a: str, b: str) -> float` (token Jaccard); `lint.load_lists(root) -> tuple[dict, dict]`.
- `content/banned.yaml` sections: `politics` (party names, PM/CM names, "sarkar giri", "vote"), `communal` (religion-vs-religion terms), `advice` (`kharid lo`, `bech do`, `target price`, `guaranteed`, `pakka return`, `100% safe`, `multibagger`), `myth_forbidden` (`science proves god`, `andhvishwas`, comparisons of faiths). `content/hashtags.yaml`: per channel, `instagram` (12 tags, pipeline picks 5-8), `youtube` (5), `threads` (2).

- [ ] **Step 1: Tests** (Hindi fixtures in the test file):
```python
def test_blocks_buy_call(): assert any("advice" in r for r in lint.check_script(piece_with("Reliance kharid lo abhi"), BANNED, []))
def test_blocks_politician_name(): ...
def test_myth_claim_without_label_fails(): piece.script["scenes"][0]["label"] = None → reason "label"
def test_near_duplicate_script_fails(): similarity ≥ 0.6 with a prior → reason "originality"
def test_short_word_count_bounds(): 100 words → fail; 140 → pass; 180 → fail
def test_avatar_share_cap(): 4 of 10 scenes avatar → fail (>25 %)
def test_finance_caption_needs_disclaimer_and_5_to_8_tags(): ...
def test_caption_rejects_phone_or_email(): "+91 98765 43210" → reason "pii"
```
- [ ] **Step 2: Run, fail**  - [ ] **Step 3: Implement**  - [ ] **Step 4: Run, pass**  - [ ] **Step 5: Commit** `feat: lint gates and banned/hashtag lists`

### Task 5: Claims library and number matching

**Files:**
- Create: `engine/claims.py`, `content/claims.yaml`
- Test: `tests/test_claims.py`

**Interfaces:**
- Produces: `claims.numbers_in(text: str) -> list[float]` (digits with Indian separators `1,50,000`, decimals, `%`, and Hindi words: ek, do, teen, chaar, paanch, chhe, saat, aath, nau, das, gyarah..bees, pachaas, sau, hazaar, lakh, crore, pratishat, with Devanagari equivalents); `claims.match(script_text: str, facts: list[dict], library: list[dict], tolerance: float = 0.005) -> list[float]` (returns unmatched numbers; empty = pass); `claims.load_library(root) -> list[dict]`. `content/claims.yaml` entries: `{id, text, number, unit, source_url, source_date, valid_until}`; seed with 15 standing facts (income tax slabs FY26-27, GST slabs, SEBI SIP minimum, RBI repo rate with date, PF rate, 80C limit, LTCG rates, India crude import share ≈ 85-88 %, etc.), each with a URL the implementer verifies on the day.

- [ ] **Step 1: Tests**
```python
def test_hindi_number_words_match_digits():
    assert claims.numbers_in("India apna assi pratishat tel bahar se khareedta hai") == [80.0]
    assert claims.numbers_in("do hazaar paanch sau rupaye") == [2500.0]
    assert claims.numbers_in("₹1.5 lakh crore ka profit") == [1.5e12]
def test_unmatched_number_is_reported(): match("profit 12 pratishat", facts=[{"number": 11.0}], library=[]) == [12.0]
def test_library_fact_counts_as_source(): ...
```
- [ ] **Step 2: Run, fail**  - [ ] **Step 3: Implement** (word→value table, compound scaling: `do hazaar paanch sau` = 2×1000 + 5×100)  - [ ] **Step 4: Run, pass**  - [ ] **Step 5: Commit** `feat: claims library and number matching`

### Task 6: Topic sources

**Files:**
- Create: `engine/topics.py`, `content/myth-topics.yaml`, `tests/fixtures/et-markets.xml`
- Test: `tests/test_topics.py`

**Interfaces:**
- Produces: `topics.FEEDS: list[tuple[str, str, int]]` (name, URL, rank) = ET Markets, ET Economy, Mint Markets, Business Standard Markets, RBI press releases, SEBI press, BSE corporate announcements RSS; `topics.fetch_feed(url, fetch=urlopen) -> list[dict{title, link, published, source, summary}]` (stdlib `xml.etree`, RSS 2.0 and Atom); `topics.score(item: dict) -> int` (+3 has a number, +2 household keyword hit, +rank, −10 if title contains a banned politics term); `topics.pick_finance(items, used_links: set, now) -> dict | None` (last 24 h, best score, not used in 30 days); `topics.next_myth(root, used_ids: set) -> dict` (rotation through `content/myth-topics.yaml`: `{id, title_hi, place, hooks[3], allowed_sources[], notes}`; seed 40 topics from spec §B).

- [ ] **Step 1: Tests**: `test_parse_rss_fixture_yields_items`, `test_score_prefers_number_and_household_keyword`, `test_pick_skips_used_and_old`, `test_myth_rotation_skips_used_and_wraps`.
- [ ] **Step 2-5:** fail → implement → pass → commit `feat: topic sources`

### Task 7: Research (Gemini, grounded)

**Files:**
- Create: `engine/gemini.py`, `engine/research.py`, `content/prompts/research-finance.txt`, `content/prompts/research-myth.txt`
- Test: `tests/test_research.py`

**Interfaces:**
- Produces: `gemini.generate(model: str, body: dict, key: str, post=_post) -> dict` (status handling as arthvan-media `tts._generate`: 3 tries, 60 s wait on 429/503); `research.fact_sheet(topic: dict, channel: str, ask=gemini.generate) -> dict` using model `gemini-3.8-flash`, `tools:[{"google_search":{}}]`, `generationConfig.responseMimeType="application/json"`, temperature 0; output `{facts:[{text, number, unit, source_url, source_name, source_date, quote, label}], summary}`; `research.clean(sheet: dict, channel: str, today: date) -> dict` drops facts without URL, finance facts older than 7 days for news pieces, mythology facts without a label in `{scripture, archaeology, disputed, legend}`.

- [ ] **Step 1: Tests**
```python
def test_fact_without_url_is_dropped(): ...
def test_old_finance_fact_is_dropped(): source_date 10 days back → gone
def test_myth_fact_needs_label(): label "maybe" → dropped
def test_fact_sheet_uses_grounding_tool(fake_ask): body["tools"] == [{"google_search": {}}]
```
- [ ] **Step 2-5:** fail → implement → pass → commit `feat: grounded research fact sheet`

### Task 8: Writer (Claude, Gemini fallback)

**Files:**
- Create: `engine/writer.py`, `content/prompts/writer-system.txt`, `content/prompts/formula-sglearning.txt`, `content/prompts/formula-arthvan.txt`, `engine/schema.py`
- Test: `tests/test_writer.py`

**Interfaces:**
- Consumes: fact sheet (Task 7), claims library (Task 5), banned list (Task 4).
- Produces: `schema.PIECE_SCHEMA: dict` (JSON schema: `hook, scenes[{vo, visual{type∈avatar|art|card|photo, prompt, card{big_number,line,source}}, facts_used[int], label}], end_question, cards[], captions{youtube{title,description,tags[],chapters[]}, instagram{caption,hashtags[]}, threads{text}}, carousel: bool`, `additionalProperties: false`, all required); `writer.write(piece: Piece, sheet: dict, library: list, banned: dict, formula: str, client=None) -> dict` calling `anthropic.Anthropic().beta.messages.create(model="claude-opus-5-5", max_tokens=16000, output_config={"effort": "high", "format": {"type": "json_schema", "schema": PIECE_SCHEMA}}, betas=["server-side-fallback-2026-07-01"], fallbacks="default", system=[{type:"text", text: writer-system + formula, cache_control:{type:"ephemeral"}}], messages=[{role:"user", content: fact sheet + library + banned as JSON}])`; on `stop_reason == "refusal"` or any `anthropic.APIStatusError` after SDK retries → `writer.write_with_gemini(...)` (same schema via `responseMimeType=application/json`, model `gemini-3.8-flash`) and `piece.writer = "gemini"`; `writer.cost_usd(usage) -> float` ($4/M in, $20/M out) recorded to `logs/claude-spend.json` by day.
- System prompt content (fixed by spec): the channel formula (§C), the voice ("seedhi baat", second person, no "namaste dosto", first line is the claim or the question), hard rules (numbers only from the fact sheet, every number written in digits in `vo`, finance disclaimer line verbatim, mythology labels), `visual.type == "avatar"` allowed only for hook, so-what, end card and chapter turns.

- [ ] **Step 1: Tests** (inject a fake client returning a canned `Message`): `test_request_uses_opus_schema_and_fallbacks`, `test_refusal_falls_back_to_gemini_and_marks_writer`, `test_cost_recorded_per_day`, `test_schema_rejects_unknown_visual_type` (jsonschema-free: validate with a small recursive checker in `schema.validate(obj) -> list[str]`).
- [ ] **Step 2-5:** fail → implement → pass → commit `feat: Claude writer with Gemini fallback`

### Task 9: Voice (replicated Gemini TTS)

**Files:**
- Create: `engine/voice.py`, `content/voice.json`
- Test: `tests/test_voice.py`

**Interfaces:**
- Produces: `voice.enrol(ref_wav: Path, consent_wav: Path, key: str, display_name: str, post=_post) -> str` (voice id; CLI `python -m engine.voice --enrol <ref.wav> <consent.wav>` writes `content/voice.json = {"default": id, "fallback": id, "created": date}`); `voice.say(text: str, voice_id: str, out_wav: Path, *, key, cache_dir=ROOT/"cache"/"voice", budget=ROOT/"logs"/"voice-budget.json", post=_post, style="clear, warm Hindi explainer") -> float` (seconds; cache key sha1(voice_id|style|text); one request per call; raises `VoiceBudget` when the day's count ≥ 80 before making the request); `voice.lines(piece: Piece, voice_id, **kw) -> list[tuple[Path, float]]`; `voice.requests_today(budget) -> int`.

- [ ] **Step 1: Tests**
```python
def test_cached_line_costs_no_request(tmp_path, fake_post): say twice → fake_post.calls == 1
def test_budget_hit_mid_piece_keeps_cache(tmp_path, fake_post):
    budget file at 79 → first line ok, second raises VoiceBudget; cache dir has 1 wav; rerun with fresh budget makes 1 more request only
def test_enrol_builds_replicated_body(fake_post): body["voice"]["type"] == "replicated" and both audio parts present
```
- [ ] **Step 2-5:** fail → implement → pass → commit `feat: replicated voice synthesis with cache and budget`

### Task 10: Art (scenes, avatar library, Commons photos)

**Files:**
- Create: `engine/art.py`, `content/prompts/style-sglearning.txt`, `content/prompts/style-arthvan.txt`, `content/prompts/avatar.txt`, `content/avatar-library.yaml`
- Test: `tests/test_art.py`

**Interfaces:**
- Produces: `art.paint(prompt: str, out: Path, *, refs: list[Path] = (), key, model="gemini-3.1-flash-lite-image", spend=ROOT/"logs"/"image-spend.json", post=_post) -> Path` (request shape copied from arthvan-media `illustrate._generate_with`: inline base64 refs + text, `responseModalities ["IMAGE"]`; cache by sha1(model|prompt|ref names); ₹3 per call recorded by day; raises `ImageBudget` when day ≥ ₹150); `art.avatar(pose_key: str, root=ROOT) -> Path` (returns `assets/avatar/<pose>.png`, generating once from `Reference/founder-01,05,11.jpg` + the pose line in `avatar-library.yaml`: 30 entries: `explaining_front, surprised, thinking, pointing_right, end_smile, chapter_turn, ...`, each with its prompt and which 3 reference photos to send); `art.commons_photo(query: str, out_dir: Path, fetch=urlopen) -> dict | None` (Wikimedia Commons API `action=query&generator=search&prop=imageinfo&iiprop=url|extmetadata`; accept only `LicenseShortName` in {CC0, CC BY 4.0, CC BY-SA 4.0, Public domain}; returns `{path, credit}`); CLI `python -m engine.art --avatar-library` builds all 30 (≈ ₹90 once).
- `Reference/` photos are copied into `assets/reference/` in this task (they are the founder's own, not secret).

- [ ] **Step 1: Tests**: `test_paint_is_cached_by_prompt`, `test_image_budget_stops_at_150`, `test_commons_rejects_non_free_licence` (fixture JSON with `CC BY-NC`), `test_avatar_uses_three_reference_photos`.
- [ ] **Step 2-5:** fail → implement → pass → commit `feat: scene art, avatar library, Commons photos`

### Task 11: Cards and thumbnails (Playwright)

**Files:**
- Create: `engine/cards.py`, `templates/{hook,number,source,label,end,thumb,slide}.html`, `assets/fonts/` (Noto Sans Devanagari, Inter, with OFL licence files)
- Test: `tests/test_cards.py` (marked `slow`)

**Interfaces:**
- Produces: `cards.render(kind: str, data: dict, out: Path, size: tuple[int,int]) -> Path` (kinds: `hook` {line, avatar_path?}, `number` {big_number, line, source}, `source` {name, date} strip 1080×120, `label` chip {label} 400×90 transparent, `end` {question, handle}, `thumb` {words[2..4], number?, avatar_path?} 1280×720, `slide` {big_number, line, source} 1080×1350); one Chromium per process, `page.set_content` + `screenshot(clip=...)`; text must read at 150 px wide: minimum font size 64 px on 1080-wide cards.

- [ ] **Step 1: Tests** (`@pytest.mark.slow`): `test_number_card_is_1080x1920_png`, `test_thumb_is_1280x720`, `test_devanagari_renders_no_tofu` (render "₹80 हज़ार" and assert the PNG's non-background pixel count > 2 % of area).
- [ ] **Step 2-5:** fail → implement → pass (`python -m playwright install chromium` once) → commit `feat: cards and thumbnails`

### Task 12: Assembly (ffmpeg)

**Files:**
- Create: `engine/assemble.py`, `engine/captions.py`, `assets/music/` (3 beds + licences)
- Test: `tests/test_assemble.py` (slow), `tests/test_captions.py`

**Interfaces:**
- Consumes: voiced lines (Task 9), pictures (Task 10), cards (Task 11).
- Produces: `captions.split(vo: str, seconds: float) -> list[tuple[float, float, str]]` (phrases ≤ 6 words, time proportional to syllable count, Devanagari and Latin counted); `captions.ass(cues, size) -> str` (ASS with Noto Sans Devanagari, bottom third for 9:16, lower-sixth for 16:9); `assemble.scene_clip(image: Path, seconds: float, size, out: Path, zoom=1.08) -> Path` (zoompan at 30 fps); `assemble.build(piece: Piece, lines: list[tuple[Path,float]], visuals: list[Path], size, out_dir: Path, music: Path) -> Path` (concat scene clips, overlay source strip on finance scenes and label chip on mythology claim scenes, mix voice (−16 LUFS) over music (−22 LUFS, ducked), loudnorm two-pass, writes `reel.mp4` (= story) or `long.mp4`); `assemble.chapters(piece, timings) -> str` (YouTube chapter lines `00:00 Hook`).

- [ ] **Step 1: Tests**: `test_split_times_sum_to_scene_length`, `test_ass_has_devanagari_font`, slow: `test_two_scene_short_builds_1080x1920_30fps` (synthetic PNGs + 2 s silent WAVs → ffprobe width/height/fps/duration ≈ 4.0 ± 0.2).
- [ ] **Step 2-5:** fail → implement → pass → commit `feat: ffmpeg assembly with captions`

### Task 13: QA on rendered files

**Files:**
- Create: `engine/qa.py`
- Test: `tests/test_qa.py` (slow)

**Interfaces:**
- Produces: `qa.report(path: Path, kind: str, voiced_seconds: float, caption_cues: list) -> list[str]` (empty = pass): duration (short 40-59 s; long within ±20 % of target), integrated loudness −16 ± 1.5 LUFS (`ebur128`), decode errors 0 (`ffmpeg -v error -f null`), freeze > 3 s (`freezedetect`), first frame not black (`blackdetect` on first 0.5 s), caption coverage ≥ 95 % of voiced time.

- [ ] **Step 1: Tests**: `test_silent_black_clip_fails_three_ways`, `test_good_synthetic_clip_passes` (tone at −16 LUFS over a coloured frame).
- [ ] **Step 2-5:** fail → implement → pass → commit `feat: render QA`

### Task 14: YouTube upload

**Files:**
- Create: `engine/youtube.py`
- Test: `tests/test_youtube.py`

**Interfaces:**
- Produces: `youtube.access_token(channel: str, env) -> str` (refresh-token grant, as arthvan-media); `youtube.metadata(piece: Piece, publish_at_utc: datetime) -> dict` (`snippet.title` ≤ 60 incl. ` #Shorts` for shorts, `snippet.description` = hook + so-what + `Sources:` lines + disclaimer (finance) + chapters (long) + hashtags, `tags` ≤ 15, `categoryId` 22 (sglearning) / 27 (arthvan), `status = {privacyStatus: "private", publishAt: iso, selfDeclaredMadeForKids: false, containsSyntheticMedia: true}`; `UNLISTED_DAY1=1` env switches `privacyStatus` to `unlisted` with no `publishAt`); `youtube.upload(token, path, metadata, call=_call) -> str` (resumable, as arthvan-media `upload_short`); `youtube.set_thumbnail(token, video_id, jpg, call=_call) -> bool` (logs and returns False on 403).

- [ ] **Step 1: Tests**: `test_short_title_keeps_suffix_within_60`, `test_description_lists_sources_and_disclaimer`, `test_status_is_scheduled_private_with_synthetic_flag`, `test_unlisted_day1_has_no_publish_at`, `test_thumbnail_403_returns_false`.
- [ ] **Step 2-5:** fail → implement → pass → commit `feat: YouTube scheduled upload`

### Task 15: Instagram and Threads

**Files:**
- Create: `engine/instagram.py`, `engine/threads.py`
- Test: `tests/test_instagram.py`, `tests/test_threads.py`

**Interfaces:**
- Produces: `instagram.media_url(piece: Piece, name: str, repo: str) -> str` (`https://raw.githubusercontent.com/<repo>/<out_sha>/out/<id>/<name>`); `instagram.post_reel(ig_id, token, video_url, caption, call, sleep) -> str`; `instagram.post_story(...) -> str`; `instagram.post_carousel(ig_id, token, image_urls: list[str], caption, call, sleep) -> str` (container per slide → CAROUSEL → publish; polling as arthvan-media `_wait`, max 90 polls × 4 s); `instagram.publish_piece(piece: Piece, env, call, sleep) -> Piece` (skips each platform id already present on the piece, saves after each success); `threads.post_video(uid, token, video_url, text, call, sleep) -> str`.

- [ ] **Step 1: Tests**
```python
def test_partial_publish_resumes_without_duplicate(fake_call):
    piece.ids["ig_reel_id"] = "123"  → publish_piece makes no REELS container, makes STORIES
def test_carousel_only_when_flagged(): piece.script["carousel"] False → no CAROUSEL call
def test_media_url_uses_out_sha(): ...
def test_threads_text_within_500(): ...
```
- [ ] **Step 2-5:** fail → implement → pass → commit `feat: Instagram and Threads publishing`

### Task 16: Telegram bot

**Files:**
- Create: `engine/telegram.py`, `engine/digest.py`
- Test: `tests/test_digest.py`, `tests/test_telegram.py`

**Interfaces:**
- Produces: `telegram.send(text, env, post=_post) -> bool`; `telegram.send_file(path, caption, env, post) -> bool`; `telegram.poll_commands(env, state=ROOT/"logs"/"tg-offset.json", get=_get) -> list[str]` (`/pause` writes `logs/pause.json`, `/resume` removes it, `/status` replies with `digest.status_line`); `digest.run_summary(root, day) -> str` (made / rejected with reasons / posted / buffer days per channel / spend / voice requests); `digest.alerts(root, day) -> list[str]` (buffer < 2 days, two failed runs, token expiry ≤ 7 days from `logs/tokens.json`); `digest.status_line(root) -> str`.

- [ ] **Step 1: Tests**: `test_summary_counts_pieces_by_status`, `test_alert_when_buffer_under_two_days`, `test_pause_command_writes_flag`, `test_send_scrubs_secrets`.
- [ ] **Step 2-5:** fail → implement → pass → commit `feat: Telegram digest, alerts and commands`

### Task 17: Buffer planner and produce CLI

**Files:**
- Create: `engine/buffer.py`, `engine/pipeline.py`, `engine/produce.py`
- Test: `tests/test_buffer.py`, `tests/test_pipeline.py`

**Interfaces:**
- Consumes: everything above.
- Produces: `buffer.needed(root, today_ist: date, horizon_short=7, horizon_long=3) -> list[tuple[date, str, str]]` (publish day, channel, kind) for pieces not yet `uploaded`/`posted`, longs first, then earliest Shorts; `pipeline.Deps` dataclass bundling injectable functions (`research, write, say, paint, render_card, build, qa, upload, set_thumbnail`); `pipeline.make(piece: Piece, deps: Deps, root) -> Piece` running steps 1-10 of spec §3 with `pieces.transition` after each, 3 topic tries on lint reject, budget exceptions → `failed-<step>` and return; for mythology Shorts, source scenes from the week's long piece record (`piece.topic["from_long"]`); `produce.main(argv) -> int` (`--dry-run` stops before upload and writes to `out/`; `--max 3`; exits 0 when a budget stops the run, 1 on an unexpected exception) and appends to `logs/runs.jsonl`, then sends the Telegram digest.

- [ ] **Step 1: Tests**: `test_needed_orders_longs_first_then_shorts`, `test_needed_skips_uploaded`, `test_make_rejected_script_tries_next_topic_up_to_three`, `test_make_voice_budget_marks_failed_voice_and_returns`, `test_myth_short_reuses_long_scenes`, `test_dry_run_never_calls_upload`.
- [ ] **Step 2-5:** fail → implement → pass → commit `feat: buffer planner and produce pipeline`

### Task 18: Publish CLI

**Files:**
- Create: `engine/publish.py`
- Test: `tests/test_publish.py`

**Interfaces:**
- Produces: `publish.due(root, now_utc: datetime, channel: str) -> list[Piece]` (pieces with `status == uploaded`, `kind == short`, publish day = today IST, platform ids missing, and `slots.ig_slot_ok`); `publish.main(argv) -> int` (`--channel sglearning|arthvan`; posts via `instagram.publish_piece` and `threads.post_video`, transitions to `posted` when all ids present; honours `logs/pause.json`; digest afterwards).

- [ ] **Step 1: Tests**: `test_due_only_today_uploaded_shorts_missing_ids`, `test_pause_flag_skips_everything`, `test_posted_when_all_ids_present`.
- [ ] **Step 2-5:** fail → implement → pass → commit `feat: publish CLI`

### Task 19: Weekly report

**Files:**
- Create: `engine/report.py`
- Test: `tests/test_report.py`

**Interfaces:**
- Produces: `report.youtube_week(token, channel_id, start, end, call) -> dict` (YouTube Analytics API `reports.query` metrics views, estimatedMinutesWatched, subscribersGained, averageViewPercentage by video); `report.instagram_week(ig_id, token, call) -> dict` (insights reach, plays, follower_count); `report.text(data: dict, targets: dict) -> str` (per channel vs spec §E day-90 targets, top 5 comments by like count); `report.main(argv)` writes `logs/weekly.json` and sends to Telegram.

- [ ] **Step 1: Tests**: `test_text_marks_short_average_under_200_as_hook_change_needed`, `test_targets_progress_percent`.
- [ ] **Step 2-5:** fail → implement → pass → commit `feat: weekly report`

### Task 20: GitHub Actions workflows and secrets checklist

**Files:**
- Create: `.github/workflows/produce.yml`, `.github/workflows/publish.yml`, `.github/workflows/weekly-report.yml`, `.github/workflows/refresh-tokens.yml`, `.github/workflows/tests.yml`, `docs/secrets.md`, `scripts/prune_out.py`
- Test: `tests/test_workflows.py`

**Interfaces:**
- `produce.yml`: cron `0 2 * * *` and `0 3 * * *`, `workflow_dispatch` inputs `dry_run`, `max`; steps: checkout, setup-python 3.12 with pip cache, apt ffmpeg, pip install, playwright chromium, `pytest -q -m "not slow"`, run `python -m engine.produce`, `scripts/prune_out.py --days 14`, commit `pieces/ out/ logs/ content/voice.json` as `sg-content-bot` and push; `concurrency: produce`, `timeout-minutes: 120`, `permissions: contents: write`.
- `publish.yml`: crons `30 7 * * *` (sglearning) and `0 16 * * 1,3,5` (arthvan), each runs `python -m engine.publish --channel <x>`, commits `pieces/ logs/`.
- `weekly-report.yml`: `0 5 * * 1`. `refresh-tokens.yml`: `0 6 1 * *` runs `python -m engine.instagram --refresh` and `python -m engine.threads --refresh`, writes new expiry to `logs/tokens.json` (tokens themselves go to Telegram as "rotate secret X" alerts; Actions cannot write secrets).
- `tests.yml`: on push and pull_request, `pytest -q` including slow tests with ffmpeg and Chromium installed.
- `docs/secrets.md`: the 12 secret names, where each comes from, and the `gh secret set NAME < file` commands.

- [ ] **Step 1: Test**: `test_workflows_parse_and_name_only_known_secrets` (yaml.safe_load each file; every `${{ secrets.X }}` is in the Global Constraints list).
- [ ] **Step 2-5:** fail → write → pass → commit `ci: workflows`

### Task 21: Local integration run and Day-1 unlisted mode

**Files:**
- Modify: `README.md` (run book), `engine/produce.py` (`--unlisted-day1`)
- Create: `.env` (local, from `~/Desktop/SG-Content-Project/keys/`), `content/voice.json` (via `engine.voice --enrol`)

- [ ] **Step 1:** Move the three key files into `~/sg-content/.env` (`ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `TELEGRAM_BOT_TOKEN`), copy the YouTube, Instagram and Threads values from `~/arthvan-social/.env` by name only (never print them), resolve `TELEGRAM_CHAT_ID` with `python -m engine.telegram --find-chat`, delete `~/Desktop/SG-Content-Project/keys/`.
- [ ] **Step 2:** `python -m engine.voice --enrol <scratch refMix.wav> <consent2.wav>` (the 25.5 s mixed sample and the 21:17 consent take, both at `Voice/` after this step copies them in as `Voice/sample-mixed.wav` and `Voice/consent.wav`); expect a `voice_...` id in `content/voice.json`.
- [ ] **Step 3:** `python -m engine.art --avatar-library`; expect 30 PNGs under `assets/avatar/` and `logs/image-spend.json` ≈ ₹90.
- [ ] **Step 4:** `python -m engine.produce --dry-run --max 2 --only sglearning:short,arthvan:long --long-minutes 3`; expect `out/<id>/reel.mp4` and `out/<id>/long.mp4`, QA pass lines in the log, Telegram digest received. Copy both files to `~/Desktop/SG-Content-Project/Preview/` for the founder.
- [ ] **Step 5:** Founder watches both and says go. Then `UNLISTED_DAY1=1 python -m engine.produce --max 2` uploads them unlisted; links in Telegram.
- [ ] **Step 6:** Commit `docs: run book and first integration run`. Founder pushes `main`, creates the 12 secrets per `docs/secrets.md`, and enables the workflows. Day 2 onward: cron runs public.

---

## Self-review notes (done 19 Oct 2026)
- Spec coverage: §1 cadence → Tasks 2, 17, 18; §3 steps 1-12 → Tasks 6-16; §4 packaging → Tasks 4, 14, 15; §5 avatar → Tasks 4 (cap), 10; §6 gates → Tasks 4, 5, 7, 9, 10, 13; §7 errors → Tasks 7, 9, 15, 16, 17; §8 testing → every task + Task 21; §9 budgets → Tasks 8, 9, 10; §10 out of scope honoured (thumbnail A/B stored only: Task 14 uploads one, Task 11 renders two).
- Names used consistently: `Piece`, `pieces.transition`, `secrets.get/scrub`, `slots.utc_for`, `voice.say`, `art.paint`, `cards.render`, `assemble.build`, `qa.report`, `youtube.upload`, `instagram.publish_piece`, `pipeline.make`, `buffer.needed`, `publish.due`.
- Review Focus tests are placed in Tasks 2, 5, 7, 9, 15.
