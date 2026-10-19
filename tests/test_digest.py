import json
from datetime import date

from engine import digest, pieces


def _seed(root):
    rows = [("2026-10-20-sglearning-short", "sglearning", "short", date(2026, 10, 20), "uploaded"),
            ("2026-10-21-sglearning-short", "sglearning", "short", date(2026, 10, 21), "uploaded"),
            ("2026-10-22-sglearning-short", "sglearning", "short", date(2026, 10, 22), "rejected"),
            ("2026-10-21-arthvan-short", "arthvan", "short", date(2026, 10, 21), "posted"),
            ("2026-10-24-arthvan-long", "arthvan", "long", date(2026, 10, 24), "uploaded")]
    for pid, ch, kind, day, status in rows:
        p = pieces.Piece(id=pid, channel=ch, kind=kind, publish_day=day)
        p.status = status
        if status == "rejected":
            p.reasons = ["advice: kharid lo"]
        p.updated = "2026-10-20T03:00:00+00:00"
        pieces.save(p, root)
    (root / "logs").mkdir(exist_ok=True)
    (root / "logs" / "voice-budget.json").write_text(json.dumps({"2026-10-20": 23}))
    (root / "logs" / "image-spend.json").write_text(json.dumps({"2026-10-20": {"inr": 27.0, "requests": 9}}))
    (root / "logs" / "claude-spend.json").write_text(json.dumps({"2026-10-20": {"usd": 0.31, "requests": 2}}))


def test_summary_counts_pieces_by_status(tmp_path):
    _seed(tmp_path)
    text = digest.run_summary(tmp_path, date(2026, 10, 20))
    assert "made 4" in text and "rejected 1" in text and "advice: kharid lo" in text
    assert "voice 23/80" in text and "₹27" in text and "$0.31" in text


def test_buffer_days_per_channel(tmp_path):
    _seed(tmp_path)
    b = digest.buffer_days(tmp_path, date(2026, 10, 20))
    assert b["sglearning"] == 2 and b["arthvan"] == 1            # arthvan: Wed 21 Oct short ready; Fri 23 not


def test_alert_when_buffer_under_two_days(tmp_path):
    _seed(tmp_path)
    alerts = digest.alerts(tmp_path, date(2026, 10, 20))
    assert any("arthvan" in a and "buffer" in a for a in alerts)
    assert not any("sglearning" in a and "buffer" in a for a in alerts)


def test_alert_on_two_failed_runs_and_token_expiry(tmp_path):
    _seed(tmp_path)
    (tmp_path / "logs" / "runs.jsonl").write_text(json.dumps({"day": "2026-10-19", "ok": False}) + "\n" + json.dumps({"day": "2026-10-20", "ok": False}) + "\n")
    (tmp_path / "logs" / "tokens.json").write_text(json.dumps({"instagram_expires": "2026-10-25", "threads_expires": "2026-12-01"}))
    alerts = digest.alerts(tmp_path, date(2026, 10, 20))
    assert any("failed" in a for a in alerts) and any("Instagram token" in a for a in alerts) and not any("Threads token" in a for a in alerts)


def test_status_line(tmp_path):
    _seed(tmp_path)
    line = digest.status_line(tmp_path, date(2026, 10, 20))
    assert "sglearning" in line and "arthvan" in line and "running" in line
