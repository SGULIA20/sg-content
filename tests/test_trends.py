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
    x = pieces.Piece(id="2026-11-02-sglearning-x1", channel="sglearning", kind="short", publish_day=TODAY, status="uploaded")
    x.topic = {"slot_ist": "13:00", "category": "ai"}; pieces.save(x, tmp_path)
    made, sent = _run(tmp_path, [_item("RBI cuts repo rate")])
    assert trends.extras_today(TODAY) == 1 and made == [] and "made; next cycle reports only" in sent[0]


def test_the_ramp():
    assert trends.extras_today(date(2026, 10, 29)) == 1 and trends.extras_today(date(2026, 11, 5)) == 2 and trends.extras_today(date(2026, 11, 20)) == 3


def test_no_voice_credit_on_youtube_or_instagram():
    from engine import instagram, youtube
    p = pieces.Piece(id="2026-11-02-sglearning-short", channel="sglearning", kind="short", publish_day=TODAY)
    p.script = {"hook": "h", "scenes": [], "captions": {"youtube": {"description": "d", "tags": []}, "instagram": {"caption": "c", "hashtags": []}}}
    assert "Voice:" not in instagram.caption_text(p)
    meta = youtube.metadata(p, datetime(2026, 11, 2, 14, 30, tzinfo=timezone.utc), {})
    assert "Voice:" not in meta["snippet"]["description"]
