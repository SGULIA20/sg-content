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
        "hook": (" ".join(vo.split()[:6]) + "?") if vo else "Oil 100 dollar?",     # the first spoken line starts with the hook
        "scenes": scenes or [{"vo": vo, "visual": {"type": "art", "prompt": "oil"}, "facts_used": [0], "label": label}],
        "end_question": "Aapko kya lagta hai?",
        "cards": [],
        "captions": {"youtube": {"title": "Oil 100 dollar hua to?", "description": "x", "tags": ["a"], "chapters": []},
                     "instagram": {"caption": f"Oil 100 dollar. {DISCLAIMER} Share karo us dost ko jo petrol daily bharta hai.", "hashtags": HASHTAGS["sglearning"]["instagram"][:6]},
                     "threads": {"text": "Oil 100 dollar?"}},
        "carousel": False,
    }
    return p


def test_clean_finance_script_passes():
    p = piece_with(_words(180) + " " + DISCLAIMER)
    assert lint.check_script(p, BANNED, []) == []


def test_blocks_buy_call():
    reasons = lint.check_script(piece_with("Reliance kharid lo abhi " + _words(120)), BANNED, [])
    assert any(r.startswith("advice") for r in reasons)


def test_blocks_politician_name():
    reasons = lint.check_script(piece_with("Modi ji ne kaha " + _words(120)), BANNED, [])
    assert any(r.startswith("politics") for r in reasons)


def test_myth_claim_without_label_fails():
    p = piece_with(_words(120), channel="arthvan", label=None)
    assert any(r.startswith("label") for r in lint.check_script(p, BANNED, []))


def test_myth_forbidden_phrase_fails():
    p = piece_with("science proves god " + _words(120), channel="arthvan", label="legend")
    assert any(r.startswith("myth_forbidden") for r in lint.check_script(p, BANNED, []))


def test_near_duplicate_script_fails():
    text = "crude oil sau dollar ke paar gaya to petrol diesel ka daam badhega aur EMI par asar " * 10
    p = piece_with(text)
    assert any(r.startswith("originality") for r in lint.check_script(p, BANNED, [text]))
    assert lint.similarity(text, text) == 1.0
    assert lint.similarity("a b c", "d e f") == 0.0


def test_short_word_count_bounds(monkeypatch):
    from engine import config
    monkeypatch.setattr(config, "STORY_FORMAT", set())      # the 90-135 rule applies to non-story Shorts
    # non-story Shorts (mythology) keep the 90-135 rule
    assert any(r.startswith("length") for r in lint.check_script(piece_with(_words(80), channel="arthvan"), BANNED, []))
    assert not any(r.startswith("length") for r in lint.check_script(piece_with(_words(120), channel="arthvan"), BANNED, []))
    assert any(r.startswith("length") for r in lint.check_script(piece_with(_words(150), channel="arthvan"), BANNED, []))


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
    p = piece_with(_words(120))
    assert lint.check_captions(p, HASHTAGS) == []
    p.script["captions"]["instagram"]["caption"] = "Oil 100 dollar."
    assert any(r.startswith("disclaimer") for r in lint.check_captions(p, HASHTAGS))
    p.script["captions"]["instagram"]["caption"] = f"Oil. {DISCLAIMER}"
    p.script["captions"]["instagram"]["hashtags"] = ["#PaiseKiKhabar"]
    assert any(r.startswith("hashtags") for r in lint.check_captions(p, HASHTAGS))


def test_caption_rejects_unknown_hashtag():
    p = piece_with(_words(120))
    p.script["captions"]["instagram"]["hashtags"] = HASHTAGS["sglearning"]["instagram"][:5] + ["#GetRichQuick"]
    assert any(r.startswith("hashtags") for r in lint.check_captions(p, HASHTAGS))


def test_caption_rejects_phone_or_email():
    p = piece_with(_words(120))
    p.script["captions"]["instagram"]["caption"] = f"Call +91 98765 43210. {DISCLAIMER}"
    assert any(r.startswith("pii") for r in lint.check_captions(p, HASHTAGS))
    p.script["captions"]["threads"]["text"] = "mail me at sg@example.com"
    assert any(r.startswith("pii") for r in lint.check_captions(p, HASHTAGS))


def test_caption_limits():
    p = piece_with(_words(120))
    p.script["captions"]["youtube"]["title"] = "x" * 61
    assert any(r.startswith("title") for r in lint.check_captions(p, HASHTAGS))
    p.script["captions"]["youtube"]["title"] = "ok"
    p.script["captions"]["threads"]["text"] = "y" * 501
    assert any(r.startswith("threads") for r in lint.check_captions(p, HASHTAGS))


def test_load_lists_reads_content_yaml():
    banned, tags = lint.load_lists()
    assert set(banned) >= {"politics", "communal", "advice", "myth_forbidden"}
    assert len(tags["sglearning"]["instagram"]) >= 10 and len(tags["arthvan"]["instagram"]) >= 10


def test_banned_matches_whole_words_only():
    assert not any(r.startswith("politics") for r in lint.check_script(piece_with("Commodity prices badh gaye " + _words(120)), BANNED, []))
    assert any(r.startswith("politics") for r in lint.check_script(piece_with("Modi ne kaha " + _words(120)), BANNED, []))


