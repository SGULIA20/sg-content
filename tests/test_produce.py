

def test_an_empty_gemini_balance_is_named_at_the_top_of_the_report(tmp_path):
    from engine import pieces as P
    p = P.Piece(id="2026-10-29-sglearning-short", channel="sglearning", kind="short", publish_day=__import__("datetime").date(2026, 10, 29))
    p.reasons = ["try 1: GeminiError: gemini-3.8-flash failed (402): Your prepayment credits are depleted."]
    P.save(p, tmp_path)
    from engine import produce
    assert produce.out_of_credit(tmp_path, [(p.id, "failed-research")])
    assert not produce.out_of_credit(tmp_path, [("x", "uploaded")])
