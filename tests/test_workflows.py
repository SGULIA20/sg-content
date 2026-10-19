import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
KNOWN = {"ANTHROPIC_API_KEY", "GEMINI_API_KEY", "YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_SGLEARNING_REFRESH_TOKEN", "YT_ARTHVAN_REFRESH_TOKEN",
         "IG_ACCESS_TOKEN", "IG_USER_ID", "THREADS_ACCESS_TOKEN", "THREADS_USER_ID", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "GITHUB_TOKEN", "ACTIONS_PAT"}


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
    assert "0 2 * * *" in crons and "0 3 * * *" in crons
    job = data["jobs"]["produce"]
    assert job["timeout-minutes"] == 120 and data["concurrency"]["group"] == "produce"
    steps = " ".join(s.get("run", "") for s in job["steps"])
    assert "python -m pytest -q -m \"not slow\"" in steps and "python -m engine.produce" in steps and "prune_out.py" in steps


def test_publish_crons_match_slots():
    data = yaml.safe_load((ROOT / ".github" / "workflows" / "publish.yml").read_text())
    crons = [s["cron"] for s in (data.get(True) or data.get("on"))["schedule"]]
    assert "30 7 * * *" in crons and "0 16 * * 1,3,5" in crons


def test_docs_secrets_lists_every_secret():
    doc = (ROOT / "docs" / "secrets.md").read_text()
    for name in KNOWN - {"GITHUB_TOKEN"}:
        assert name in doc, name
