# Founder decisions (read before asking)

Settled decisions. A session that is unsure about one of these follows this file instead of asking again.
Newest first; each line says who decided and when.

## Operating rules
- **Fully automatic.** The founder never decides what is made or posted on a given day. Topics, scripts, voice, video, upload and posting run on their own; a piece that fails a check is skipped and retried by the next run, never posted. (founder, 21 Oct 2026)
- **Buffer: never under 4 days, aim for 5+.** The buffer targets 7 days of Shorts and 10 of longs (`engine/buffer.py`); under 4 days is an alert (`digest.BUFFER_ALERT_DAYS`). (founder, 21 Oct 2026)
- **One failure never stops the rest.** A crash in one piece marks that piece `failed-crash` and the run carries on (`engine/produce.py`). (21 Oct 2026, after the long-video crash)
- **No duplicates.** A piece is made once per publish slot (`pieces/<day>-<channel>-<kind>.json`); finished pieces are never remade; each platform is posted once per piece (its id is stored before the next platform is tried).
- Claude writes every script; Gemini is only the fallback, and a fallback is recorded on the piece. (founder, 20 Oct 2026)

## Control room (phone)
- Private claude.ai page plus Telegram as the fallback; buttons for pause, resume, stop, retry, run now, post now, and typed instructions that become one of those actions after a confirm. (founder, 21 Oct 2026)
- Commands and status live in a walled-off `command` schema inside the ScoreMyBiz Supabase project (free plan, 2-project limit), never in this public repo. (founder, 21 Oct 2026)

## Scope
- Channels: Learning with SG (`sglearning`) and SG-MYTH-WORLD (`arthvan`) on YouTube, Instagram Reels and Stories, Threads.
- **LinkedIn:** the founder's personal profile; each Short becomes a native video with a short post. (founder, 21 Oct 2026; replaces "out of scope" in spec §10)
- **ScoreMyBiz and Waypoint** join the control room: business numbers, social promotion of both, and controls for them. (founder, 21 Oct 2026)
