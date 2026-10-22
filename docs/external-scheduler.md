# A clock that does not depend on GitHub or the Mac

GitHub's cron fires late or not at all on busy days (22 Oct 2026: none of the day's content runs started on their own). The Mac
now presses the Run buttons (`scripts/install_triggers.sh`), but only while it is on. A free outside scheduler such as
cron-job.org removes that dependency: it calls GitHub's API at the exact minute and the run starts within seconds.

## One-time setup (about 15 minutes, needs your GitHub login)

1. GitHub → Settings → Developer settings → Fine-grained personal access tokens → Generate. Repository access: `sg-content`
   and `arthvan-media`. Permissions: **Actions: Read and write**. Expiry: 1 year. Copy the token once; it is never stored in a repo.
2. cron-job.org → create a free account → for every row below, **Create cronjob**:
   - URL: `https://api.github.com/repos/SGULIA20/<repo>/actions/workflows/<workflow>/dispatches`
   - Method: POST
   - Headers: `Authorization: Bearer <token>`, `Accept: application/vnd.github+json`, `Content-Type: application/json`
   - Body: `{"ref":"main"}` or, where inputs are given, `{"ref":"main","inputs":{...}}`
   - Schedule: the time below (set the account time zone to Africa/Lagos).

| Lagos time | Repo | Workflow | Body |
|---|---|---|---|
| 04:40 | arthvan-media | linkedin-personal.yml | `{"ref":"main","inputs":{"mode":"post"}}` |
| 08:15, 14:45 | sg-content | produce.yml | `{"ref":"main"}` |
| 09:35 | sg-content | publish.yml | `{"ref":"main","inputs":{"channel":"sglearning"}}` |
| 15:40 | arthvan-media | daily-post.yml | `{"ref":"main","inputs":{"mode":"post"}}` |
| 17:05 | sg-content | publish.yml | `{"ref":"main","inputs":{"channel":"arthvan"}}` |
| 21:05 | sg-content | evening.yml | `{"ref":"main"}` |
| 21:30 | arthvan-media | status.yml | `{"ref":"main"}` |
| every 15 min | arthvan-media | telegram-commands.yml | `{"ref":"main"}` |

Every engine refuses to post or upload the same piece twice, so a run started by cron-job.org, by the Mac and by GitHub on the
same day does one job once.
