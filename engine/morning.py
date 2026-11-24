"""The morning maintenance agent (founder, 24 Nov 2026: "Build the maintenance agent next"; part of the December test). Every morning
it reads what happened in the last day and tells the founder, in plain words on Telegram, what failed, why, what needs him, and the fix
it would make. It runs on the API credit, not in a Claude session, so the daily checking no longer depends on anyone being awake.

It gathers the evidence itself, with no model involved: failed workflow runs in both repositories and the end of each failed log; pieces
that failed, were turned down or are short of a clip close to their day; what the finished-video review said; whether real music was
used; the month's API spend. Claude then reads only that evidence and writes the report. REPORT ONLY: it changes nothing, pushes
nothing and posts nothing but the one Telegram message. A quiet day is one line.

python -m engine.morning [--dry]
"""
import json
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import pieces, secrets
from .config import CHANNELS, ROOT

MODEL = "claude-opus-5-5"
REPOS = ("SGULIA20/sg-content", "SGULIA20/arthvan-media")
HOURS = 26                              # a little over a day, so a run that fires late misses nothing
LOG_TAIL = 2500                         # characters kept from the end of a failed job's log
MAX_FAILED = 8
CREDIT_USD = 100.0                      # the monthly API credit of the plan
API = "https://api.github.com/repos/{repo}"
PROMPT = """You are the morning maintenance check for a one-person video business. The owner is not a programmer. Below is the evidence
gathered automatically from the last {hours} hours: failed automation runs with the end of their logs, the state of the videos due in
the next days, and the month's spend. Today is {today}; give every time in WAT (Lagos, UTC+1).

Write the Telegram message he reads with his morning tea:
- First line: either "✅ All clear" with one short reason, or "⚠️ <n> thing(s) need attention".
- Then one short block per real problem, most urgent first: what happened in plain words (name the video by date and channel, not by
  file or function), the likely cause read from the log, what it affects (which video, which day), and "Fix:" one line saying what
  should be done and who does it (him, or Claude in the next session).
- Then "Needs you today:" only if something truly waits on him (a clip to record, a thumbnail, a yes), each with its deadline.
- Last line: API spend this month against the ${credit:.0f} credit.

Rules: only what the evidence shows; if a log does not show the cause, say the cause is not known yet. A run that failed and then
succeeded on a later try is not a problem: leave it out. No code, no file paths, no jargon, no advice beyond the evidence. At most
1,500 characters. If nothing is wrong, three lines are enough.

EVIDENCE
{evidence}"""


