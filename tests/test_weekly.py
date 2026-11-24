import json
from datetime import date
from pathlib import Path

from engine import pieces, weekly

TODAY = date(2026, 11, 7)
FINANCE_SLOT, MYTH_SLOT = "2026-11-14-sglearning-short", "2026-11-14-arthvan-short"


def _reply(items):
    return "```json\n" + json.dumps(items) + "\n```"


def _ask(prompt):
    if "Learning with SG" in prompt:
        return _reply([
            {"slot": FINANCE_SLOT, "title": "Gold silver crash: abhi khareedein ya rukein, ₹33,710 sasta?", "summary": "Why gold and silver fell and what a buyer should check.",
             "hooks": ["Sona 33,710 sasta hua, ab kya karein?"], "why": "gold crash videos at 2M views"},
            {"slot": "2026-11-15-sglearning-short", "title": "BJP rally mein kya hua, election ka poora sach", "summary": "Rally.", "hooks": [], "why": "x"},     # party politics: dropped
        ])
    return _reply([{"slot": MYTH_SLOT, "title": "Bhagwan Vishnu ka sir kaise kata? Hayagriva ka rahasya", "summary": "The Hayagriva story and its sources.",
                    "hooks": ["Vishnu ka sir kaise kata?"], "why": "6.2M views on the same story"}])


def test_build_plans_the_open_slots_keeps_strong_proposals_and_fills_weak_ones_from_the_banks(tmp_path):
    plan = weekly.build(tmp_path, TODAY, {"sglearning": [], "arthvan": []}, ask=_ask, calendar=[])
    e = plan["entries"]
    assert e[FINANCE_SLOT]["id"] == f"wk-{FINANCE_SLOT}" and e[FINANCE_SLOT]["weekly"] and not e[FINANCE_SLOT].get("from_bank") and e[FINANCE_SLOT]["topic_score"] >= weekly.MIN_SCORE
    assert e[MYTH_SLOT]["allowed_sources"] and e[MYTH_SLOT]["topic_score"] >= weekly.MIN_SCORE
    dropped = e["2026-11-15-sglearning-short"]
    assert dropped.get("from_bank") and "rally" not in str(dropped.get("title"))
    assert any("dropped" in n for n in plan["notes"])
    titles = [str(t.get("title") or t.get("title_hi")) for t in e.values()]
    assert len(titles) == len(set(titles))                                          # no topic twice in the week


def test_already_made_pieces_are_not_planned_and_a_claude_failure_falls_back_to_the_banks(tmp_path):
    p = pieces.Piece(id=FINANCE_SLOT, channel="sglearning", kind="short", publish_day=date(2026, 11, 14)); p.status = "uploaded"; pieces.save(p, tmp_path)
    def boom(prompt):
        raise RuntimeError("no key")
    plan = weekly.build(tmp_path, TODAY, {}, ask=boom, calendar=[])
    assert FINANCE_SLOT not in plan["entries"] and len(plan["entries"]) > 10 and all(t.get("from_bank") for t in plan["entries"].values())
    assert sum("could not propose" in n for n in plan["notes"]) == 2


def test_topic_for_gives_the_planned_topic_once_and_never_loops_on_a_failed_one(tmp_path):
    (tmp_path / "content").mkdir()
    plan = weekly.build(tmp_path, TODAY, {}, ask=_ask, calendar=[])
    weekly.save(plan, tmp_path / "content" / "weekly-plan.json")
    piece = pieces.Piece(id=FINANCE_SLOT, channel="sglearning", kind="short", publish_day=date(2026, 11, 14))
    first = weekly.topic_for(tmp_path, piece, set())
    assert first and first["title"].startswith("Gold silver crash")
    assert weekly.topic_for(tmp_path, piece, {first["id"]}) is None                  # tried and failed: the usual flow takes over
    other = pieces.Piece(id="2030-01-01-sglearning-short", channel="sglearning", kind="short", publish_day=date(2030, 1, 1))
    assert weekly.topic_for(tmp_path, other, set()) is None


