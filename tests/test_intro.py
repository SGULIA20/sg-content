import json
from datetime import date, datetime, timezone
from pathlib import Path

from engine import intro, pieces


def _piece(kind="short", channel="sglearning", pid=None, day=date(2026, 11, 7)):
    p = pieces.Piece(id=pid or f"{day.isoformat()}-{channel}-{kind}", channel=channel, kind=kind, publish_day=day, status="assembled")
    p.script = {"title": "SIP giri, phir bhi *fund house* jeeta?", "hook": "Aapki SIP doobe, phir bhi fund house kyun kamata hai?",
                "scenes": [{"index": 0, "vo": "Aapki SIP doobe, phir bhi fund house kyun kamata hai?"},
                           {"index": 1, "vo": "Har mahine salary aate hi SIP kat jaati hai."}, {"index": 2, "vo": "Market gira, Papa bole SIP band karo."}]}
    p.timings = [0.0, 4.01, 10.9]
    return p


def test_enabled_for_painted_shorts_and_longs_not_code_card_reels():
    assert intro.enabled(_piece()) and intro.enabled(_piece("long", "arthvan"))
    x = _piece(pid="2026-11-07-sglearning-x1"); assert not intro.enabled(x)
    n = _piece(); n.topic = {"news": True, "graphics": True}; assert not intro.enabled(n)
    r = _piece(); r.topic = {"preset": {"roundup": True}}; assert not intro.enabled(r)


def test_plan_is_question_bridge_closing_within_26_words_with_the_founders_prompt_rules():
    p = _piece()
    plan = intro.plan(p, ask=lambda prompt: "Aapka paisa doobta hai, unki fees phir bhi pakki rehti hai")
    assert plan["question"] == p.script["hook"] and plan["bridge"].endswith(".") and plan["closing"] == "Aaiye isko samajhte hain."
    assert plan["text"].endswith("Aaiye isko samajhte hain.") and plan["words"] <= 26 and plan["aspect"] == "9:16"
    for must in ("9:16 vertical, 1080x1920", "window key light", "open palm", "come with me", "SIP debited", "No watermark", "Speaks from the first frame"):
        assert must in plan["prompt"], must


def test_a_long_bridge_or_a_failed_ask_leaves_question_and_closing_only():
    p = _piece("long", "arthvan")
    too_long = intro.plan(p, ask=lambda _p: " ".join(["bahut"] * 30))
    assert too_long["bridge"] == "" and too_long["text"] == p.script["hook"] + " Aaiye isko samajhte hain." and too_long["aspect"] == "16:9"
    def boom(_p): raise RuntimeError("no key")
    assert intro.plan(p, ask=boom)["bridge"] == "" and "old map" in intro.plan(p, ask=boom)["prompt"]


def test_deadline_is_three_hours_before_the_earliest_slot():
    short = _piece()                                           # Learning Short: Instagram 18:30 India comes before YouTube 20:00
    assert intro.earliest_slot_utc(short) == datetime(2026, 11, 7, 13, 0, tzinfo=timezone.utc)
    assert intro.deadline_utc(short) == datetime(2026, 11, 7, 10, 0, tzinfo=timezone.utc)
    long = _piece("long", "sglearning", day=date(2026, 11, 11))      # a long: YouTube 19:00 India
    assert intro.deadline_utc(long) == datetime(2026, 11, 11, 10, 30, tzinfo=timezone.utc)


def test_request_text_names_the_piece_the_words_the_caption_and_the_deadline_in_wat():
    p = _piece(); plan = intro.plan(p, ask=lambda _p: "Aapka paisa doobta hai, unki fees pakki rehti hai")
    text = intro.request_text(p, plan)
    assert "Intro for 2026-11-07-sglearning-short" in text and plan["text"] in text and "intro 2026-11-07-sglearning-short" in text
    assert "Sat 07 Nov 11:00 WAT" in text and "FILE" in text


def test_check_wants_8_to_12_seconds_the_words_and_the_closing_line(tmp_path):
    clip = tmp_path / "c.mp4"; clip.write_bytes(b"x")
    plan = {"text": "Aapki SIP doobe, phir bhi fund house kyun kamata hai? Aapka paisa doobta hai. Aaiye isko samajhte hain."}
    heard = "aapki sip doobe phir bhi fund house kyun kamata hai aapka paisa doobta hai aaiye isko samajhte hain"
    assert intro.check(clip, plan, transcribe=lambda c: heard, seconds=9.9) == []
    assert any("8-12 s" in r for r in intro.check(clip, plan, transcribe=lambda c: heard, seconds=14.2))
    bad = intro.check(clip, plan, transcribe=lambda c: "namaste doston aaj gold ki baat", seconds=9.9)
    assert any("missing words" in r for r in bad) and any("closing line" in r for r in bad)