def _get(url: str, token: str = "", accept: str = "application/vnd.github+json") -> bytes:
    headers = {"Accept": accept, "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "sg-content-morning"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60, context=secrets.ssl_context()) as r:
        return r.read()


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def _get_log(url: str, token: str = "") -> bytes:
    """A job's log. GitHub answers with a redirect to a storage address that refuses the request when the GitHub token is sent along
    (24 Nov 2026: the first report said "the log could not be read from here" for every failure). The address is asked for with the
    token, then fetched without it."""
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                                               "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "sg-content-morning"})
    opener = urllib.request.build_opener(_NoRedirect, urllib.request.HTTPSHandler(context=secrets.ssl_context()))
    try:
        with opener.open(req, timeout=60) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        where = e.headers.get("Location") if e.code in (301, 302, 303, 307, 308) else None
        if not where:
            raise
    with urllib.request.urlopen(urllib.request.Request(where, headers={"User-Agent": "sg-content-morning"}), timeout=90, context=secrets.ssl_context()) as r:
        return r.read()


def failed_runs(repo: str, since: datetime, token: str = "", get=_get, get_log=None) -> list:
    """Workflow runs that failed since `since` and were not followed by a later success of the same workflow, each with the end of its
    failed job's log where the token may read it (this repository's own runs)."""
    try:
        body = json.loads(get(API.format(repo=repo) + f"/actions/runs?per_page=100&created=%3E{since.strftime('%Y-%m-%dT%H:%M:%SZ')}", token))
    except Exception as e:
        return [{"repo": repo, "error": f"runs not readable ({type(e).__name__}: {secrets.scrub(str(e))[:100]})"}]
    runs = body.get("workflow_runs") or []
    healed = {}                                                       # workflow -> time of its latest success
    for r in runs:
        if r.get("conclusion") == "success":
            healed[r["name"]] = max(healed.get(r["name"], ""), r.get("created_at", ""))
    out, seen = [], {}
    for r in runs:                                                    # newest first, as GitHub lists them
        if r.get("conclusion") not in ("failure", "timed_out", "startup_failure"):
            continue
        if r["name"] in seen:                                         # the same workflow failing again: counted, its log read once
            seen[r["name"]]["times"] += 1
            continue
        row = {"repo": repo.split("/")[1], "workflow": r["name"], "at": r.get("created_at"), "result": r["conclusion"], "times": 1,
               "later_success": healed.get(r["name"], "") > r.get("created_at", "")}
        if not row["later_success"] and len(out) < MAX_FAILED:
            row["log_end"] = _log_end(repo, r["id"], token, get, get_log)
        seen[r["name"]] = row
        out.append(row)
    return out


def _log_end(repo: str, run_id: int, token: str, get, get_log=None) -> str:
    try:
        jobs = json.loads(get(API.format(repo=repo) + f"/actions/runs/{run_id}/jobs", token)).get("jobs") or []
        bad = next((j for j in jobs if j.get("conclusion") == "failure"), None)
        if not bad:
            return ""
        step = next((s["name"] for s in bad.get("steps") or [] if s.get("conclusion") == "failure"), "")
        try:
            url = API.format(repo=repo) + f"/actions/jobs/{bad['id']}/logs"
            text = (get_log(url, token) if get_log else _get_log(url, token) if get is _get else get(url, token)).decode(errors="replace")
        except Exception:
            return f"failed step: {step} (log not readable from here)"
        marks = [l[29:] if len(l) > 29 and l[4] == "-" else l for l in text.splitlines() if "FAILED " in l or "Error" in l or "Traceback" in l][-12:]
        return f"failed step: {step}\n" + secrets.scrub("\n".join(marks)[:1200] + "\n...\n" + text[-LOG_TAIL:])
    except Exception as e:
        return f"(log not readable: {type(e).__name__})"


def piece_state(root: Path, today: date, days: int = 4) -> list:
    """One row per piece due from yesterday to `days` ahead, and any piece in a failed state: what the report needs to judge them."""
    rows = []
    for p in pieces.list_all(root):
        if not p.publish_day:
            continue
        gap = (p.publish_day - today).days
        failed = p.status.startswith("failed") or p.status == "qa_failed"
        if not (-1 <= gap <= days or failed and gap >= -3):
            continue
        ids = p.ids or {}
        row = {"video": f"{p.publish_day:%d %b} {CHANNELS[p.channel].display_name} {'Short' if p.kind == 'short' else 'long'}", "days_away": gap,
               "status": p.status, "title": str((p.script or {}).get("title") or (p.topic or {}).get("title") or "")[:70]}
        if p.reasons and p.status not in ("uploaded", "posted"):       # a finished piece's old reasons are history, not news
            row["last_reason"] = str(p.reasons[-1])[:200]
        if ids.get("intro_rejected"):
            row["clip_turned_down"] = str(ids.get("intro_rejected_why", ""))[:200]
        if p.status == "intro-wait":
            row["waiting_for"] = "his clip" + ("" if ids.get("intro_sent") else " (not asked yet)")
        if ids.get("watch"):
            row["review"] = ids["watch"]
        if ids.get("sound"):
            row["sound"] = ids["sound"]
        rows.append(row)
    return sorted(rows, key=lambda r: r["days_away"])


def spend(root: Path, today: date) -> dict:
    try:
        data = json.loads((Path(root) / "logs" / "claude-spend.json").read_text())
    except (OSError, ValueError):
        return {}
    month = today.strftime("%Y-%m")
    return {"month_usd": round(sum(v.get("usd", 0) for k, v in data.items() if k.startswith(month)), 2),
            "yesterday_usd": round(data.get((today - timedelta(days=1)).isoformat(), {}).get("usd", 0), 2), "credit_usd": CREDIT_USD}


def evidence(root: Path = ROOT, now: datetime | None = None, token: str = "", get=_get) -> dict:
    now = now or datetime.now(timezone.utc)
    since = now - timedelta(hours=HOURS)
    runs = [r for repo in REPOS for r in failed_runs(repo, since, token, get)]
    return {"failed_runs": runs, "videos": piece_state(root, now.date()), "api_spend": spend(root, now.date()),
            "note": "sg-content failures carry the end of their log; arthvan-media logs cannot be read from this job."}


def _ask(prompt: str) -> str:
    import anthropic
    client = anthropic.Anthropic(api_key=secrets.get("ANTHROPIC_API_KEY"))
    r = client.messages.create(model=MODEL, max_tokens=8000, messages=[{"role": "user", "content": prompt}])
    try:
        from . import writer
        writer.record_spend(r.usage, writer.SPEND_FILE, None)
    except Exception:
        pass
    return "".join(getattr(b, "text", "") for b in r.content).strip()


def plain(ev: dict) -> str:
    """The report without a model: used when Claude cannot be reached, so a broken key never hides a broken night."""
    bad = [r for r in ev["failed_runs"] if not r.get("later_success") and not r.get("error")]
    stuck = [v for v in ev["videos"] if v["status"].startswith("failed") or v["status"] == "qa_failed" or v.get("clip_turned_down")]
    if not bad and not stuck:
        return "✅ All clear: no failed runs and no stuck videos in the last day. (Written without Claude: the report writer could not be reached.)"
    lines = [f"⚠️ {len(bad) + len(stuck)} thing(s) need attention (written without Claude: the report writer could not be reached)"]
    lines += [f"• {r['repo']}: {r['workflow']} failed at {r['at']}" for r in bad[:6]]
    lines += [f"• {v['video']}: {v['status']} {v.get('clip_turned_down') or v.get('last_reason') or ''}"[:220] for v in stuck[:6]]
    return "\n".join(lines)


def run(root: Path = ROOT, now: datetime | None = None, env=None, ask=_ask, notify=None, get=_get, dry: bool = False) -> str:
    import os
    env = os.environ if env is None else env
    now = now or datetime.now(timezone.utc)
    ev = evidence(root, now, env.get("GITHUB_TOKEN", ""), get)
    try:
        text = ask(PROMPT.format(hours=HOURS, today=f"{now:%A %d %B %Y}", credit=CREDIT_USD, evidence=json.dumps(ev, indent=1, ensure_ascii=False, default=str)[:60000]))
        if not text:
            raise ValueError("empty report")
    except Exception as e:
        print(f"morning: Claude did not write the report ({type(e).__name__}: {secrets.scrub(str(e))[:120]})", flush=True)
        text = plain(ev)
    text = "🌅 Morning check\n" + text[:3600]
    if not dry:
        if notify is None:
            from . import telegram
            notify = telegram.send
        notify(text)
    return text


def main(argv=None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    print(run(dry="--dry" in args))
    return 0


if __name__ == "__main__":
    sys.exit(main())
