# Founder decisions (read before asking)

Settled decisions for ALL of the founder's work: sg-content, arthvan-media, ScoreMyBiz, Waypoint. Every Claude session (Mac, VS Code,
phone, cloud) reads this file first and follows it instead of asking again. When the founder settles something new, the session adds one
line here (who, date) in the same change. Newest first.

## Recent changes and why (newest first)
- 24 Oct 2026: **Volumes and styles are settled; price them, never re-ask or propose cutting them** (founder: "we already decided this").
  Learning with SG and SG-MYTH-WORLD: a Short every day on each; longs Wed + Sat (Learning with SG) and Thu + Sun (SG-MYTH-WORLD), set 21 Oct
  in `engine/config.py`, which is 60 Shorts and 17 longs in a 30-day month. ScoreMyBiz and Waypoint: one app post a day from arthvan-media
  `content/schedule.json`, with Reels from the queue in `content/production_queue.json` (31 sets, 27 Oct to 9 Dec). Styles: see "Picture style".
  New Veo clips stop by design when the Google trial credit is finished (`story.film_available`); a day with no Reel gets the graphics set.
- 24 Oct 2026: cost per piece (founder: "no charges on waste or repetitive tasks"). `engine/costs.py` keeps each piece's running cost in `ids["cost"]`
  (pictures in rupees, Claude in dollars, voice lines) across runs, re-makes and crashes; the 9 pm alerts name a piece from the last two days that cost
  more than 3x the median of its kind (needs 5 pieces of that kind). `python -m engine.costs` lists them. Subtitle translation (Sonnet) is now in
  the Claude meter. Still unmetered: Gemini research and the voice read-back (no verified price; research is capped at 4 calls per piece per day).
