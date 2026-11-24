import json
from datetime import date

from engine import intro, lang, lint, pieces, storyframe, writer, youtube


def _piece(day, channel="sglearning", kind="short"):
    return pieces.Piece(id=f"{day.isoformat()}-{channel}-{kind}", channel=channel, kind=kind, publish_day=day)


def test_english_starts_on_the_configured_day_for_learning_only():
    assert json.loads((lang.CONTENT_DIR / "language.json").read_text())["sglearning"]["english_from"] == "2026-11-23"
    assert not lang.english(_piece(date(2026, 11, 22))) and lang.english(_piece(date(2026, 11, 23)))
    assert lang.english(_piece(date(2026, 11, 25), kind="long")) and not lang.english(_piece(date(2026, 12, 1), channel="arthvan"))
    assert lang.disclaimer(_piece(date(2026, 11, 22))) == lint.DISCLAIMER and lang.disclaimer(_piece(date(2026, 11, 23))) == "This is not investment advice"


def test_the_writer_gets_the_english_rules_only_for_english_pieces():
    en = writer.claude_params(_piece(date(2026, 11, 23)), {"facts": []}, [], {})
    hi = writer.claude_params(_piece(date(2026, 11, 22)), {"facts": []}, [], {})
    text = lambda p: json.dumps(p["system"], ensure_ascii=False) if not isinstance(p["system"], str) else p["system"]
    assert "ENGLISH ONLY" in text(en) and "This is not investment advice" in text(en) and "ENGLISH ONLY" not in text(hi)


def test_the_checks_look_for_the_english_fixed_lines():
    p = _piece(date(2026, 11, 23))
    p.script = {"hook": "Money sent to the wrong UPI ID. Why can't your bank just take it back?",
                "end_question": "Send this to your mother, who pays by UPI every day.",
                "scenes": [{"vo": "Money sent to the wrong UPI ID. Why can't your bank just take it back?"},
                           {"vo": "Send this to your mother, who pays by UPI every day."}]}
    assert lint.check_send(p) == []
    assert not any(r.startswith("hook:") and "words" in r for r in lint.check_hook(p))            # 15 words are allowed in English
    p.script["end_question"] = "Yeh Mummy ko bhejo, jo roz UPI karti hain."
    assert any(r.startswith("send:") for r in lint.check_send(p))
    old = _piece(date(2026, 11, 22))
    old.script = {"end_question": "Yeh Mummy ko bhejo, jo roz UPI karti hain.", "scenes": [{"vo": "Yeh Mummy ko bhejo, jo roz UPI karti hain."}]}
    assert lint.check_send(old) == []                                                             # earlier pieces keep the Hindi rule


def test_the_founders_line_and_the_end_card_are_english():
    p = _piece(date(2026, 11, 23))
    p.script = {"hook": "A 50,00,000 home loan, and the bank gets back 95,93,875?", "scenes": [{"vo": "x"}]}
    plan = intro.plan(p, ask=lambda _p: "")
    assert plan["closing"] in lang.CLOSINGS_EN and "50 lakh" in plan["text"] and "about 95.9 lakh" in plan["text"] and "pachaas" not in plan["text"]
    assert storyframe.brand("sglearning", p)["tagline"] == "Money news, straight talk" and "and share" in storyframe.brand("sglearning", p)["cta_html"]
    assert storyframe.brand("sglearning")["tagline"] == "Paise ki khabar, seedhi baat"
    assert youtube._language(p) == "en" and youtube._language(_piece(date(2026, 11, 22))) == "hi"


def test_learning_goes_back_to_hinglish_from_the_until_day_and_the_english_week_stays_english():
    """Founder, 24 Nov 2026: 'SG learning is not working in English, let's make it in Hinglish'."""
    from types import SimpleNamespace as P
    assert lang.english(P(id="2026-11-29-sglearning-short", channel="sglearning", publish_day="2026-11-29"))
    assert not lang.english(P(id="2026-11-30-sglearning-short", channel="sglearning", publish_day="2026-11-30"))
    assert not lang.english(P(id="2026-11-30-arthvan-short", channel="arthvan", publish_day="2026-11-30"))


def test_only_the_learning_clip_prompt_asks_for_a_bare_forehead():
    from engine import intro, pieces
    from datetime import date
    for ch, want in (("sglearning", True), ("arthvan", False)):
        p = pieces.Piece(id=f"2026-11-30-{ch}-short", channel=ch, kind="short", publish_day=date(2026, 11, 30))
        p.topic = {"title": "x"}; p.script = {"scenes": [{"visual": {"prompt": "a street"}}]}
        assert ("no tilak" in intro.story_prompt(p, {"text": "Kyun?"})) is want
