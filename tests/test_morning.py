import json
from datetime import date, datetime, timezone

from engine import morning, pieces

NOW = datetime(2026, 12, 2, 5, 47, tzinfo=timezone.utc)


def _get(url, token="", accept=""):
    if "/actions/runs?" in url:
        if "arthvan-media" in url:
            return json.dumps({"workflow_runs": []}).encode()
        return json.dumps({"workflow_runs": [
            {"id": 1, "name": "produce", "conclusion": "failure", "created_at": "2026-12-01T20:00:00Z"},
            {"id": 2, "name": "studio", "conclusion": "failure", "created_at": "2026-12-01T21:00:00Z"},
            {"id": 3, "name": "studio", "conclusion": "success", "created_at": "2026-12-01T21:05:00Z"}]}).encode()
    if url.endswith("/actions/runs/1/jobs"):
        return json.dumps({"jobs": [{"id": 11, "conclusion": "failure", "steps": [{"name": "Make the day's pieces", "conclusion": "failure"}]}]}).encode()
    if url.endswith("/actions/jobs/11/logs"):
        return ("x" * 5000 + "music: 'Hitman' not downloaded (URLError)\nTraceback ... KeyError: 'title'").encode()
    raise AssertionError(url)


def _piece(root, pid, status, **ids):
    ch, kind = pid.split("-")[3], pid.split("-")[4]
    p = pieces.Piece(id=pid, channel=ch, kind=kind, publish_day=date.fromisoformat(pid[:10])); p.status = status
    p.script = {"title": "Trojan Horse sach tha?", "scenes": []}; p.ids.update(ids); pieces.save(p, root)


def test_the_evidence_holds_the_failures_that_did_not_heal_the_stuck_videos_and_the_spend(tmp_path):
    """Founder, 24 Nov 2026: 'Build the maintenance agent next'."""
    _piece(tmp_path, "2026-12-03-arthvan-short", "intro-wait", intro_rejected="abc", intro_rejected_why="missing words (only 30% heard)", intro_sent="x")
    _piece(tmp_path, "2026-12-02-sglearning-short", "uploaded", watch={"opening": 5, "verdict": "fix", "issues": 2, "best_change": "open on the train"}, sound="track")
    _piece(tmp_path, "2026-12-20-arthvan-long", "uploaded")                                       # far off and fine: not in the report
    (tmp_path / "logs").mkdir(exist_ok=True)
    (tmp_path / "logs" / "claude-spend.json").write_text(json.dumps({"2026-12-01": {"usd": 1.5, "requests": 9}, "2026-11-30": {"usd": 9.0, "requests": 2}}))
    ev = morning.evidence(tmp_path, NOW, "tok", _get)
    runs = {(r["workflow"], r["later_success"]) for r in ev["failed_runs"]}
    assert runs == {("produce", False), ("studio", True)}
    produce = next(r for r in ev["failed_runs"] if r["workflow"] == "produce")
    assert "failed step: Make the day's pieces" in produce["log_end"] and "KeyError" in produce["log_end"] and len(produce["log_end"]) < 2700
    videos = {v["video"]: v for v in ev["videos"]}
    assert len(videos) == 2 and "missing words" in videos["03 Dec SG-MYTH-WORLD Short"]["clip_turned_down"]
    assert videos["02 Dec Learning with SG Short"]["review"]["verdict"] == "fix"
    assert ev["api_spend"] == {"month_usd": 1.5, "yesterday_usd": 1.5, "credit_usd": 100.0}


def test_the_report_goes_to_telegram_and_a_dead_writer_still_reports_the_failures(tmp_path):
    _piece(tmp_path, "2026-12-03-arthvan-short", "failed-voice")
    sent, asked = [], []
    text = morning.run(tmp_path, NOW, {"GITHUB_TOKEN": "t"}, ask=lambda p: asked.append(p) or "⚠️ 1 thing needs attention\nThe 3 Dec Short has no voice.", notify=sent.append, get=_get)
    assert sent == [text] and text.startswith("🌅 Morning check") and "EVIDENCE" in asked[0] and "WAT" in asked[0] and "failed-voice" in asked[0]
    def dead(prompt):
        raise RuntimeError("credit balance is too low")
    text = morning.run(tmp_path, NOW, {"GITHUB_TOKEN": "t"}, ask=dead, notify=sent.append, get=_get)
    assert "written without Claude" in text and "produce failed" in text and "03 Dec SG-MYTH-WORLD Short" in text
    assert "studio failed" not in text                                                             # it succeeded on the next try
    assert morning.run(tmp_path, NOW, {}, ask=lambda p: "ok", notify=sent.append, get=_get, dry=True) and len(sent) == 2      # a dry run sends nothing
