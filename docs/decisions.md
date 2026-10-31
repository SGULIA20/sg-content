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
  27 Oct 2026: the API's `is_shared_to_feed` shows it (24 Oct: Learning with SG 1,235 views True, SG-MYTH-WORLD 115 views False),
  so the card marks each one ✅ shared or 👉 not shared, and the founder taps only the 👉 ones.
- Reels (founder, 25 Oct 2026, after the 24 Oct diagnosis): Shorts keep their length (item 1 left). Finance topics favour the viewer's
  own wallet (engine/topics.py WALLET); myth topics put famous, easy-to-picture places first (`priority: 1` in myth-topics.yaml).
  Learning loop: the weekly report saves the three best and worst openings per channel (logs/hook-lessons.json, from 6 Shorts) and
  the writer reads them as examples. The opening rule (item 2) was not chosen; the data later showed the same scene-setting opener
  on both a 1,358-view and a 59-view Short, so topic, not that opener, made the difference.
  Then (founder, 25 Oct 2026, "do 2nd also"): the opening rule is on. Scene 1 is the hook, word for word: the surprising fact or the
  question, with a number or a name, at most 12 words (Hinglish needs ke/ka/hai; Ram Setu's 11-word opening was the best), never a
  time, day or character first. engine/lint.py check_hook; a miss rewrites the same topic. Shorts are one file for YouTube and
  Instagram, so both get it. The made reserve goes out as made.
- LinkedIn (founder, 25 Oct 2026, after the 90-day export: 1,245 followers; our posts 50-120 impressions, the founder's own
  hand post of 9 Oct 3,213): post at 08:10 WAT (clock; was 04:40) so the founder can reply in the first hour, with a Telegram
  nudge; Mon/Wed/Fri as a swipeable document (opening, card, one page per point, question), other days the picture, two-week
  test; opening line at most 140 characters (lint). Same visual style for now.
- App Reels (25 Oct 2026, item 5): the scheduled app Reels are story mode and already open in the scene (founder). The ~270 old
  "Hi, I'm Lumi/Mira" files are not scheduled and are not rewritten; arthvan-media engine/story_hook.py refuses to render any new
  story that opens with a greeting. mira-shaadi-mr (6 Nov) text fixed ('एकोणतीस'); its MP4 needs a re-render on the Mac.
- Reel link tips: up to 8 a month (founder, 24 Oct 2026: their Meta Verified plan allows 8; public pages list 2/4/6 by tier).
- Long videos run a thumbnail click test: B (same picture, the title's words) two days after going public; the higher click rate
  stays, A when the numbers are missing or too few (engine/thumbtest.py). (founder, 23 Oct 2026)
- Meta Verified (one month from 23 Oct 2026): Reel links are app-only and few, so engine/reeltip.py sends a daily Telegram tip naming
  the Reel taking off and the exact Play link to add (max 4 a month). Renew only if the Reel links bring installs. (founder, 24 Oct 2026)
- The weekly "what's working" report is report-only; nothing changes topics or posting on its own without the founder's yes.

## Reporting
- All times told to the founder are in **WAT (Lagos)**. (founder, 22 Oct 2026)
- The control room's live status refreshes on its own every 30 seconds. (founder, 22 Oct 2026)

## Priority (founder, 25 Oct 2026)
- The job is growing Reel and Short views. Do not propose new automation unless it directly serves reach; work on the Reels
  themselves (what viewers see and hear, topics, openings, distribution) and show it with numbers.
- Reel first seconds (founder, 25 Oct 2026, A + B): the first picture is the story's own striking object or moment, never a cast
  member with a phone (8 of 10 Learning with SG Shorts opened on Bhai with his phone) and never close to the last 5 Shorts' first
  picture (lint check_opener; a miss rewrites the same topic). The first 1.3 s are a moving close-up, then a cut to the full picture
  (storyframe PUNCH_S). C (founder, 25 Oct 2026, "go with C as shown"): Shorts run the picture from the title band to the foot of
  the screen (panels drawn 2:3, lower third kept calm), a soft shadow at the foot, captions big bold white with a black outline and
  numbers / the title keyword in yellow, the logo top right, evidence chips top left. Long videos keep the old layout.
- Shares and remakes (founder, 25 Oct 2026, "do 1 and 2"): every Short ends with a spoken SEND line naming who to send it to
  ("Yeh Papa ko bhejo, jo ..."), shown on the end card (lint check_send; Instagram's strongest signal for new viewers is DM sends,
  ours were 0-6 per Reel). Every Sunday each channel's Short is a fresh version of a past winner (top third of the month on
  Instagram, at least 800 views, at least 10 days old, each remade once; its own facts, new opening and picture). First: 1 Nov,
  US stocks for 1 dollar (1,451) and Ram Setu (1,565).
- Weak Reels (founder, 27 Oct 2026, "remake them"): no deleting or re-uploading (Instagram's repost rules). Mon-Sat, one Short a
  day (either channel, oldest first) is a fresh version of a Short under 1,000 Instagram views, settled 4 days, never remade and
  not itself a remake; it takes that channel's slot that day. First: 3 Nov Kailash, 4 Nov Meta AI, 5 Nov Kedarnath, 6 Nov
  Chakravyuh, 7 Nov SIP fees. The 1 Nov Ram Setu Sunday remake goes out as it is (founder).
- No Sunday winner remakes (founder, 27 Oct 2026, "dont do this"): replaces the Sunday part of "Shares and remakes" above. Sunday's
  Short is always a new topic. The two 1 Nov remakes (US stocks, Ram Setu) were already made and scheduled; weak-Reel second chances stay Mon-Sat.
- Thumbnails (founder, 27 Oct 2026, "yes fix for present, drafts, scheduled and future"): the big channels' layout. One dramatic,
  vivid sight (before/after split when the story is a change; no face close-up), the TOPIC NAME huge on a red banner, a number in a
  yellow tag and one shock word. SG-MYTH-WORLD in Devanagari, Learning with SG in Roman; a long's click test tries the other script
  on the same picture. Still one picture per video (no extra cost per Reel); redoing the 39 already made cost about ₹120 once.
  Posted Instagram Reels keep their cover (Meta's API cannot change it).
- App Reels every day again (founder, 28 Oct 2026, "better to go everyday"): replaces the 24-25 Oct Mon/Wed/Fri rule (item B); each
  still a Trial Reel, ScoreMyBiz and Waypoint alternating day by day as content/schedule.json already plans.
- Style test (founder, 28-29 Oct 2026, "upload now this sample", "keep both"): the 30 Oct gold Short as code-only motion graphics
  (Trial Reel DfDlOxPABYP, 29 Oct 00:11 WAT) and its painted version (30 Oct) both post; compared at 72 hours (1 Nov), then a
  one-week Learning with SG test after the 6 Nov review. SG-MYTH-WORLD stays painted.
- LinkedIn (founder, 29 Oct 2026, "yes do A"): the personal post goes out Mon/Wed/Fri only (Wednesday a document, Mon/Fri the
  picture); 23-29 Oct export: daily posts fell 333 -> 31 impressions a day, posts about the founder led (139/138) and general essays
  trailed (22-35). Next: posts start from the founder's own stories (he sends them); 10 minutes of replies and comments per post day.
- Reels like the top channels (founder, 30 Oct 2026, "yes do B C"; A, the founder on camera, declined): B: SG-MYTH-WORLD Shorts
  open on a real, credited Wikimedia Commons photo of the place when the script names it, then the drawn story; C: Learning with SG
  Shorts 35-45 s (85-125 words, 7-9 scenes) instead of 60-74 s, a one-week test. Both reach posts from about 6-7 Nov (7-day buffer).
- Fresh news (founder, 30 Oct 2026, "yes build 1-3"): (1) each morning (news workflow 08:47/09:47 WAT) Learning with SG makes a
  same-day news Short from that morning's household money news (synchronous writer, about $0.40 a day more) and swaps it into today's
  slot; the planned Short moves to the first free day after the buffer; if anything fails by 13:00 WAT the planned Short posts.
  (2) The buffer takes no dated headlines ("today", "outlook", dates); the daily market call is never a Short. (3) Money Reels post on
  Instagram at 18:30 India (14:00 WAT) instead of 14:00 India; YouTube stays at 20:00 India.
- Learning with SG growth engine (founder, 29 Oct 2026, master prompt + "do a b c d ... from today"): A: monthly ceilings raised to
  pictures Rs 8,000 and Claude $75. B: extra Reels beyond the daily one from today (engine/extra.py, own slots 13:00 / 16:30 / 22:45
  India), ramping to 3-4 a day while views per Reel hold. C: topics widen to jobs and workplace, management, psychology, AI,
  economy and numbers (jobs news scores like the wallet). D: Reels are India and global; Nigeria news goes to LinkedIn. Next: a
  research cycle every 4 hours with a Telegram report that makes the extra Reels by itself.
- Niches and trust (founder, 29 Oct 2026, "1 2 and 3"): (1) 55 evergreen Learning with SG topics (AI and jobs, money decisions,
  management, psychology of money, economy, numbers; no crypto, dark psychology, conspiracy or true crime) feed the 4-hourly research
  cycle on quiet days; (2) two Learning with SG Reels in a row never share a category; (3) the money channel names the voice:
  "Voice: Sanjeev Gulia, FCMA, IIM" on the end card, the YouTube description and the Instagram caption.
- Item 13 (Waypoint ban-appeal review) dropped: the Supabase connector can reach only one organisation (ScoreMyBiz).

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
  11 WhatsApp usernames.

## Open (not decided yet; ask, don't assume)
- WhatsApp spend after Meta's 1 Oct 2026 price change: not built. On 23 Oct ScoreMyBiz had sent 32 WhatsApp messages in 30 days,
  far under the 1,000 free a month; build the spend line when sends pass 500 a month.
- Waypoint crisis help (helplines from chats, comments, check-in; more languages; voice alert): founder said **no** on 23 Oct 2026.
  Waypoint PR #1 stays unmerged; do not merge or re-propose unless the founder asks.
- Google Play account (25 Oct 2026, founder): `play-reports-reader` now also has Reply to reviews and the Play Developer Reporting
  API (crash data) for both apps; still no release, price or listing rights. Checked 25 Oct: reviews read 200 (0 in the last
  7 days), crash metrics 200 for both apps. Replies go to the founder's Telegram first, like the YouTube replies.
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
- Voice: no change from before 29 Oct: the designed storyteller pool (content/voice.json), every line sent exactly as the batch sends it (no style note), and no "Voice: ..." credit anywhere, since it is not the founder's voice (founder, 29 Oct 2026; replaces the voice-credit part of niches item 3).
- News and extra Reels explain why it happened, the wider and AI impact, the consequences and the viewer's legal remedies (naming the law), 50-60 s, not basic advice (founder, 29 Oct 2026).
- The 9 pm card lists each extra Learning with SG Reel as its own row, and tomorrow's plan shows the extra slots (founder, 29 Oct 2026).
- Old basic Innodata layoff Reel (2026-10-29-sglearning-x1) taken down everywhere (YouTube, Instagram Reel and Story, Threads) once the deeper remake is live (founder, 29 Oct 2026).
- Gemini credit: the 9 pm card shows an estimated balance counted down from the newest top-up in content/gemini-credit.json and warns 3 days before it runs out; an empty balance sends the top-up alert, not a red research run; daily US market wraps are never picked (founder, 29 Oct 2026).
- Growth goal is YouTube income (YouTube Partner Program); route: long-video watch time, SG-MYTH-WORLD first, plus moving Instagram followers to YouTube. Free levers on: big-question topics, the day's Sensex/Nifty move never a topic, hooks, Collab outreach. The founder runs a Rs 6,000 two-week paid test; scale only on the rule in docs/growth-plan.md (founder, 30 Oct 2026).
- Every long video gets an automatic Instagram Story card ("Naya video ... Poora video YouTube par, link bio mein") once it is public; the founder keeps the YouTube link in the Instagram bio (API cannot add link stickers) (founder, 30 Oct 2026).
- Foreign elections may be covered only as neutral "FOREIGN ELECTION EXPLAINER" Reels on what they mean for India's economy (no sides, no religion, no Indian politics); the general no-politics rule stays (founder, 30 Oct 2026, Israel election Reel).
- "Top 10 in 60 seconds" news roundup is a Learning with SG format (TOP 10 ROUNDUP: 12 scenes, one line per item); first one 30 Oct 2026, made daily only if it performs (founder, 30 Oct 2026).
- Israel election Reel dropped (founder, 30 Oct 2026: not worth it as a limited, neutral Reel). Top 10 roundup never opens with a generic "aaj ki 10 khabrein / 60 second mein" line: it opens on the day's biggest fact. A failed or taken-down extra no longer uses up the research cycle's daily allowance (founder, 30 Oct 2026).
- Plain language rule: Learning with SG lines must make sense to a 15-year-old; money/tech jargon is rejected by the script check and said in everyday words. Topics widen to AI, tech, crypto, companies, commodities and world events that move money (party politics still out). News, extra and Top 10 Reels use free code-drawn news cards (no paid pictures); 3 breaking-news extras a day from 31 Oct; a daily Top 10 at 09:30 India from 1 Nov (founder, 30 Oct 2026).
- Google Ads watch, phase 1: uses the YouTube uploads' Google Cloud project; reports spend and cost per new subscriber daily, and only ever pauses (founder /pause, monthly cap, or > Rs 25 a subscriber after Rs 1,500); never raises or starts spend (founder, 30 Oct 2026).
- A chosen story's own checked brief counts as a reported source for the number check; the Top 10 may run 125-170 words (founder's Top 10, 31 Oct 2026).
- Google Ads account for the YouTube promotion test: 601-481-4549 (founder, 31 Oct 2026).
- The Rs 6,000 YouTube promotion test is launched by code (engine/adlaunch.py): one Demand Gen campaign per channel on its newest public long video, India, Hindi + English, Maximize clicks, Rs 3,000 over 14 days, clicks open the Subscribe prompt; Google validates first, then live (founder, 31 Oct 2026: "I want to automise step 3").
- Google Ads billing is postpaid: at most USD 50 a month in total, so Rs 4,000 of ad spend a month (plus 18% GST about Rs 4,720) and Rs 2,000 per channel for the 14-day test; the watch pauses at Rs 4,000 (founder, 31 Oct 2026).
- Long-video pictures are painted wide (21:9, faces in the middle band) so nothing is cut between the title and caption bands; the half-price picture batch and each scene send the identical request, so pictures are never paid twice (founder noticed the cut-off FD video, 31 Oct 2026).
- No Anthropic API credit warning on the 9 pm card: the founder tops up when the credit-out alert comes; the 7-8 day buffer keeps posting meanwhile. The USD 100 "promotional" Anthropic credit came with the Max plan (9 Oct) and expires 12 Nov; the founder's own purchased balance is separate (founder, 31 Oct 2026).
- Google Ads account 601-481-4549 is in USD: every ads limit lives in content/ads.json "limits" per currency (USD: $21 per channel for the 14-day test = $1.50 a day, $42 monthly cap, so with tax about $50); the launcher and the watch read the account currency first and refuse/pause when no limit exists for it (31 Oct 2026: a rupee 143 was read as $143 a day; caught while ads were under review, nothing spent).
- Claude Sonnet 5.5 (half Opus's price) writes only the FIRST draft of Learning with SG extras, news Reels and the Top 10; any draft that fails a check, every patch, and all daily Shorts, longs and SG-MYTH-WORLD stay on Opus 5.5, with the same number, jargon, length and hook checks for both (founder, 31 Oct 2026: "use sonnet for extras and news, quality should not deteriorate").
- Resume both "SG test" ads campaigns once their budgets are within the limit ($5 a day, see next line); the resume step turns on only a campaign already within the limit (founder, 31 Oct 2026: "resume both campaigns with revised limits").
- Ads cap raised to USD 140 for the 14-day test: Google's Demand Gen minimum is $5 a day per campaign, so both channels run at $5 a day ($70 each); the watch pauses at $140 a month, or once $30 is spent if a new subscriber costs over $0.30 (founder, 31 Oct 2026: chose "Raise the cap" over one channel only).
- Ads show only on YouTube (home feed, Shorts, before videos), never Gmail, Discover or partner websites; set on both test campaigns and on every new launch (founder, 31 Oct 2026: "switch both to YouTube only").
- Each test ad carries extra videos besides the original: by default its channel's 2 best-watched public long videos (last 90 days, 20+ views), or the founder's pick in content/ads.json ad_videos (31 Oct: by topic, views too thin; CIMA exam video kept out); same $5 a day per campaign, Google moves it to the best video; trim losers around day 5 (founder, 31 Oct 2026: "add 2 best videos to each campaign today").