def test_run_saves_the_plan_and_tells_the_founder_and_dry_run_does_neither(tmp_path):
    (tmp_path / "content").mkdir()
    sent = []
    plan = weekly.run(tmp_path, TODAY, ask=_ask, notify=sent.append, rows={"sglearning": [{"views": 2081757, "title": "Gold-Silver Crash!", "seconds": 146, "channel": "x"}], "arthvan": []})
    assert (tmp_path / "content" / "weekly-plan.json").exists() and sent and "Topic plan" in sent[0] and "Learning with SG" in sent[0] and "SG-MYTH-WORLD" in sent[0]
    sent.clear()
    (tmp_path / "content" / "weekly-plan.json").unlink()
    weekly.run(tmp_path, TODAY, ask=_ask, notify=sent.append, rows={}, dry=True)
    assert not sent and not (tmp_path / "content" / "weekly-plan.json").exists()


def test_parse_survives_fences_prose_and_garbage():
    assert weekly.parse('Here you go:\n```json\n[{"slot": "a", "title": "t"}]\n```') == [{"slot": "a", "title": "t"}]
    assert weekly.parse("nothing useful") == [] and weekly.parse("[not json]") == []
    assert weekly.repeats("Gold silver crash kyun hua", ["Gold silver crash: kya karein"]) and not weekly.repeats("Kedarnath ki deewar", ["Gold silver crash"])


def test_parse_accepts_an_object_wrapping_the_list_and_other_key_names():
    raw = '{"topics": [{"slot_id": "2026-11-14-arthvan-short", "topic": "Vishnu ka sir kaise kata?"}]}'
    assert weekly.parse(raw) == [{"slot_id": "2026-11-14-arthvan-short", "topic": "Vishnu ka sir kaise kata?", "slot": "2026-11-14-arthvan-short", "title": "Vishnu ka sir kaise kata?"}]


def test_an_unusable_reply_is_reported_in_the_plan_notes(tmp_path):
    plan = weekly.build(tmp_path, TODAY, {}, ask=lambda p: "Sorry, I cannot do that.", calendar=[])
    assert sum("no usable topics" in n for n in plan["notes"]) == 2 and all(t.get("from_bank") for t in plan["entries"].values())


def test_a_reply_cut_off_midway_still_yields_the_complete_items():
    raw = ('```json\n[\n {"slot": "a", "title": "Gold *crash* kyun? \U0001F4C9", "summary": "x", "hooks": ["q"]},\n'
           ' {"slot": "b", "title": "Sona ya chandi?", "summary": "y"},\n {"slot": "c", "title": "cut off here", "summary": "unfinis')
    got = weekly.parse(raw)
    assert [g["slot"] for g in got] == ["a", "b"] and got[0]["title"] == "Gold crash kyun?"


def test_the_planner_sees_the_founders_pasted_analyses_as_hints_only(tmp_path):
    (tmp_path / "intel").mkdir()
    (tmp_path / "intel" / "arthvan.md").write_text("Seven Unakoti Shorts split interest.")
    assert weekly.intel_for("arthvan", tmp_path) == "Seven Unakoti Shorts split interest." and weekly.intel_for("sglearning", tmp_path) == ""
    seen = []
    weekly.build(tmp_path, TODAY, {}, ask=lambda p: seen.append(p) or "[]", calendar=[])
    arth = next(p for p in seen if "SG-MYTH-WORLD" in p)
    assert "hints only, unchecked" in arth                                   # the shipped content/intel notes are in the prompt