- 24 Oct 2026: 9 pm card day: before 05:00 WAT still counts as the previous day (`evening.card_day`; the app poster's relay uses the same rule).
- 24 Oct 2026: **Everything already made posts as made, in its old look; everything new is made in the revised styles. Only the pictures change; the
  way stories and scripts are made does not.** Reusing clips between Reels was tried as a sample and dropped by the founder: do not build it.
- 24 Oct 2026: cost cuts that do not touch the video (founder, "go ahead"): story word limit is soft up to 260; a draft that fails only on an unsourced
  number, banned wording, a missing label or being too long is PATCHED (only the failing scenes are rewritten, ~$0.03 against ~$0.30 for a full
  draft; tried twice, then a full rewrite); each piece gets at most 6 drafts and 4 research calls per quota day; `scripts/remake.py` needs `--yes`
  and is used only for defects viewers can see. Expected content-pipeline cost about ₹4,000-4,500 a month (estimate, not a cap); hard stops are the
  provider limits the founder sets (Anthropic workspace limit, AI Studio project cap) plus the in-code ceilings.
- 22 Oct 2026: Play Console is read by a read-only service account (`play-reports-reader`, key in ~/sg-content/play-reader-key.json, never committed); no
  write rights. `engine/playreports.py --weekly` sends installs, countries, ratings and Waypoint's phase gates (`content/growth-gates.yaml`) every Monday.
- 23 Oct 2026: one picture style per brand (see "Picture style"); only the pictures change. Founder, after comparing nine styles.
- 23 Oct 2026: GitHub skipped every morning job; the LinkedIn post and the Learning with SG post were started by hand. Fix: the Supabase clock
  starts each job at its exact Lagos minute (docs/external-scheduler.md). **Live since 24 Oct 09:39 UTC**: the founder added `GITHUB_TOKEN`;
  12 jobs in `command.clock`, pg_cron ticks every minute with no failures, and thumbtest (12:45 WAT) and produce (14:45 WAT) started on the exact minute.
  A slot missed by the clock is caught up for 3 hours; GitHub's own cron and the Mac triggers stay as backups (engines never post twice).
- 22 Oct 2026: LinkedIn gets picture posts only (sg-content b67bc3e, arthvan-media 0e1d13f); no app posts on LinkedIn (arthvan-media 75b3a12).
- 21-22 Oct 2026: control room (claude.ai page + Telegram buttons) on branch `command-center`, PR #1. Run reports already reach `command.events` from the production and publish runs (checked 24 Oct), so `SG_COMMAND_KEY` works.

## Picture style (founder, 23 Oct 2026)
- Learning with SG: **claymation**. SG-MYTH-WORLD: **Indian comic (retro)**. ScoreMyBiz ads: **3D animated film**. Waypoint ads: **soft
  painted anime** (inspired by the look, never a copy of any studio). Prompts: content/prompts/style-<channel>.txt here; arthvan-media
  content/brand_styles.json.
- **Only the pictures change.** Logo, the watermark (including the faint one in the centre), voice, captions, title band, layout, music,
  posting times and dates, channels, titles and descriptions stay exactly as they are.
- **The reserve goes out as made.** Pieces already made keep their pictures and post at their scheduled time; nothing is redrawn. The new
  look starts with the next new piece.
- The cast keeps the same people, drawn once per channel in that channel's style (assets/cast/<channel>/).

## Operating rules
- **Buffer (supersedes the 21 Oct line below): 7 days of Shorts and 4 longs per channel; an alert under 7 / under 4.** (founder, 22 Oct 2026; engine/digest.py)
- **No trimming, no speed-up, no Google voices.** Narration runs at its natural speed and length; only the designed storyteller voices are used. (founder, 22 Oct 2026)
- **Fully automatic.** The founder never decides what is made or posted on a given day. Topics, scripts, voice, video, upload and posting run on their own; a piece that fails a check is skipped and retried by the next run, never posted. (founder, 21 Oct 2026)
- **Buffer: never under 4 days, aim for 5+.** The buffer targets 7 days of Shorts and 10 of longs (`engine/buffer.py`); under 4 days is an alert (`digest.BUFFER_ALERT_DAYS`). (founder, 21 Oct 2026)
- **One failure never stops the rest.** A crash in one piece marks that piece `failed-crash` and the run carries on (`engine/produce.py`). (21 Oct 2026, after the long-video crash)
- **Instagram Story only when the Short fits in 60 s.** A longer Reel keeps its full length and that day has no Story; a Story is never
  trimmed. (founder, 22 Oct 2026)
- **Never early.** A Short goes out at its slot (at most an hour early), even when a GitHub run is late. (23 Oct 2026, after a late run
  posted the next day's Short 20 hours early)
- **No duplicates.** A piece is made once per publish slot (`pieces/<day>-<channel>-<kind>.json`); finished pieces are never remade; each platform is posted once per piece (its id is stored before the next platform is tried).
- Claude writes every script; Gemini is only the fallback, and a fallback is recorded on the piece. (founder, 20 Oct 2026)

## Engagement (founder, 23 Oct 2026)
- Each public Short gets a channel comment and a description line pointing to the channel's newest public long video (engine/ytlink.py).
  YouTube's API cannot pin a comment; pinning is the founder's optional tap.
- Threads video posts carry a topic tag (Personal Finance / Indian Mythology) and one poll under them: "Pehle se pata tha / Aaj pata chala".
- Instagram captions ask "Comment karein APP"; engine/commentdm.py answers each such comment once by DM with the Play link
  (ScoreMyBiz for Learning with SG, Waypoint for SG-MYTH-WORLD). Needs the messaging permission on the Instagram token.
- Instagram Reels go out as Trial Reels: shown to non-followers first, shared with followers by Instagram when they do well
  (graduation SS_PERFORMANCE); a plain Reel when Instagram refuses a trial. (founder, 23 Oct 2026)
  The 9 pm card lists each Trial Reel once its 72 hours are over (views, likes, comments, shares, saves, link) so the founder can tap
  "Share to followers" by hand when Instagram did not; Meta's API can neither read nor do that step (founder, 24 Oct 2026, option 2).
  Sharing stays a manual tap: no re-posting the video as a normal Reel, no app automation (founder, 24 Oct 2026, "keep the tap").
- Reels (founder, 25 Oct 2026, after the 24 Oct diagnosis): Shorts keep their length (item 1 left). Finance topics favour the viewer's
  own wallet (engine/topics.py WALLET); myth topics put famous, easy-to-picture places first (`priority: 1` in myth-topics.yaml).
  Learning loop: the weekly report saves the three best and worst openings per channel (logs/hook-lessons.json, from 6 Shorts) and
  the writer reads them as examples. The opening rule (item 2) was not chosen; the data later showed the same scene-setting opener
  on both a 1,358-view and a 59-view Short, so topic, not that opener, made the difference.
- Reel link tips: up to 8 a month (founder, 24 Oct 2026: their Meta Verified plan allows 8; public pages list 2/4/6 by tier).
- Long videos run a thumbnail click test: B (same picture, the title's words) two days after going public; the higher click rate
  stays, A when the numbers are missing or too few (engine/thumbtest.py). (founder, 23 Oct 2026)
- Meta Verified (one month from 23 Oct 2026): Reel links are app-only and few, so engine/reeltip.py sends a daily Telegram tip naming
  the Reel taking off and the exact Play link to add (max 4 a month). Renew only if the Reel links bring installs. (founder, 24 Oct 2026)
- The weekly "what's working" report is report-only; nothing changes topics or posting on its own without the founder's yes.

## Reporting
- All times told to the founder are in **WAT (Lagos)**. (founder, 22 Oct 2026)
- The control room's live status refreshes on its own every 30 seconds. (founder, 22 Oct 2026)

## Approved 24 Oct 2026 (founder: "okay yes do"), built one at a time
- A: each YouTube Short description carries an app line with a tagged Play link (ScoreMyBiz under Learning with SG, Waypoint under
  SG-MYTH-WORLD). The video itself does not change.
- B: app ad posts drop from daily to 2-3 a week, each as an Instagram Trial Reel.
- 10: YouTube comment replies: Claude drafts, Telegram Approve/Skip; after two weeks friendly replies may go automatically.
- 7: nightly Claude routine reads the newest app crash and opens a fix pull request with a test; never merges.
- 13: Waypoint ban-appeal review (Claude summary, founder decides) and a weekly spot-check of 20 AI moderation decisions.
- 12a: ScoreMyBiz payment follow-up WhatsApp: **left** by the founder (24 Oct 2026, "leave 12a"). Do not build or re-propose it.
  Found first: the approved due-reminder wording says it "never asks for payment details" and has no UPI (trust and every country),
  so a pay link would have broken that; the safer form (Already paid / Will pay in 7 days buttons) was offered too.
- Later (founder's call): 8 app releases from the phone, 9 Waypoint Expo upgrade, 12b WhatsApp entry form, 12c partner payouts,
  11 WhatsApp usernames, the Play service account.

## Open (not decided yet; ask, don't assume)
- WhatsApp spend after Meta's 1 Oct 2026 price change: not built. On 23 Oct ScoreMyBiz had sent 32 WhatsApp messages in 30 days,
  far under the 1,000 free a month; build the spend line when sends pass 500 a month.
- Waypoint crisis help (helplines from chats, comments, check-in; more languages; voice alert): founder said **no** on 23 Oct 2026.
  Waypoint PR #1 stays unmerged; do not merge or re-propose unless the founder asks.
- Google Play service account (review replies, crash watch): later, founder's call (23 Oct 2026).
- LinkedIn re-login reminder on Telegram: not wanted (founder, 23 Oct 2026). Do not build it.
- Moving the app Reel production off the Mac: the founder takes this on, starting 23 Oct 2026 evening.
- Exact clock: running in Supabase (`command.clock`, function `sg-command`) since 24 Oct 2026 09:39 UTC; `GITHUB_TOKEN` is set. Do not ask the founder for it again.
  24 Oct 15:00 UTC fix: each job fired only once (last_fired kept microseconds, the function compares milliseconds); the column is now
  `timestamptz(3)` (migration 20261024_clock_ms.sql). YouTube reply drafts (ytreplies.yml) run every 3 hours from the clock.
- Clock watchdog (founder yes, 24 Oct 2026): Supabase function `sg-watchdog`, pg_cron every 10 minutes. Telegram (once per problem) when a
  clock job is 30 minutes late or a GitHub run of a clock workflow fails; quiet while sg-content is paused. Starts nothing.
- Threads HTTP 500 code 2 on 24 Oct: caused by the topic tag (the publish step failed on tagged posts; untagged drafts were fine). Since
  PR #14 a failed tagged post is retried whole without the tag; the 24 Oct SG-MYTH-WORLD Short then posted at once. Topic feeds may
  simply not apply until Threads accepts tags again.

## Control room (phone)
- One menu for everything (24 Oct 2026): the Telegram buttons (webhook to sg-command) also start the app posts and the LinkedIn
  post; the clock (command.clock) starts every scheduled job at its Lagos minute.
- Private claude.ai page plus Telegram as the fallback; buttons for pause, resume, stop, retry, run now, post now, and typed instructions that become one of those actions after a confirm. (founder, 21 Oct 2026)
- Commands and status live in a walled-off `command` schema inside the ScoreMyBiz Supabase project (free plan, 2-project limit), never in this public repo. (founder, 21 Oct 2026)

## Scope
- Channels: Learning with SG (`sglearning`) and SG-MYTH-WORLD (`arthvan`) on YouTube, Instagram Reels and Stories, Threads.
- **LinkedIn:** the founder's personal profile, **picture posts only**, one a day from arthvan-media `linkedin-personal`; no Short or Reel video and no app posts go to LinkedIn. (founder, 22 Oct 2026; replaces the 21 Oct "each Short as a native video")
- **ScoreMyBiz and Waypoint** join the control room: business numbers, social promotion of both, and controls for them. (founder, 21 Oct 2026)
