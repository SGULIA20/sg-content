# Founder decisions (read before asking)

Settled decisions for ALL of the founder's work: sg-content, arthvan-media, ScoreMyBiz, Waypoint. Every Claude session (Mac, VS Code,
phone, cloud) reads this file first and follows it instead of asking again. When the founder settles something new, the session adds one
line here (who, date) in the same change. Newest first.

## Recent changes and why (newest first)
- 23 Oct 2026: one picture style per brand (see "Picture style"); only the pictures change. Founder, after comparing nine styles.
- 23 Oct 2026: GitHub skipped every morning job; the LinkedIn post and the Learning with SG post were started by hand. Fix waiting on the
  founder: `GITHUB_TOKEN` in Supabase so the database starts each job at its exact minute (docs/external-scheduler.md).
- 22 Oct 2026: LinkedIn gets picture posts only (sg-content b67bc3e, arthvan-media 0e1d13f); no app posts on LinkedIn (arthvan-media 75b3a12).
- 21-22 Oct 2026: control room (claude.ai page + Telegram buttons) on branch `command-center`, PR #1, waiting on the `SG_COMMAND_KEY` secret.

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
- **Fully automatic.** The founder never decides what is made or posted on a given day. Topics, scripts, voice, video, upload and posting run on their own; a piece that fails a check is skipped and retried by the next run, never posted. (founder, 21 Oct 2026)
- **Buffer: never under 4 days, aim for 5+.** The buffer targets 7 days of Shorts and 10 of longs (`engine/buffer.py`); under 4 days is an alert (`digest.BUFFER_ALERT_DAYS`). (founder, 21 Oct 2026)
- **One failure never stops the rest.** A crash in one piece marks that piece `failed-crash` and the run carries on (`engine/produce.py`). (21 Oct 2026, after the long-video crash)
- **Instagram Story only when the Short fits in 60 s.** A longer Reel keeps its full length and that day has no Story; a Story is never
  trimmed. (founder, 22 Oct 2026)
- **Never early.** A Short goes out at its slot (at most an hour early), even when a GitHub run is late. (23 Oct 2026, after a late run
  posted the next day's Short 20 hours early)
- **No duplicates.** A piece is made once per publish slot (`pieces/<day>-<channel>-<kind>.json`); finished pieces are never remade; each platform is posted once per piece (its id is stored before the next platform is tried).
- Claude writes every script; Gemini is only the fallback, and a fallback is recorded on the piece. (founder, 20 Oct 2026)

## Reporting
- All times told to the founder are in **WAT (Lagos)**. (founder, 22 Oct 2026)
- The control room's live status refreshes on its own every 30 seconds. (founder, 22 Oct 2026)

## Open (not decided yet; ask, don't assume)
- WhatsApp spend after Meta's 1 Oct 2026 price change: not built. On 23 Oct ScoreMyBiz had sent 32 WhatsApp messages in 30 days,
  far under the 1,000 free a month; build the spend line when sends pass 500 a month.
- Waypoint crisis help (helplines from chats, comments, check-in; more languages; voice alert): founder said **no** on 23 Oct 2026.
  Waypoint PR #1 stays unmerged; do not merge or re-propose unless the founder asks.
- Google Play service account (review replies, crash watch): later, founder's call (23 Oct 2026).
- Exact clock: built and running in Supabase (command.clock); it starts jobs once `GITHUB_TOKEN` is added to the sg-command function.

## Control room (phone)
- Private claude.ai page plus Telegram as the fallback; buttons for pause, resume, stop, retry, run now, post now, and typed instructions that become one of those actions after a confirm. (founder, 21 Oct 2026)
- Commands and status live in a walled-off `command` schema inside the ScoreMyBiz Supabase project (free plan, 2-project limit), never in this public repo. (founder, 21 Oct 2026)

## Scope
- Channels: Learning with SG (`sglearning`) and SG-MYTH-WORLD (`arthvan`) on YouTube, Instagram Reels and Stories, Threads.
- **LinkedIn:** the founder's personal profile, **picture posts only**, one a day from arthvan-media `linkedin-personal`; no Short or Reel video and no app posts go to LinkedIn. (founder, 22 Oct 2026; replaces the 21 Oct "each Short as a native video")
- **ScoreMyBiz and Waypoint** join the control room: business numbers, social promotion of both, and controls for them. (founder, 21 Oct 2026)