def test_a_dropped_slot_takes_a_spare_trend_topic_before_any_bank_topic(tmp_path):
    """Founder, 23 Nov 2026: 'pick the trending topics without my approval'. The 22 Nov plan filled 15 of 22 slots from the banks."""
    def ask(prompt):
        assert "spare-short-1" in prompt
        if "Learning with SG" not in prompt:
            return "[]"
        return _reply([
            {"slot": "2026-11-15-sglearning-short", "title": "BJP rally mein kya hua, election ka poora sach", "summary": "Rally.", "hooks": [], "why": "x"},
            {"slot": "spare-short-1", "title": "Gold silver crash: abhi khareedein ya rukein, ₹33,710 sasta?", "summary": "Why gold and silver fell and what a buyer should check.",
             "hooks": ["Sona 33,710 sasta hua, ab kya karein?"], "why": "gold crash videos at 2M views"}])
    e = weekly.build(tmp_path, TODAY, {"sglearning": [{"id": "a", "title": "Gold crash", "channel": "X", "views": 9, "seconds": 40, "short": True}]}, ask=ask, calendar=[])["entries"]
    took = e["2026-11-15-sglearning-short"]
    assert took.get("spare") and not took.get("from_bank") and "Gold" in took["title"]
    assert sum(1 for t in e.values() if t.get("spare")) == 1                        # a spare is used once
    assert "took off in the last 7 days" in weekly._prompt("sglearning", [("2026-11-15-sglearning-short", "sglearning", "short", date(2026, 11, 15))],
                                                           [{"title": "Gold crash", "channel": "X", "views": 9, "seconds": 40, "short": True}], TODAY, [], [])


def test_learning_takes_any_viral_subject_without_the_theme_wait_or_the_money_score(tmp_path):
    """Founder, 24 Nov 2026: 'any topic for sglearning' ... 'the channel to learn anything not only money'."""
    def ask(prompt):
        if "Learning with SG" not in prompt:
            return "[]"
        assert "ANY subject" in prompt and "trending charts right now" in prompt and "WORLD is talking about" in prompt
        return _reply([{"slot": "2026-11-14-sglearning-short", "title": "IPL auction mein 27 crore: yeh paisa aata kahan se hai?", "summary": "The record bid.", "hooks": [], "why": "trending"},
                       {"slot": "2026-11-15-sglearning-short", "title": "Chandrayaan ne chaand par kya dhoondha, jo kisi ne nahi socha?", "summary": "The find.", "hooks": [], "why": "trending"},
                       {"slot": "2026-11-18-sglearning-long", "title": "Dilli ki hawa itni zehreeli kyun, aur 5 cheezein jo sach mein kaam karti hain", "summary": "Air.", "hooks": [], "why": "trending"}])
    rows = {"sglearning": [{"id": "t1", "title": "IPL auction record", "channel": "X", "views": 9000000, "seconds": 600, "viral": True}]}
    e = weekly.build(tmp_path, TODAY, rows, ask=ask, calendar=[])["entries"]
    for pid in ("2026-11-14-sglearning-short", "2026-11-15-sglearning-short"):
        assert e[pid]["trend"] and not e[pid].get("from_bank")                       # no money words, a low score, still taken
    longs = [t for k, t in e.items() if k.endswith("sglearning-long") and t.get("trend")]
    assert len(longs) <= 1                                                           # a long slot may take a viral subject too


def test_learning_is_made_two_days_ahead_and_the_other_channel_keeps_its_week():
    from engine import buffer
    need = buffer.needed(Path("/nonexistent"), date(2026, 12, 1))
    days = lambda ch, kind: [(d - date(2026, 12, 1)).days for d, c, k in need if c == ch and k == kind]
    assert max(days("sglearning", "short")) == 2 and max(days("sglearning", "long")) <= 4
    assert max(days("arthvan", "short")) == 6


def test_a_subject_made_weeks_ago_is_still_remembered_and_a_market_rally_is_not_politics(tmp_path):
    from engine import topicscore
    p = pieces.Piece(id="2026-09-01-arthvan-short", channel="arthvan", kind="short", publish_day=date(2026, 9, 1)); p.status = "posted"
    p.script = {"title": "Konark mandir ka *chumbak* sach tha?", "scenes": []}; p.topic = {"title": "Konark ka chumbak"}; pieces.save(p, tmp_path)
    seen = weekly.recent_titles(tmp_path, today=TODAY)
    assert "Konark ka chumbak" in seen and weekly.repeats("Konark ke Sun Temple ka chumbak jahaz kheenchta tha?", seen)
    assert weekly.recent_titles(tmp_path, days=30, today=TODAY) == []                       # older than the window
    assert topicscore.score({"title": "Sona-chandi ki rally achanak kyun ruki?", "summary": "", "hooks": []}, "sglearning", TODAY, [])[0] > -10
