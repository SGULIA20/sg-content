from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

from engine import art, costs, digest, pieces, pipeline, voice, voicebatch, writer


def test_spend_while_a_piece_is_made_is_added_up():
    with costs.track() as c:
        costs.add(inr=1.5)
        costs.add(inr=3.0, usd=0.03)
        costs.add(voice=2)
    assert c == {"inr": 4.5, "usd": 0.03, "voice": 2}


def test_spend_outside_a_piece_is_ignored():
    costs.add(inr=9.0)                                                  # nothing is tracking: no error, nothing kept
    with costs.track() as c:
        pass
    assert c == {"inr": 0.0, "usd": 0.0, "voice": 0}


def test_a_picture_a_claude_call_and_a_voice_line_each_reach_the_open_piece(tmp_path):
    usage = SimpleNamespace(input_tokens=1_000_000, output_tokens=0)
    with costs.track() as c:
        art._record(tmp_path / "image.json", date(2026, 10, 24), 3.0)
        writer.record_spend(usage, tmp_path / "claude.json", date(2026, 10, 24), factor=0.5)
        voice._count_request(tmp_path / "voice.json", date(2026, 10, 24))
        voicebatch.submit(["one", "two", "three"], "voiceX", "label", key="k", post=lambda url, body, key: (200, {"name": "batches/1"}))
    assert c["inr"] == 3.0
    assert round(c["usd"], 4) == round(writer.cost_usd(usage) * 0.5, 4) and c["usd"] > 0
    assert c["voice"] == 4                                              # one sync request plus a three-line batch


def test_subtitle_translation_is_metered_at_sonnet_prices(tmp_path):
    import json
    from engine import subtitles

    class FakeClient:
        class messages:
            @staticmethod
            def create(**kw):
                lines = json.loads(kw["messages"][0]["content"])
                class R:
                    content = [type("B", (), {"text": json.dumps(lines)})()]
                    usage = SimpleNamespace(input_tokens=1_000_000, output_tokens=100_000)     # Sonnet 5.5: $2 in, $10 out per million tokens
                return R()
    spend = tmp_path / "claude.json"
    with costs.track() as c:
        subtitles.translate(["ek", "do"], "en", client=FakeClient(), spend=spend, today=date(2026, 10, 24))
    assert c["usd"] == 3.0                                             # $2.00 for the input + $1.00 for the output
    assert json.loads(spend.read_text())["2026-10-24"]["usd"] == 3.0


def test_totals_add_up_and_convert_dollars_to_rupees():
    assert costs.merge({"inr": 3.0, "usd": 0.1, "voice": 1}, {"inr": 1.0, "usd": 0.2, "voice": 2}) == {"inr": 4.0, "usd": 0.3, "voice": 3}
    assert costs.merge(None, {"inr": 1.0, "usd": 0.0, "voice": 0}) == {"inr": 1.0, "usd": 0.0, "voice": 0}
    assert costs.total_inr({"inr": 10.0, "usd": 1.0, "voice": 5}) == 10.0 + costs.INR_PER_USD


def test_one_piece_over_three_times_the_median_is_flagged_only_with_enough_company():
    rows = [("a", 10.0), ("b", 11.0), ("c", 9.0), ("d", 10.0), ("e", 100.0)]
    assert costs.outliers(rows) == [("e", 100.0, 10.0)]
    assert costs.outliers(rows[:4] + [("e", 25.0)]) == []               # 2.5 times the median: fine
    assert costs.outliers(rows[:3] + [("e", 100.0)]) == []              # four pieces are too few to call anything unusual


def _piece(root, pid, kind, inr, updated):
    p = pieces.Piece(id=pid, channel="sglearning", kind=kind, publish_day=date(2026, 10, 24), status="uploaded")
    p.ids = {"cost": {"inr": inr, "usd": 0.0, "voice": 0}}
    p.updated = updated
    pieces.save(p, root)
    return p


def test_the_digest_names_a_recent_piece_that_cost_far_more_than_usual(tmp_path):
    (tmp_path / "pieces").mkdir()
    now = datetime(2026, 10, 24, 9, 0, tzinfo=timezone.utc).isoformat(timespec="seconds")
    for i, inr in enumerate([10.0, 12.0, 9.0, 11.0, 10.0]):
        _piece(tmp_path, f"2026-10-2{i}-sglearning-short", "short", inr, now)
    _piece(tmp_path, "2026-10-29-sglearning-short", "short", 90.0, now)
    lines = [a for a in digest.alerts(tmp_path, date(2026, 10, 24)) if "cost" in a]
    assert len(lines) == 1 and "2026-10-29-sglearning-short" in lines[0] and "₹90" in lines[0]


def test_an_old_expensive_piece_does_not_alert_again_and_again(tmp_path):
    (tmp_path / "pieces").mkdir()
    old = (datetime(2026, 10, 24, 9, 0, tzinfo=timezone.utc) - timedelta(days=5)).isoformat(timespec="seconds")
    for i, inr in enumerate([10.0, 12.0, 9.0, 11.0, 10.0, 90.0]):
        _piece(tmp_path, f"2026-10-2{i}-sglearning-short", "short", inr, old)
    assert not [a for a in digest.alerts(tmp_path, date(2026, 10, 24)) if "cost" in a]


def test_make_keeps_the_running_cost_on_the_piece_across_runs(tmp_path, monkeypatch):
    (tmp_path / "pieces").mkdir()
    p = pieces.Piece(id="2026-10-25-sglearning-short", channel="sglearning", kind="short", publish_day=date(2026, 10, 25))

    def fake(piece, deps, root, dry_run, pack_mode):
        costs.add(inr=3.0, usd=0.02, voice=1)
        return piece
    monkeypatch.setattr(pipeline, "_make", fake)
    pipeline.make(p, None, tmp_path)
    p2 = pipeline.make(pieces.load(p.id, tmp_path), None, tmp_path)                    # a second run (a re-make, a resume) adds to the first
    assert pieces.load(p.id, tmp_path).ids["cost"] == {"inr": 6.0, "usd": 0.04, "voice": 2}
    assert p2.ids["cost"]["inr"] == 6.0


def test_a_dry_run_records_nothing(tmp_path, monkeypatch):
    (tmp_path / "pieces").mkdir()
    p = pieces.Piece(id="2026-10-25-sglearning-short", channel="sglearning", kind="short", publish_day=date(2026, 10, 25))
    monkeypatch.setattr(pipeline, "_make", lambda piece, deps, root, dry_run, pack_mode: piece)
    assert "cost" not in pipeline.make(p, None, tmp_path, dry_run=True).ids