def test_cues_follow_the_spoken_phrases_one_per_segment_else_the_syllable_split():
    text = "Aapki SIP doobe, phir bhi fund house kyun kamata hai? Aapka paisa doobta hai. Aaiye isko samajhte hain."
    n = len(intro.captions._phrases(text))
    segs = [(0.5 + i * 2.0, 1.9 + i * 2.0) for i in range(n)]
    cues = intro.cues_for(text, segs, 9.9)
    assert len(cues) == n and cues[0][0] == 0.45 and cues[0][1] == segs[1][0] and cues[-1][1] == 9.9 and cues[-1][2].startswith("Aaiye")
    other = intro.cues_for(text, [(0.5, 8.5)], 9.9)
    assert other[0][0] == 0.45 and other[-1][1] == 9.9 and all(len(t.split()) > 1 for _s, _e, t in other)   # "hai?" never stands alone
    assert " ".join(t for _s, _e, t in other) == text


class _Deps:
    intro_notify = None
    subtitles = None
    def __init__(self): self.uploaded = []
    def upload(self, piece, video, thumb): self.uploaded.append(piece.id); return "yt" + piece.id[:4]


def _waiting(tmp_path, with_clip=True):
    p = _piece(); p.status = "intro-wait"; p.topic["intro"] = intro.plan(p, ask=lambda _p: "Aapka paisa doobta hai, unki fees pakki rehti hai")
    out = tmp_path / "out" / p.id; out.mkdir(parents=True); (out / "reel.mp4").write_bytes(b"reel"); (out / "thumb.jpg").write_bytes(b"t")
    pieces.save(p, tmp_path)
    if with_clip:
        c = intro.clip_path(tmp_path, p); c.parent.mkdir(parents=True, exist_ok=True); c.write_bytes(b"clip")
    return p


def test_collect_merges_a_good_clip_and_uploads(tmp_path, monkeypatch):
    p = _waiting(tmp_path); deps = _Deps(); sent, composed = [], []
    monkeypatch.setattr(intro, "duration", lambda path: 9.9)
    heard = "aapki sip doobe phir bhi fund house kyun kamata hai aapka paisa doobta hai unki fees pakki rehti hai aaiye isko samajhte hain"
    action, p = intro.collect(p, deps, tmp_path, now=datetime(2026, 11, 6, 9, 0, tzinfo=timezone.utc), notify=sent.append,
                              transcribe=lambda c: heard, compose_fn=lambda piece, clip, out: composed.append(clip.name))
    assert action == "uploaded-intro" and composed == ["2026-11-07-sglearning-short.mp4"] and deps.uploaded == [p.id]
    assert pieces.load(p.id, tmp_path).status == "uploaded" and "merged" in sent[0]


def test_collect_rejects_a_wrong_clip_once_and_waits_then_plain_at_the_deadline(tmp_path, monkeypatch):
    p = _waiting(tmp_path); deps = _Deps(); sent = []
    monkeypatch.setattr(intro, "duration", lambda path: 9.9)
    early = datetime(2026, 11, 6, 9, 0, tzinfo=timezone.utc)
    action, p = intro.collect(p, deps, tmp_path, now=early, notify=sent.append, transcribe=lambda c: "kuch aur", compose_fn=lambda *a: None)
    assert action == "rejected" and deps.uploaded == [] and "not used" in sent[0] and p.ids.get("intro_rejected")
    action, p = intro.collect(p, deps, tmp_path, now=early, notify=sent.append, transcribe=lambda c: "kuch aur", compose_fn=lambda *a: None)
    assert action == "waiting" and len(sent) == 1                       # the same clip is not checked twice
    assert intro.needed(tmp_path, early) is False
    late = datetime(2026, 11, 7, 10, 0, tzinfo=timezone.utc)
    assert intro.needed(tmp_path, late) is True
    action, p = intro.collect(p, deps, tmp_path, now=late, notify=sent.append, transcribe=lambda c: "kuch aur", compose_fn=lambda *a: None)
    assert action == "uploaded-plain" and deps.uploaded == [p.id] and p.ids.get("intro_skipped") and "plain version" in sent[-1]


