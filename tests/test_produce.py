

def test_an_empty_gemini_balance_is_named_at_the_top_of_the_report(tmp_path):
    from engine import pieces as P
    p = P.Piece(id="2026-10-29-sglearning-short", channel="sglearning", kind="short", publish_day=__import__("datetime").date(2026, 10, 29))
    p.reasons = ["try 1: GeminiError: gemini-3.8-flash failed (402): Your prepayment credits are depleted."]
    P.save(p, tmp_path)
    from engine import produce
    assert produce.out_of_credit(tmp_path, [(p.id, "failed-research")])
    assert not produce.out_of_credit(tmp_path, [("x", "uploaded")])


def test_only_pieces_due_within_the_horizon_are_researched(tmp_path):
    """3 Nov 2026 (cost): a piece with no script waits until it is due within RESEARCH_HORIZON_DAYS; a scripted one keeps moving."""
    from datetime import date
    from engine import pieces, produce, slots
    today = date(2026, 11, 3)
    assert not produce._waits_for_its_turn(tmp_path, date(2026, 11, 4), "sglearning", "short", today)     # tomorrow: research
    assert not produce._waits_for_its_turn(tmp_path, date(2026, 11, 10), "sglearning", "short", today)    # 7 days ahead: research
    assert produce._waits_for_its_turn(tmp_path, date(2026, 11, 11), "sglearning", "short", today)        # 8 days ahead: wait
    scripted = pieces.Piece(id=slots.piece_id(date(2026, 11, 11), "sglearning", "short"), channel="sglearning", kind="short",
                            publish_day=date(2026, 11, 11))
    scripted.script = {"scenes": []}
    pieces.save(scripted, tmp_path)
    assert not produce._waits_for_its_turn(tmp_path, date(2026, 11, 11), "sglearning", "short", today)    # already has its script


def test_no_new_video_starts_on_yesterdays_plan_and_a_video_due_soon_skips_the_slow_lanes(tmp_path):
    """founder, 27 Nov 2026: 'max 1 days advance and long videos no advance ... deep search before making reels'."""
    import json
    from datetime import date, datetime, timezone
    from types import SimpleNamespace as P
    from engine import pipeline, produce
    assert produce._waits_for_todays_plan(tmp_path, datetime(2026, 11, 28, 6, 0, tzinfo=timezone.utc)) is False       # no plan file: nothing to wait for
    (tmp_path / "content").mkdir()
    (tmp_path / "content" / "weekly-plan.json").write_text(json.dumps({"generated": "2026-11-27T05:40:00+00:00"}))
    assert produce._waits_for_todays_plan(tmp_path, datetime(2026, 11, 27, 7, 5, tzinfo=timezone.utc)) is False       # planned this morning
    assert produce._waits_for_todays_plan(tmp_path, datetime(2026, 11, 27, 19, 5, tzinfo=timezone.utc)) is True       # past midnight in India: tomorrow's plan is not here yet
    assert produce._waits_for_todays_plan(tmp_path, datetime(2026, 11, 28, 4, 0, tzinfo=timezone.utc)) is True
    assert produce._waits_for_todays_plan(tmp_path, datetime(2026, 11, 28, 10, 45, tzinfo=timezone.utc)) is False      # 16:15 India, still no plan: go on with the old one
    now = datetime(2026, 11, 27, 6, 0, tzinfo=timezone.utc)
    assert pipeline.due_soon(P(channel="sglearning", kind="short", publish_day=date(2026, 11, 28)), now) is True
    assert pipeline.due_soon(P(channel="sglearning", kind="short", publish_day=date(2026, 12, 5)), now) is False
