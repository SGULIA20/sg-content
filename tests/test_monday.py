from engine import monday


def test_three_reports_become_one_message_and_a_dead_writer_still_sends_one(tmp_path, monkeypatch):
    """Founder, 24 Nov 2026: 'Merge Monday's three reports into one'."""
    monkeypatch.setenv("SG_REPORT_DIR", str(tmp_path))
    assert monday.hold("report", "Learning with SG: subs +12, views 1,400") and monday.hold("whatworks", "Best: Sahara refund 261 views")
    assert monday.hold("postmortem", "SG-MYTH-WORLD: Trojan Horse held 55% at the 10% mark.")
    sent, asked = [], []
    merged = "Week of 23-29 Nov: " + "Learning +12 subs, 1,400 views. Best Sahara refund (261). Trojan Horse held 55%. " * 3 + "\nThis week's one change: open on the name."
    text = monday.run(tmp_path, ask=lambda p: asked.append(p) or merged, notify=sent.append)
    assert sent == [text] and text.startswith("📊 Monday report") and "one change" in text
    assert all(part in asked[0] for part in ("subs +12", "Sahara refund", "Trojan Horse")) and "ONE message" in asked[0]
    def dead(prompt):
        raise RuntimeError("no credit")
    text = monday.run(tmp_path, ask=dead, notify=sent.append)
    assert len(sent) == 2 and "LAST WEEK IN NUMBERS" in text and "WHAT WORKED" in text and "POST-MORTEM" in text and len(text) < 4000
    (tmp_path / "whatworks.txt").unlink()
    assert "Not made this week: what worked" in monday.run(tmp_path, ask=lambda p: merged, notify=sent.append)


def test_without_the_folder_each_report_sends_itself_as_before(tmp_path, monkeypatch):
    monkeypatch.delenv("SG_REPORT_DIR", raising=False)
    assert monday.hold("report", "x") is False and monday.run(tmp_path, notify=lambda t: 1 / 0) == ""
    long = {"report": "a" * 5000, "whatworks": "b" * 5000, "postmortem": "c" * 5000}
    assert len(monday.joined(long)) <= monday.ROOM and monday.joined(long).count("cut to fit") == 3
