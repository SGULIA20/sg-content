# Secrets for sg-content

Local: `~/sg-content/.env`, one `NAME=value` per line (git-ignored). Cloud: GitHub Actions secrets with the same names:

```
gh secret set NAME --repo SGULIA20/sg-content < file-with-the-value
```

| Name | Where it comes from | Used by |
|---|---|---|
| `ANTHROPIC_API_KEY` | console.anthropic.com → API Keys (key named sg-content) | produce (script writer) |
| `GEMINI_API_KEY` | aistudio.google.com → API key in the **sg-content** Google project (own voice quota) | produce (research, voice, pictures) |
| `YT_CLIENT_ID`, `YT_CLIENT_SECRET` | the Google Cloud OAuth client already used by arthvan-media | produce (upload), weekly report |
| `YT_SGLEARNING_REFRESH_TOKEN` | OAuth refresh token for Learning with SG (same value as arthvan-media) | produce, report |
| `YT_ARTHVAN_REFRESH_TOKEN` | OAuth refresh token for SG-MYTH-WORLD (same value as arthvan-media) | produce, report |
| `ADS_REFRESH_TOKEN` | `python3 scripts/yt_authorize.py ads` (Google Ads permission on the same OAuth client; sign in with the Ads account's owner) | ads watch |
| `IG_ACCESS_TOKEN`, `IG_USER_ID` | Instagram Graph long-lived token and the IG user id for sanjeev_gulia (same as arthvan-media) | publish, report, refresh |
| `THREADS_ACCESS_TOKEN`, `THREADS_USER_ID` | Threads API token and user id (same as arthvan-media) | publish, refresh |
| `LINKEDIN_CLIENT_ID`, `LINKEDIN_CLIENT_SECRET` (optional, local only) | linkedin.com/developers → the sg-content app → Auth tab; products "Sign In with LinkedIn using OpenID Connect" and "Share on LinkedIn"; redirect URL `http://localhost:8765/callback` | `python -m engine.linkedin --auth` on the Mac (not a GitHub secret) |
| `LINKEDIN_ACCESS_TOKEN`, `LINKEDIN_PERSON_URN` (optional) | printed by `python -m engine.linkedin --auth`; the token lasts 60 days and is not refreshed automatically, so re-run `--auth` when the digest warns (7 days ahead, from `logs/tokens.json`) | publish (LinkedIn is skipped when these are absent) |
| `TELEGRAM_BOT_TOKEN` | @BotFather token for @Sglearningcontent_bot (this project's own bot) | every workflow |
| `TELEGRAM_CHAT_ID` | `python -m engine.telegram --find-chat` after messaging the bot once | every workflow |
| `ACTIONS_PAT` (optional) | a fine-grained GitHub token with "Secrets: write" on this repo; lets refresh-tokens rotate the Instagram/Threads secrets itself | refresh-tokens |
| `SG_COMMAND_KEY` (optional) | Supabase (ScoreMyBiz project) → Project Settings → Vault → `sg_command_ingest`; lets runs report to the founder's control page and obey its pause button | produce, publish |

Rules: never commit `.env`; never paste a value into a piece, a log or a Telegram message (the engine scrubs known values); when a token is rotated, update the GitHub secret the same day.