def test_captions_and_cards_are_checked_for_banned_and_numbers():
    p = piece_with(_words(120))
    p.script["captions"]["youtube"]["title"] = "Reliance kharid lo: Modi ka plan"
    p.script["captions"]["youtube"]["tags"] = ["bjp"]
    p.script["cards"] = [{"big_number": "₹5 lakh crore", "line": "guaranteed return", "source": "x"}]
    reasons = lint.check_captions(p, HASHTAGS)
    assert any(r.startswith("advice") for r in reasons) and any(r.startswith("politics") for r in reasons)
    assert "₹5 lakh crore" in lint.all_text(p) and "guaranteed return" in lint.all_text(p)


def test_real_banned_list_has_no_bare_conversion_and_catches_variants():
    banned, _ = lint.load_lists()
    text = "FD conversion rate acha hai, " + _words(120)
    assert not any(r.startswith("communal") for r in lint.check_script(piece_with(text), banned, []))
    for bad in ("buy karo", "sell karo", "guarantee hai 20% return", "pakka munafa", "Nirmala Sitharaman"):
        assert lint.check_script(piece_with(bad + " " + _words(120)), banned, []), bad


def test_short_word_bounds_fit_59_seconds_of_hinglish(monkeypatch):
    from engine import config
    monkeypatch.setattr(config, "STORY_FORMAT", set())      # the 90-135 rule applies to non-story Shorts
    # measured 20 Oct 2026: the clone speaks Hinglish at about 2.5 words a second; 59 s minus pads leaves room for ~135 words
    assert lint.SHORT_WORDS == (90, 135)
    assert not any(r.startswith("length") for r in lint.check_script(piece_with(_words(120), channel="arthvan"), BANNED, []))
    assert any(r.startswith("length") for r in lint.check_script(piece_with(_words(150), channel="arthvan"), BANNED, []))


def test_card_big_number_must_be_short():
    p = piece_with(_words(120))
    p.script["cards"] = [{"big_number": "₹1,50,735 cr maange", "line": "x", "source": "RBI"}]
    assert any(r.startswith("card") for r in lint.check_captions(p, HASHTAGS))
    p.script["cards"] = [{"big_number": "₹1.5 lakh cr", "line": "x", "source": "RBI"}]
    assert not any(r.startswith("card") for r in lint.check_captions(p, HASHTAGS))


def test_story_shorts_allow_longer_scripts():
    p = piece_with(_words(200))                                               # sglearning short = story format
    assert not any(r.startswith("length") for r in lint.check_script(p, BANNED, []))
    assert any(r.startswith("length") for r in lint.check_script(piece_with(_words(120)), BANNED, []))
    p2 = piece_with(_words(200), channel="arthvan"); p2.script["scenes"][0]["label"] = "legend"
    assert not any(r.startswith("length") for r in lint.check_script(p2, BANNED, []))      # mythology Shorts are stories too


def test_myth_scene_without_facts_may_skip_label():
    p = piece_with(_words(200), channel="arthvan", label="archaeology")
    p.script["scenes"].append({"vo": "Aapko kya lagta hai?", "visual": {"type": "art", "prompt": "x"}, "facts_used": [], "label": None})
    assert not any(r.startswith("label") for r in lint.check_script(p, BANNED, []))
    p.script["scenes"].append({"vo": "36 metre neeche deewar.", "visual": {"type": "art", "prompt": "x"}, "facts_used": [0], "label": None})
    assert any(r.startswith("label") for r in lint.check_script(p, BANNED, []))


def test_captions_need_share_line_and_three_youtube_hashtags():
    p = piece_with(_words(180))
    p.script["captions"]["instagram"]["caption"] = f"Oil 100 dollar. {DISCLAIMER}"
    assert any(r.startswith("share") for r in lint.check_captions(p, HASHTAGS))
    p.script["captions"]["instagram"]["caption"] = f"Oil 100 dollar. {DISCLAIMER} Share karo us dost ko jo abhi bhi FD mein paisa rakhta hai."
    assert not any(r.startswith("share") for r in lint.check_captions(p, HASHTAGS))


def _hooked(hook, first=None, channel="sglearning"):
    from datetime import date
    from engine.pieces import Piece
    p = Piece(id=f"2026-10-30-{channel}-short", channel=channel, kind="short", publish_day=date(2026, 10, 30))
    p.script = {"hook": hook, "scenes": [{"vo": first if first is not None else hook}]}
    return p


def test_hook_rule_rejects_slow_openings_and_keeps_good_ones():
    from engine import lint
    assert lint.check_hook(_hooked("Dividend ka paisa sach mein free hai?")) == []
    assert lint.check_hook(_hooked("Samundar ke beech ek pul, kya woh aaj bhi dikhta hai?", channel="arthvan")) == []
    assert lint.check_hook(_hooked("Kya Kurukshetra ke pattharon par Chakravyuh ka 5,000 saal purana naksha hai?", channel="arthvan")) == []
    slow = lint.check_hook(_hooked("Subah chai ke saath, Bhai ke phone par headline chamki."))
    assert any("setting a scene" in r for r in slow)
    assert any("needs a question" in r for r in lint.check_hook(_hooked("Ek poora mandir pahaad kaat kar bana.")))
    assert any("first spoken line" in r for r in lint.check_hook(_hooked("Petrol 2 rupaye sasta?", first="Aaj ki khabar suniye.")))
    assert lint.check_hook(_hooked("")) == ["hook: missing"]
