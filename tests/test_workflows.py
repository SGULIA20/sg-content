import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
KNOWN = {"ADS_REFRESH_TOKEN", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_SGLEARNING_REFRESH_TOKEN", "YT_ARTHVAN_REFRESH_TOKEN",
         "IG_ACCESS_TOKEN", "IG_USER_ID", "THREADS_ACCESS_TOKEN", "THREADS_USER_ID", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "GITHUB_TOKEN", "ACTIONS_PAT",
         "SG_COMMAND_KEY", "LINKEDIN_ACCESS_TOKEN", "LINKEDIN_PERSON_URN", "LINKEDIN_CLIENT_ID", "LINKEDIN_CLIENT_SECRET"}


def _workflows():
    files = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
    assert {f.name for f in files} >= {"produce.yml", "publish.yml", "weekly-report.yml", "refresh-tokens.yml", "tests.yml"}
    return files


def test_workflows_parse_and_name_only_known_secrets():
    for f in _workflows():
        text = f.read_text()
        data = yaml.safe_load(text)
        assert "jobs" in data, f.name
        used = set(re.findall(r"\$\{\{\s*secrets\.([A-Z_]+)\s*\}\}", text))
        assert used <= KNOWN, f"{f.name} uses unknown secrets {used - KNOWN}"


def test_produce_schedule_and_guards():
    data = yaml.safe_load((ROOT / ".github" / "workflows" / "produce.yml").read_text())
    crons = [s["cron"] for s in data[True]["schedule"]] if True in data else [s["cron"] for s in data["on"]["schedule"]]
    assert "13 7 * * *" in crons and "43 7 * * *" in crons and "13 9 * * *" in crons     # several chances after the 07:00 UTC quota reset
    job = data["jobs"]["produce"]
    assert job["timeout-minutes"] == 300 and data["concurrency"]["group"] == "produce"
    steps = " ".join(s.get("run", "") for s in job["steps"])
    assert "python -m pytest -q -m \"not slow\"" in steps and "python -m engine.produce" in steps and "prune_out.py" in steps


def test_publish_crons_match_slots():
    data = yaml.safe_load((ROOT / ".github" / "workflows" / "publish.yml").read_text())
    crons = [s["cron"] for s in (data.get(True) or data.get("on"))["schedule"]]
    assert "3 13 * * *" in crons and "3 14 * * *" in crons and "3 16 * * *" in crons and "3 17 * * *" in crons      # 18:30 / 21:30 India
    pick = next(s["run"] for s in data["jobs"]["publish"]["steps"] if s.get("id") == "slot")
    assert '"3 13 * * *"' in pick and '"3 14 * * *"' in pick and '"33 14 * * *"' in pick        # every finance slot maps to sglearning


def test_docs_secrets_lists_every_secret():
    doc = (ROOT / "docs" / "secrets.md").read_text()
    for name in KNOWN - {"GITHUB_TOKEN"}:
        assert name in doc, name


def test_produce_commit_step_always_runs_and_syncs_through_gitsync():
    text = (ROOT / ".github" / "workflows" / "produce.yml").read_text()
    data = yaml.safe_load(text)
    steps = data["jobs"]["produce"]["steps"]
    commit = next(s for s in steps if "Commit" in s.get("name", ""))
    assert commit.get("if") == "always()"
    assert "engine.gitsync" in commit["run"] and "git pull --rebase" not in commit["run"]        # one sync path that never leaves a stuck rebase (24 Oct 2026)
    assert any("actions/cache" in s.get("uses", "") for s in steps)


def test_gitignore_keeps_published_short_files():
    ignore = (ROOT / ".gitignore").read_text().splitlines()
    assert "out/" not in ignore and "out/**/vo/" in ignore and "out/**/scene*.mp4" in ignore and "out/**/long.mp4" in ignore
    assert "assets/avatar/.cache/" in ignore


def test_publish_picks_channel_from_schedule_not_clock():
    text = (ROOT / ".github" / "workflows" / "publish.yml").read_text()
    assert "github.event.schedule" in text and "date -u +%H" not in text
    assert yaml.safe_load(text)["jobs"]["publish"]["timeout-minutes"] >= 60
    commit = next(s for s in yaml.safe_load(text)["jobs"]["publish"]["steps"] if "Commit" in s.get("name", ""))
    assert commit.get("if") == "always()" and "engine.gitsync" in commit["run"] and "pieces logs" in commit["run"]


def test_gitsync_records_out_sha_after_commit(tmp_path):
    import subprocess
    from datetime import date
    from engine import gitsync, pieces
    subprocess.run(["git", "init", "-q", "-b", "main", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "t"], check=True)
    p = pieces.Piece(id="2026-10-20-sglearning-short", channel="sglearning", kind="short", publish_day=date(2026, 10, 20))
    p.status = "uploaded"; p.ids = {"yt_id": "y"}; pieces.save(p, tmp_path)
    (tmp_path / "out" / p.id).mkdir(parents=True); (tmp_path / "out" / p.id / "reel.mp4").write_bytes(b"mp4")
    sha = gitsync.commit(tmp_path, "test", push=False)
    assert sha and pieces.load(p.id, tmp_path).ids["out_sha"] == sha
    assert gitsync.commit(tmp_path, "again", push=False) == ""                # the sha record was committed inside the first call; nothing left dirty
    assert subprocess.run(["git", "-C", str(tmp_path), "status", "--porcelain"], capture_output=True, text=True).stdout == ""


def test_gitsync_enabled_by_either_flag():
    from engine import gitsync
    assert gitsync.enabled({"SG_PUSH_FROM_MAC": "1"}) and gitsync.enabled({"SG_COMMIT_EACH": "1"}) and gitsync.enabled({"GITHUB_ACTIONS": "true"})
    assert not gitsync.enabled({})


def test_evening_scorecard_is_sent_before_seven_pm_lagos():
    data = yaml.safe_load((ROOT / ".github" / "workflows" / "evening.yml").read_text())
    crons = [s["cron"] for s in (data.get(True) or data.get("on"))["schedule"]]
    assert crons == ["3 20 * * *", "23 20 * * *"]                                     # 21:03 and 21:23 WAT (founder, 22 Oct 2026: 9 pm)
    assert "engine.evening --send" in " ".join(s.get("run", "") for s in data["jobs"]["evening"]["steps"])


def test_growth_report_runs_weekly_on_monday_morning_lagos():
    data = yaml.safe_load((ROOT / ".github" / "workflows" / "growth.yml").read_text())
    crons = [s["cron"] for s in (data.get(True) or data.get("on"))["schedule"]]
    assert crons == ["13 8 * * 1", "43 9 * * 1"]
    assert "engine.playreports --weekly --send" in " ".join(s.get("run", "") for s in data["jobs"]["growth"]["steps"])
