from datetime import date

from engine import lint, pieces

BANNED = {
    "politics": ["modi", "rahul gandhi", "bjp", "congress party", "vote"],
    "communal": ["hindu vs muslim", "musalman", "dharm yudh"],
    "advice": ["kharid lo", "bech do", "target price", "guaranteed", "pakka return", "100% safe", "multibagger"],
    "myth_forbidden": ["science proves god", "andhvishwas", "bhagwan nahi hai"],
}
HASHTAGS = {
    "sglearning": {"instagram": ["#PaiseKiKhabar", "#SeedhiBaat", "#StockMarketIndia", "#MoneyTipsHindi", "#HinglishFinance",
                                 "#ShareMarket", "#InvestingIndia", "#PersonalFinanceIndia", "#CrudeOil", "#RBI", "#SEBI", "#Nifty"],
                   "youtube": ["#Shorts", "#Finance", "#Hindi", "#StockMarket", "#India"], "threads": ["#PaiseKiKhabar", "#Finance"]},
    "arthvan": {"instagram": ["#SabutKeSaath", "#Mahabharat", "#Ramayan", "#Dwarka", "#IndianHistory", "#Mythology",
                              "#Archaeology", "#AncientIndia", "#HinduMythology", "#Itihaas", "#Rahasya", "#Sanatan"],
                "youtube": ["#Shorts", "#Mythology", "#Hindi", "#History", "#India"], "threads": ["#SabutKeSaath", "#Mythology"]},
}
DISCLAIMER = "Yeh investment advice nahi hai"


def _words(n):
    return " ".join(["paisa"] * n)


def piece_with(vo: str, channel="sglearning", kind="short", scenes=None, label="reported"):
    p = pieces.Piece(id=f"2026-10-20-{channel}-{kind}", channel=channel, kind=kind, publish_day=date(2026, 10, 20))
    p.script = {
        "hook": "Oil 100 dollar?",
        "scenes": scenes or [{"vo": vo, "visual": {"type": "art", "prompt": "oil"}, "facts_used": [0], "label": label}],
        "end_question": "Aapko kya lagta hai?",
        "cards": [],
        "captions": {"youtube": {"title": "Oil 100 dollar hua to?", "description": "x", "tags": ["a"], "chapters": []},
                     "instagram": {"caption": f"Oil 100 dollar. {DISCLAIMER}", "hashtags": HASHTAGS["sglearning"]["instagram"][:6]},
                     "threads": {"text": "Oil 100 dollar?"}},
        "carousel": False,
    }
    return p


def test_clean_finance_script_passes():
    p = piece_with(_words(140) + " " + DISCLAIMER)
    assert lint.check_script(p, BANNED, []) == []


def test_blocks_buy_call():
    reasons = lint.check_script(piece_with("Reliance kharid lo abhi " + _words(140)), BANNED, [])
    assert any(r.startswith("advice") for r in reasons)


def test_blocks_politician_name():
    reasons = lint.check_script(piece_with("Modi ji ne kaha " + _words(140)), BANNED, [])
    assert any(r.startswith("politics") for r in reasons)


def test_myth_claim_without_label_fails():
    p = piece_with(_words(140), channel="arthvan", label=None)
    assert any(r.startswith("label") for r in lint.check_script(p, BANNED, []))


def test_myth_forbidden_phrase_fails():
    p = piece_with("science proves god " + _words(140), channel="arthvan", label="legend")
    assert any(r.startswith("myth_forbidden") for r in lint.check_script(p, BANNED, []))


def test_near_duplicate_script_fails():
    text = "crude oil sau dollar ke paar gaya to petrol diesel ka daam badhega aur EMI par asar " * 10
    p = piece_with(text)
    assert any(r.startswith("originality") for r in lint.check_script(p, BANNED, [text]))
    assert lint.similarity(text, text) == 1.0
    assert lint.similarity("a b c", "d e f") == 0.0


def test_short_word_count_bounds():
    assert any(r.startswith("length") for r in lint.check_script(piece_with(_words(100)), BANNED, []))
    assert not any(r.startswith("length") for r in lint.check_script(piece_with(_words(140)), BANNED, []))
    assert any(r.startswith("length") for r in lint.check_script(piece_with(_words(180)), BANNED, []))


def test_long_word_count_uses_target_minutes():
    scenes = [{"vo": _words(140 * 12), "visual": {"type": "art", "prompt": "x"}, "facts_used": [], "label": "reported"}]
    p = piece_with("", kind="long", scenes=scenes)
    p.topic["target_minutes"] = 12
    assert not any(r.startswith("length") for r in lint.check_script(p, BANNED, []))


def test_avatar_share_cap():
    scenes = [{"vo": _words(14), "visual": {"type": "avatar" if i < 4 else "art", "prompt": "x"}, "facts_used": [], "label": "reported"}
              for i in range(10)]
    assert any(r.startswith("avatar") for r in lint.check_script(piece_with("", scenes=scenes), BANNED, []))
    scenes[2]["visual"]["type"] = scenes[3]["visual"]["type"] = "art"     # 2 of 10 = 20 %, under the 25 % cap
    assert not any(r.startswith("avatar") for r in lint.check_script(piece_with("", scenes=scenes), BANNED, []))


def test_finance_caption_needs_disclaimer_and_5_to_8_tags():
    p = piece_with(_words(140))
    assert lint.check_captions(p, HASHTAGS) == []
    p.script["captions"]["instagram"]["caption"] = "Oil 100 dollar."
    assert any(r.startswith("disclaimer") for r in lint.check_captions(p, HASHTAGS))
    p.script["captions"]["instagram"]["caption"] = f"Oil. {DISCLAIMER}"
    p.script["captions"]["instagram"]["hashtags"] = ["#PaiseKiKhabar"]
    assert any(r.startswith("hashtags") for r in lint.check_captions(p, HASHTAGS))


def test_caption_rejects_unknown_hashtag():
    p = piece_with(_words(140))
    p.script["captions"]["instagram"]["hashtags"] = HASHTAGS["sglearning"]["instagram"][:5] + ["#GetRichQuick"]
    assert any(r.startswith("hashtags") for r in lint.check_captions(p, HASHTAGS))


def test_caption_rejects_phone_or_email():
    p = piece_with(_words(140))
    p.script["captions"]["instagram"]["caption"] = f"Call +91 98765 43210. {DISCLAIMER}"
    assert any(r.startswith("pii") for r in lint.check_captions(p, HASHTAGS))
    p.script["captions"]["threads"]["text"] = "mail me at sg@example.com"
    assert any(r.startswith("pii") for r in lint.check_captions(p, HASHTAGS))


def test_caption_limits():
    p = piece_with(_words(140))
    p.script["captions"]["youtube"]["title"] = "x" * 61
    assert any(r.startswith("title") for r in lint.check_captions(p, HASHTAGS))
    p.script["captions"]["youtube"]["title"] = "ok"
    p.script["captions"]["threads"]["text"] = "y" * 501
    assert any(r.startswith("threads") for r in lint.check_captions(p, HASHTAGS))


def test_load_lists_reads_content_yaml():
    banned, tags = lint.load_lists()
    assert set(banned) >= {"politics", "communal", "advice", "myth_forbidden"}
    assert len(tags["sglearning"]["instagram"]) >= 10 and len(tags["arthvan"]["instagram"]) >= 10
