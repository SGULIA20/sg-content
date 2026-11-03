

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
