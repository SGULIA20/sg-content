from datetime import date, datetime, timedelta, timezone

from engine import pieces, trends

NOW = datetime(2026, 11, 2, 4, 30, tzinfo=timezone.utc)                       # 10:00 India, Monday
TODAY = date(2026, 11, 2)


def _item(title, hours=2, link=None):
    return {"title": title, "summary": "", "link": link or title, "published": NOW - timedelta(hours=hours), "rank": 1}


def _main(root, title="Gold price falls again"):
    p = pieces.Piece(id="2026-11-02-sglearning-short", channel="sglearning", kind="short", publish_day=TODAY, status="uploaded")
    p.topic = {"title": title}
    pieces.save(p, root)


def _run(root, items, bank=None):
    made, sent = [], []
    def make(topic, root_, now, slot_ist=None, notify=None):
        made.append((topic, slot_ist))
        p = pieces.Piece(id=f"2026-11-02-sglearning-x{len(made)}", channel="sglearning", kind="short", publish_day=TODAY, status="uploaded")
        p.topic = {**topic, "slot_ist": slot_ist}; pieces.save(p, root_); return p
    trends.run(root, NOW, items=items, notify=sent.append, make=make, bank=bank or [])
    return made, sent


def test_a_cycle_makes_the_best_fresh_story_in_the_next_slot_and_reports(tmp_path):
    _main(tmp_path)
    made, sent = _run(tmp_path, [_item("Innodata lays off 550 employees in India"), _item("Sensex outlook: prediction for today")])
    assert made[0][0]["title"].startswith("Innodata") and made[0][1] == "13:00" and made[0][0]["category"] == "jobs"
    assert "skip: daily market call" in sent[0] and "Making now (fresh news, jobs)" in sent[0]


def test_two_reels_in_a_row_never_share_a_category_and_the_bank_fills_quiet_cycles(tmp_path):
    _main(tmp_path, "Layoffs at a big IT firm: 2,000 employees")                              # today's 18:30 Reel is jobs
    bank = [{"id": "eg-jobs-x", "category": "jobs", "title": "Gratuity"}, {"id": "eg-psy-x", "category": "psychology", "title": "Anchoring"}]
    made, _ = _run(tmp_path, [_item("Another company lays off 300 employees")], bank=bank)
    assert made[0][0]["id"] == "eg-psy-x"                                                      # fresh jobs story skipped: same category as the next Reel


def test_once_todays_extras_are_made_a_cycle_only_reports(tmp_path):
    _main(tmp_path)
    for n, slot in enumerate(("13:00", "16:30", "22:45"), 1):
        x = pieces.Piece(id=f"2026-11-02-sglearning-x{n}", channel="sglearning", kind="short", publish_day=TODAY, status="uploaded")
        x.topic = {"slot_ist": slot, "category": "ai"}; pieces.save(x, tmp_path)
    made, sent = _run(tmp_path, [_item("RBI cuts repo rate")])
    assert trends.extras_today(TODAY) == 3 and made == [] and "made; next cycle reports only" in sent[0]


def test_the_ramp():
    assert trends.extras_today(date(2026, 10, 29)) == 1 and trends.extras_today(date(2026, 10, 31)) == 3 and trends.extras_today(date(2026, 11, 20)) == 3


def test_no_voice_credit_on_youtube_or_instagram():
    from engine import instagram, youtube
    p = pieces.Piece(id="2026-11-02-sglearning-short", channel="sglearning", kind="short", publish_day=TODAY)
    p.script = {"hook": "h", "scenes": [], "captions": {"youtube": {"description": "d", "tags": []}, "instagram": {"caption": "c", "hashtags": []}}}
    assert "Voice:" not in instagram.caption_text(p)
    meta = youtube.metadata(p, datetime(2026, 11, 2, 14, 30, tzinfo=timezone.utc), {})
    assert "Voice:" not in meta["snippet"]["description"]


def test_an_empty_gemini_balance_sends_the_top_up_alert_not_a_red_run(tmp_path):
    from engine import produce
    _main(tmp_path)
    sent = []
    def make(topic, root_, now, slot_ist=None, notify=None):
        p = pieces.Piece(id="2026-11-02-sglearning-x1", channel="sglearning", kind="short", publish_day=TODAY, status="failed-topic")
        p.reasons = ["try 1: gemini failed (402): Your prepayment credits are depleted."]
        pieces.save(p, root_); return p
    assert trends.run(tmp_path, NOW, items=[_item("Infosys layoffs: 300 jobs cut")], notify=sent.append, make=make, bank=[]) == 0
    assert sent[-1] == produce.CREDIT_ALERT


def test_a_daily_us_market_wrap_is_skipped():
    rows = trends.ranked([_item("US markets today: US stocks end lower as Alphabet revenue miss revives AI capex jitters")], set(), NOW)
    assert rows[0][2] == "daily market call (stale by evening)"


def test_a_failed_extra_frees_its_slot_and_the_days_allowance(tmp_path):
    _main(tmp_path)
    dead = pieces.Piece(id="2026-11-02-sglearning-x1", channel="sglearning", kind="short", publish_day=TODAY, status="failed-topic")
    dead.topic = {"title": "x", "slot_ist": "13:00"}
    pieces.save(dead, tmp_path)
    made, _sent = _run(tmp_path, [_item("Infosys layoffs: 300 jobs cut")])
    assert len(made) == 1 and made[0][1] == "13:00"


def test_the_first_cycle_of_the_day_makes_the_top_10_from_ten_fresh_stories(tmp_path):
    _main(tmp_path)
    early = datetime(2026, 11, 2, 0, 30, tzinfo=timezone.utc)                    # 06:00 India
    titles = ["Bitcoin crashes 8% after Binance hack", "Gold price hits record", "Infosys hiring 20,000 freshers", "Petrol price cut Rs 2",
              "Nvidia chip sales record", "Rupee falls to 95", "Tata Motors profit jumps", "Crude oil at $113", "Home loan rates cut",
              "OpenAI launches new model", "Silver price surges"]
    items = [{"title": t, "summary": "", "link": t, "published": early - timedelta(hours=3), "rank": 1, "source": "ET"} for t in titles]
    made, sent = [], []
    def make(topic, root_, now, slot_ist=None, notify=None):
        made.append((topic, slot_ist))
        p = pieces.Piece(id=f"2026-11-02-sglearning-x{len(made)}", channel="sglearning", kind="short", publish_day=TODAY, status="uploaded")
        p.topic = {**topic, "slot_ist": slot_ist}; pieces.save(p, root_); return p
    trends.run(tmp_path, early, items=items, notify=sent.append, make=make, bank=[])
    top = [t for t, s in made if t.get("roundup")]
    assert len(top) == 1 and made[0][1] == "09:30" and top[0]["summary"].startswith("TOP 10 ROUNDUP")
    assert top[0]["summary"].count("\n") == 10
    trends.run(tmp_path, early + timedelta(hours=1), items=items, notify=sent.append, make=make, bank=[])
    assert len([t for t, s in made if t.get("roundup")]) == 1                 # once a day