def test_sweep_never_raises_and_reports_each_piece(tmp_path, monkeypatch):
    p = _waiting(tmp_path); deps = _Deps(); sent = []
    monkeypatch.setattr(intro, "duration", lambda path: 9.9)
    def boom(*a, **k): raise RuntimeError("ffmpeg died")
    heard = "aapki sip doobe phir bhi fund house kyun kamata hai aapka paisa doobta hai unki fees pakki rehti hai aaiye isko samajhte hain"
    out = intro.sweep(tmp_path, deps, now=datetime(2026, 11, 6, 9, 0, tzinfo=timezone.utc), notify=sent.append, transcribe=lambda c: heard, compose_fn=boom)
    assert out[0][0] == p.id and out[0][1].startswith("failed: RuntimeError") and "stays waiting" in sent[-1]
    assert pieces.load(p.id, tmp_path).status == "intro-wait"


def _scheduled(tmp_path, pid="2026-11-08-sglearning-short", day=date(2026, 11, 8), with_clip=False):
    p = _piece(pid=pid, day=day); p.status = "uploaded"; p.ids["yt_id"] = "old123"
    out = tmp_path / "out" / p.id; out.mkdir(parents=True, exist_ok=True); (out / "reel.mp4").write_bytes(b"reel"); (out / "thumb.jpg").write_bytes(b"t")
    pieces.save(p, tmp_path)
    if with_clip:
        c = intro.clip_path(tmp_path, p); c.parent.mkdir(parents=True, exist_ok=True); c.write_bytes(b"clip")
    return p


def test_scheduled_pieces_are_asked_three_days_ahead_once_and_not_when_their_clip_is_in(tmp_path):
    """4 Nov 2026 (founder: "from tomorrow onwards itself"): the backlog already on YouTube gets the intro too."""
    near = _scheduled(tmp_path); far = _scheduled(tmp_path, "2026-11-12-sglearning-short", date(2026, 11, 12))
    has = _scheduled(tmp_path, "2026-11-07-sglearning-short", date(2026, 11, 7), with_clip=True)
    posted = _scheduled(tmp_path, "2026-11-06-sglearning-short", date(2026, 11, 6)); posted.status = "posted"; pieces.save(posted, tmp_path)
    now = datetime(2026, 11, 5, 7, 0, tzinfo=timezone.utc); sent = []
    assert [p.id for p in intro.scheduled(tmp_path, now)] == [has.id, near.id, far.id]
    asked = intro.ask_scheduled(tmp_path, sent.append, now, ask=lambda _p: "Aapka paisa doobta hai")
    assert asked == [near.id] and len(sent) == 1 and "Intro for 2026-11-08" in sent[0]
    assert intro.ask_scheduled(tmp_path, sent.append, now, ask=lambda _p: "x") == [] and len(sent) == 1        # asked once
    assert intro.needed(tmp_path, now) is True                                                                # the 7 Nov clip is in


def test_a_scheduled_pieces_clip_replaces_its_youtube_upload_in_the_same_slot(tmp_path, monkeypatch):
    p = _scheduled(tmp_path, "2026-11-07-sglearning-short", date(2026, 11, 7), with_clip=True)
    p.topic["intro"] = intro.plan(p, ask=lambda _p: "Aapka paisa doobta hai, unki fees pakki rehti hai"); pieces.save(p, tmp_path)
    monkeypatch.setattr(intro, "duration", lambda path: 9.9)
    deps = _Deps(); sent, deleted, composed = [], [], []
    heard = p.topic["intro"]["text"].lower()
    out = intro.sweep(tmp_path, deps, now=datetime(2026, 11, 5, 7, 0, tzinfo=timezone.utc), notify=sent.append, transcribe=lambda c: heard,
                      compose_fn=lambda piece, clip, o: composed.append(piece.id), delete=lambda ch, vid: deleted.append((ch, vid)))
    assert out == [(p.id, "re-uploaded-intro")] and composed == [p.id] and deleted == [("sglearning", "old123")] and deps.uploaded == [p.id]
    q = pieces.load(p.id, tmp_path)
    assert q.status == "uploaded" and q.ids["yt_id"] == "yt2026" and q.ids["yt_id_replaced"] == "old123" and "re-scheduled" in sent[-1]
    assert intro.scheduled(tmp_path, datetime(2026, 11, 5, 8, 0, tzinfo=timezone.utc)) == []      # done once: it has its intro now


def test_a_scheduled_piece_too_close_to_its_slot_is_left_alone(tmp_path):
    _scheduled(tmp_path, "2026-11-07-sglearning-short", date(2026, 11, 7), with_clip=True)
    late = datetime(2026, 11, 7, 12, 30, tzinfo=timezone.utc)          # Instagram posts at 13:00 UTC
    assert intro.scheduled(tmp_path, late) == [] and intro.needed(tmp_path, late) is False
