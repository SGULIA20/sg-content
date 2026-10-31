from datetime import date

from engine import lint, pieces, writer


def _p(scenes, topic=None):
    p = pieces.Piece(id="2026-10-31-sglearning-x9", channel="sglearning", kind="short", publish_day=date(2026, 10, 31))
    p.topic = topic or {"preset": {"extra": True, "graphics": True}}
    p.script = {"scenes": [{"vo": vo, "visual": {"type": "card", "prompt": "", "card": {"big_number": big, "line": line, "source": "ET"}}}
                           for vo, big, line in scenes]}
    return p


def test_card_must_show_what_the_voice_says():
    ok = _p([("Jio ne 8,387 crore kamaye.", "₹8,387 cr", "ek quarter ka profit"), ("Intel 29.1 percent gira.", "-29.1%", "bura din"),
             ("Floating rate apne aap nahi girta.", "", "reset date par badlega")])
    assert lint.card_hits(ok) == []
    bad = _p([("RBI data: purane loan wahin atke.", "8.96%", "purane loan ka rate"), ("Byaaj kharid keemat par banta hai.", "2.5%", "Byaaj sirf ₹4,715 par"),
              ("2021 ka sona kaafi mehenga hai.", "3 guna", "Har gram par paisa")])
    hits = lint.card_hits(bad)
    assert len(hits) == 3 and "8.96" in hits[0] and "4715" in hits[1] and "2.5" in hits[1] and "scene 2 shows 3" in hits[2]


def test_figures_are_capped_and_years_do_not_count():
    news = _p([("Naya loan 8.51 percent, purana 8.96?", "", ""), ("Base 8.55 hua.", "", ""), ("FD 5.61, purani 6.55.", "", ""), ("2021 se.", "", "")])
    hit = lint.figure_hits(news)
    assert hit and hit[0].startswith("figures: 5 different numbers") and "allowed 3" in hit[0]
    assert lint.figure_hits(_p([("2021 ka bond, 2029 tak.", "", ""), ("Sona 14,167 har gram.", "", "")])) == []
    roundup = _p([(f"Item {n} percent.", "", "") for n in range(1, 7)], topic={"preset": {"extra": True, "roundup": True}})
    assert lint.figure_hits(roundup) == []


def test_new_jargon_is_caught():
    p = _p([("Banks ka MCLR gira, spread poochho, quarter mein profit. Yeh investment advice nahi hai.", "", "")])
    hit = lint.jargon_hits(p)[0]
    assert "mclr" in hit and "spread" in hit and "quarter" in hit


def test_these_misses_get_a_cheap_patch():
    assert writer.patchable(["card: scene 1 shows 8.96 but its voice line does not say it", "figures: 7 different numbers spoken (...), allowed 3",
                             "jargon: say mclr in everyday words"])


def test_daily_painted_shorts_are_left_alone():
    p = _p([("Meta ka capex, is quarter free cash flow minus, 10.38 percent, 145 billion, 5, 6, 7.", "", "")], topic={"title": "Meta"})
    for sc in p.script["scenes"]:
        sc["visual"] = {"type": "art", "prompt": "x", "card": None}
    assert lint.card_hits(p) == [] and lint.figure_hits(p) == []
    hit = lint.jargon_hits(p)[0]
    assert "capex" in hit and "quarter" not in hit                       # the 30 Oct list still applies; the new words do not
