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
    x = _piece(pid="2026-11-07-sglearning-x1"); assert intro.enabled(x)          # founder, 5 Nov 2026: compulsory on every Reel and video
    n = _piece(); n.topic = {"news": True, "graphics": True}; assert intro.enabled(n)
    c = _piece(); c.kind = "carousel"; assert not intro.enabled(c)


def test_plan_is_question_bridge_closing_within_26_words_with_the_founders_prompt_rules():
    p = _piece()
    plan = intro.plan(p, ask=lambda prompt: "Aapka paisa doobta hai, unki fees phir bhi pakki rehti hai")
    assert plan["question"] == p.script["hook"] and plan["bridge"].endswith(".") and plan["closing"] in intro.CLOSINGS
    assert plan["text"].endswith(plan["closing"]) and plan["words"] <= 26 and plan["aspect"] == "9:16"
    assert plan["closing"].rstrip(".") in plan["prompt"]
    for must in ("9:16 vertical, 1080x1920", "key light", "Body language in three beats", "SIP debited", "@SGLearning watermark top right", "Speaks from the first frame", "wearing"):
        assert must in plan["prompt"], must


def test_the_avatar_prompt_changes_setting_outfit_pose_and_camera_from_day_to_day():
    """4 Nov 2026 (founder): "clothes, position, walk or background should change in every reel; all can't be the same"."""
    from datetime import timedelta
    seen = set()
    for k in range(5):
        p = _piece(day=date(2026, 11, 5) + timedelta(days=k))
        pr = intro.prompt_for(p, {"text": ""})
        key = (intro._pick(p, intro.SETTINGS["sglearning"]), intro._pick(p, intro.OUTFITS, 1), intro._pick(p, intro.POSES, 2))
        assert key not in seen; seen.add(key)
        assert "walking" in pr or "seated" in pr or "standing" in pr or "leaning" in pr
    short, long = _piece(day=date(2026, 11, 6)), _piece("long", day=date(2026, 11, 5))         # a long and the next day's Short differ too
    assert intro._pick(short, intro.SETTINGS["sglearning"]) != intro._pick(long, intro.SETTINGS["sglearning"])
    myth = _piece("short", "arthvan", day=date(2026, 11, 5))
    assert "@SGMythWorld" in intro.prompt_for(myth, {"text": ""}) and "old map" in intro.prompt_for(myth, {"text": ""})


def test_a_long_bridge_or_a_failed_ask_leaves_question_and_closing_only():
    p = _piece("long", "arthvan")
    too_long = intro.plan(p, ask=lambda _p: " ".join(["bahut"] * 30))
    assert too_long["bridge"] == "" and too_long["text"] == p.script["hook"] + " " + intro.closing_for(p) and too_long["aspect"] == "16:9"
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
    extra = heard + " aapka paisa doobta hai unki fees phir bhi pakki rehti hai"        # he said more than the plan: still his script
    assert intro.check(clip, {"text": "Aapki SIP doobe, phir bhi fund house kyun kamata hai? Aaiye isko samajhte hain."}, transcribe=lambda c: extra, seconds=9.9) == []
    assert intro.recall("a b c d", "b c d e f g h i j") == 0.75


def test_cues_deal_the_phrases_to_the_speech_segments_by_syllables_never_a_lone_hai():
    """4 Nov 2026: the 7 Nov clip has four speech segments; the script has five phrases once "hai?" joins its question."""
    text = "Aapki SIP doobe, phir bhi fund house kyun kamata hai? Aapka paisa doobta hai, unki fees phir bhi pakki rehti hai. Aaiye isko samajhte hain."
    segs = [(0.508, 1.556), (1.852, 3.219), (4.287, 7.007), (7.55, 8.494)]
    cues = intro.cues_for(text, segs, 9.9)
    texts = [c[2] for c in cues]
    assert texts == ["Aapki SIP doobe,", "phir bhi fund house kyun kamata hai?", "Aapka paisa doobta hai,", "unki fees phir bhi pakki rehti hai.", "Aaiye isko samajhte hain."]
    assert cues[0][0] == 0.458 and cues[1][0] == 1.802 and cues[2][0] == 4.237 and 4.9 < cues[3][0] < 6.2 and cues[4][0] == 7.5 and cues[-1][1] == 9.9
    short = intro.cues_for("Aapki SIP doobe, phir bhi fund house kyun kamata hai? Aaiye isko samajhte hain.", segs, 9.9)
    assert [c[2] for c in short] == ["Aapki SIP doobe,", "phir bhi fund house kyun kamata hai?", "Aaiye isko samajhte hain."] and short[-1][0] == 7.5


def test_cues_follow_the_spoken_phrases_one_per_segment_else_the_syllable_split():
    text = "Aapki SIP doobe, phir bhi fund house kyun kamata hai? Aapka paisa doobta hai. Aaiye isko samajhte hain."
    n = len(intro._phrases(text))
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
    p.ids["intro_sent"] = "2026-11-06T08:00:00+00:00"                                                   # the pipeline asked when it parked
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
    assert pieces.load(p.id, tmp_path).status == "uploaded" and any("merged" in t for t in sent)


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
    assert intro.needed(tmp_path, late) is True                          # the one overdue reminder is due
    action, p = intro.collect(p, deps, tmp_path, now=late, notify=sent.append, transcribe=lambda c: "kuch aur", compose_fn=lambda *a: None)
    assert action == "waiting" and deps.uploaded == [] and p.ids.get("intro_overdue") and "Nothing goes out without it" in sent[-1]
    assert intro.needed(tmp_path, late) is False                         # founder, 5 Nov 2026: never the plain version, reminded once
    action, p = intro.collect(p, deps, tmp_path, now=late, notify=sent.append, transcribe=lambda c: "kuch aur", compose_fn=lambda *a: None)
    assert action == "waiting" and len(sent) == 2


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
                      compose_fn=lambda piece, clip, o: composed.append(piece.id), delete=lambda ch, vid: deleted.append((ch, vid)), find=lambda pc: "")
    assert out == [(p.id, "re-uploaded-intro")] and composed == [p.id] and deleted == [("sglearning", "old123")] and deps.uploaded == [p.id]
    q = pieces.load(p.id, tmp_path)
    assert q.status == "uploaded" and q.ids["yt_id"] == "yt2026" and q.ids["yt_id_replaced"] == "old123" and "re-scheduled" in sent[-1]
    assert intro.scheduled(tmp_path, datetime(2026, 11, 5, 8, 0, tzinfo=timezone.utc)) == []      # done once: it has its intro now


def test_a_scheduled_piece_too_close_to_its_slot_is_left_alone(tmp_path):
    _scheduled(tmp_path, "2026-11-07-sglearning-short", date(2026, 11, 7), with_clip=True)
    late = datetime(2026, 11, 7, 12, 30, tzinfo=timezone.utc)          # Instagram posts at 13:00 UTC
    assert intro.scheduled(tmp_path, late) == [] and intro.needed(tmp_path, late) is False


def test_a_redo_adopts_the_upload_an_earlier_run_already_made_instead_of_uploading_twice(tmp_path, monkeypatch):
    """4 Nov 2026: the first real redo replaced the video on YouTube, then its git push failed; the next run must not add a second video."""
    p = _scheduled(tmp_path, "2026-11-07-sglearning-short", date(2026, 11, 7), with_clip=True)
    p.topic["intro"] = intro.plan(p, ask=lambda _p: "Aapka paisa doobta hai, unki fees pakki rehti hai"); pieces.save(p, tmp_path)
    monkeypatch.setattr(intro, "duration", lambda path: 9.9)
    deps = _Deps(); sent, deleted = [], []
    out = intro.sweep(tmp_path, deps, now=datetime(2026, 11, 5, 7, 0, tzinfo=timezone.utc), notify=sent.append,
                      transcribe=lambda c: p.topic["intro"]["text"].lower(), compose_fn=lambda *a: None,
                      delete=lambda ch, vid: deleted.append(vid), find=lambda pc: "new777")
    assert out == [(p.id, "adopted-intro")] and deleted == ["old123"] and deps.uploaded == []        # adopted, old copy removed, nothing uploaded
    q = pieces.load(p.id, tmp_path)
    assert q.status == "uploaded" and q.ids["yt_id"] == "new777" and q.ids["yt_id_replaced"] == "old123" and q.ids.get("intro")


def test_existing_upload_matches_title_privacy_and_publish_time():
    from engine import youtube
    p = _piece(); p.script["captions"] = {"youtube": {"title": "SIP giri, phir bhi fund house jeeta?"}}
    want = youtube.metadata(p, intro.slots.publish_at(p.channel, p.kind, p.publish_day))["snippet"]["title"]
    at = intro.slots.publish_at(p.channel, p.kind, p.publish_day).strftime("%Y-%m-%dT%H:%M:%SZ")
    def call(method, url, token, **k):
        if "channels?" in url: return 200, {}, {"items": [{"contentDetails": {"relatedPlaylists": {"uploads": "UU1"}}}]}
        if "playlistItems" in url: return 200, {}, {"items": [{"contentDetails": {"videoId": "a"}}, {"contentDetails": {"videoId": "b"}}]}
        return 200, {}, {"items": [{"id": "a", "snippet": {"title": want}, "status": {"privacyStatus": "public", "publishAt": at}},
                                   {"id": "b", "snippet": {"title": want}, "status": {"privacyStatus": "private", "publishAt": at}}]}
    assert intro.existing_upload(p, "tok", call) == "b"
    assert intro.existing_upload(p, "tok", lambda m, u, t, **k: (403, {}, {})) == ""


def test_only_an_upload_newer_than_the_last_recorded_change_is_adopted_and_stray_copies_are_removed():
    """4 Nov 2026, run 15: an older stray private copy of the Tanjore long was adopted and the rebuild never happened."""
    from engine import youtube
    p = _piece("long"); p.script["captions"] = {"youtube": {"title": "T"}}; p.updated = "2026-11-04T16:42:38+00:00"
    want = youtube.metadata(p, intro.slots.publish_at(p.channel, p.kind, p.publish_day))["snippet"]["title"]
    at = intro.slots.publish_at(p.channel, p.kind, p.publish_day).strftime("%Y-%m-%dT%H:%M:%SZ")
    def call(method, url, token, **k):
        if "channels?" in url: return 200, {}, {"items": [{"contentDetails": {"relatedPlaylists": {"uploads": "UU1"}}}]}
        if "playlistItems" in url: return 200, {}, {"items": [{"contentDetails": {"videoId": "stray"}}, {"contentDetails": {"videoId": "fresh"}}]}
        return 200, {}, {"items": [
            {"id": "stray", "snippet": {"title": want, "publishedAt": "2026-11-04T15:30:00Z"}, "status": {"privacyStatus": "private", "publishAt": at}, "contentDetails": {"duration": "PT13M"}},
            {"id": "fresh", "snippet": {"title": want, "publishedAt": "2026-11-04T17:10:00Z"}, "status": {"privacyStatus": "private", "publishAt": at}, "contentDetails": {"duration": "PT13M"}}]}
    assert [f["id"] for f in intro.existing_uploads(p, "tok", call)] == ["fresh", "stray"]
    assert intro.existing_upload(p, "tok", call, after=intro._last_change(p)) == "fresh"
    p.updated = "2026-11-04T17:30:00+00:00"
    assert intro.existing_upload(p, "tok", call, after=intro._last_change(p)) == ""      # nothing newer: rebuild, never adopt the stray
    gone = []
    assert intro.remove_duplicates(p, "fresh", token_for=lambda ch: "t", delete=lambda vid: gone.append(vid) or True,
                                   uploads=lambda pc, tok: intro.existing_uploads(pc, tok, call)) == ["stray"]
    assert gone == ["stray"] and p.ids["yt_duplicates_removed"] == ["stray"]


def test_a_founder_thumbnail_is_set_once_on_the_uploaded_video_and_rides_a_re_upload(tmp_path, monkeypatch):
    """4 Nov 2026: "for long videos will give you thumbnails"."""
    p = _scheduled(tmp_path, "2026-11-05-arthvan-long", date(2026, 11, 5)); p.kind = "long"; pieces.save(p, tmp_path)
    jpg = intro.thumb_path(tmp_path, p); jpg.parent.mkdir(parents=True, exist_ok=True); jpg.write_bytes(b"jpg1")
    assert [q.id for q in intro.pending_thumbs(tmp_path)] == [p.id] and intro.needed(tmp_path, datetime(2026, 11, 4, 12, 0, tzinfo=timezone.utc))
    calls, sent = [], []
    out = intro.set_thumbs(tmp_path, notify=sent.append, set_thumb=lambda tok, vid, path: calls.append((vid, path.name)) or True, token_for=lambda ch, env=None: "t")
    assert out == [(p.id, "thumb-set")] and calls == [("old123", "2026-11-05-arthvan-long.jpg")] and "set on YouTube" in sent[0]
    assert intro.pending_thumbs(tmp_path) == [] and (tmp_path / "out" / p.id / "thumb.jpg").read_bytes() == b"jpg1"
    jpg.write_bytes(b"jpg2")                                                               # a new file is set again, once
    assert [q.id for q in intro.pending_thumbs(tmp_path)] == [p.id]


def test_a_waiting_long_without_its_video_is_rebuilt_by_the_pipeline_and_the_old_upload_removed(tmp_path, monkeypatch):
    """4 Nov 2026: out/**/long.mp4 is never in git, so a long carrying the intro is re-made from the voice and picture caches."""
    from engine import pipeline, youtube
    p = _piece("long"); p.status = "intro-wait"; p.ids["yt_id"] = "oldlong"; p.ids["intro_sent"] = "x"
    p.topic["intro"] = intro.plan(p, ask=lambda _p: "Chhote print ka ek rule"); pieces.save(p, tmp_path)
    c = intro.clip_path(tmp_path, p); c.parent.mkdir(parents=True, exist_ok=True); c.write_bytes(b"clip")
    made, deleted = [], []
    def fake_make(piece, deps, root, **k):
        made.append(piece.status); piece.ids["yt_id"] = "newlong"; piece.status = "uploaded"; pieces.save(piece, root); return piece
    monkeypatch.setattr(pipeline, "make", fake_make)
    monkeypatch.setattr(youtube, "access_token", lambda ch, env=None: "t")
    monkeypatch.setattr(youtube, "delete", lambda tok, vid: deleted.append(vid) or True)
    action, q = intro.collect(p, _Deps(), tmp_path, now=datetime(2026, 11, 6, 9, 0, tzinfo=timezone.utc), notify=lambda t: None, find=lambda pc: "")
    assert action == "rebuilt-uploaded" and made == ["drawn"] and deleted == ["oldlong"]
    assert pieces.load(p.id, tmp_path).ids["yt_id_replaced"] == "oldlong"


def test_a_long_an_earlier_run_already_rebuilt_and_uploaded_is_adopted_not_built_again(tmp_path, monkeypatch):
    """4 Nov 2026: run 10 re-made the Tanjore long and uploaded it, then its push failed on a 114 MB intermediate; the next run adopts."""
    from engine import pipeline, youtube
    p = _piece("long"); p.status = "intro-wait"; p.ids["yt_id"] = "oldlong"; p.ids["intro_sent"] = "x"
    p.topic["intro"] = intro.plan(p, ask=lambda _p: "Chhote print ka ek rule"); pieces.save(p, tmp_path)
    c = intro.clip_path(tmp_path, p); c.parent.mkdir(parents=True, exist_ok=True); c.write_bytes(b"clip")
    monkeypatch.setattr(pipeline, "make", lambda *a, **k: (_ for _ in ()).throw(AssertionError("built again")))
    deleted = []
    monkeypatch.setattr(youtube, "access_token", lambda ch, env=None: "t")
    monkeypatch.setattr(youtube, "delete", lambda tok, vid: deleted.append(vid) or True)
    monkeypatch.setattr(intro, "existing_uploads", lambda pc, tok, call=None: [{"id": "newlong", "uploaded": None, "duration": ""}, {"id": "stray", "uploaded": None, "duration": ""}])
    sent = []
    action, q = intro.collect(p, _Deps(), tmp_path, now=datetime(2026, 11, 6, 9, 0, tzinfo=timezone.utc), notify=sent.append, find=lambda pc: "newlong")
    assert action == "adopted-intro" and q.status == "uploaded" and q.ids["yt_id"] == "newlong" and q.ids["yt_id_replaced"] == "oldlong"
    assert deleted == ["oldlong", "stray"] and q.ids["yt_duplicates_removed"] == ["oldlong", "stray"]      # the old slot copy never publishes twice
    assert pieces.load(p.id, tmp_path).ids["intro"]["adopted"] and "newlong" in sent[0]


def test_a_long_body_resumes_right_after_the_hook_sentence_and_a_short_at_scene_two(tmp_path):
    """4 Nov 2026 (the Tanjore long): the first scene of a long is hook plus set-up; cutting all 22 s made it start from the middle."""
    p = _piece("long"); p.timings = [0.0, 22.05, 42.14]
    p.script["hook"] = "Kehte hain, Tanjore ke mandir ki parchhai dopahar mein zameen par girti hi nahi."
    out = tmp_path / "out" / p.id; out.mkdir(parents=True)
    out.joinpath("captions.ass").write_text("[Events]\n"
        "Dialogue: 0,0:00:00.00,0:00:00.91,Default,,0,0,0,,Kehte hain,\n"
        "Dialogue: 0,0:00:00.91,0:00:04.56,Default,,0,0,0,,Tanjore ke mandir ki parchhai dopahar\n"
        "Dialogue: 0,0:00:04.56,0:00:07.30,Default,,0,0,0,,mein zameen par girti hi nahi.\n"
        "Dialogue: 0,0:00:07.30,0:00:10.04,Default,,0,0,0,,Log ise chamatkar kehte hain,\n")
    assert intro.body_cut(p, out) == 7.3
    p.script["hook"] = "Some other hook entirely"
    assert intro.body_cut(p, out) == 0.0                      # not placed: the whole long, the hook heard twice, never a jump
    q = _piece("short"); q.timings = [0.0, 5.2, 9.9]
    assert intro.body_cut(q, out) == 5.2


def test_the_closing_line_rotates_per_piece_and_check_wants_the_planned_one(tmp_path):
    """Founder, 4 Nov 2026: "we are mentioning the same aaiye isko samajhte hain in every reel"; new wordings, same purpose."""
    seen = {intro.closing_for(_piece(day=date(2026, 11, d))) for d in range(5, 13)}
    assert len(seen) >= 6 and seen <= set(intro.CLOSINGS)
    assert intro.closing_for(_piece(day=date(2026, 11, 8))) != intro.closing_for(_piece(channel="arthvan", day=date(2026, 11, 8)))
    clip = tmp_path / "c.mp4"; clip.write_bytes(b"x")
    plan = {"text": "Aapki SIP doobe, phir bhi fund house kyun kamata hai? Chaliye, sach jaante hain.", "closing": "Chaliye, sach jaante hain."}
    assert intro.check(clip, plan, transcribe=lambda c: "aapki sip doobe phir bhi fund house kyun kamata hai chaliye sach jaante hain", seconds=9.9) == []
    bad = intro.check(clip, plan, transcribe=lambda c: "aapki sip doobe phir bhi fund house kyun kamata hai bye bye", seconds=9.9)
    assert any("Chaliye, sach jaante hain" in r for r in bad)


def test_a_redo_of_a_long_adopts_the_upload_of_a_run_whose_sync_failed(tmp_path, monkeypatch):
    """4 Nov 2026, run 34: the long was rebuilt and uploaded, the final sync clashed; the next redo must adopt it, not build again.
    The floor is the piece's last change before this run's own save."""
    from engine import pipeline
    p = _scheduled(tmp_path, "2026-11-07-sglearning-long", date(2026, 11, 7), with_clip=True); p.kind = "long"
    p.topic["intro"] = intro.plan(p, ask=lambda _p: "Chhote print ka ek rule"); p.updated = "2026-10-23T13:13:52+00:00"; pieces.save(p, tmp_path)
    monkeypatch.setattr(pipeline, "make", lambda *a, **k: (_ for _ in ()).throw(AssertionError("built again")))
    monkeypatch.setattr(intro, "duration", lambda path: 9.9)
    from engine import youtube
    monkeypatch.setattr(youtube, "access_token", lambda ch, env=None: "t")
    seen = {}
    def find_after(pc, token, call=None, after=None):
        seen["after"] = after; return "fresh77"
    monkeypatch.setattr(intro, "existing_upload", find_after)
    out = intro.redo_piece(p, _Deps(), tmp_path, notify=lambda t: None, transcribe=lambda c: p.topic["intro"]["text"].lower())
    assert out == "adopted-intro" and seen["after"].isoformat().startswith("2026-10-23")
    q = pieces.load(p.id, tmp_path)
    assert q.status == "uploaded" and q.ids["yt_id"] == "fresh77" and q.ids["yt_id_replaced"] == "old123"


def test_numbers_with_commas_are_spelt_out_for_the_avatar():
    """Founder, 5 Nov 2026: "error in reading digits" on 99,99,999."""
    assert intro.spell_number(25000) == "pachchees hazaar" and intro.spell_number(9999999) == "ninyaanve lakh ninyaanve hazaar nau sau ninyaanve"
    assert intro.spoken("25,000 chuhe aur 829 points, Rs 1,50,000 ka bill") == "pachchees hazaar chuhe aur 829 points, Rs ek lakh pachaas hazaar ka bill"
    p = _piece(); p.script["hook"] = "Karni Mata ke 25,000 chuhe, ek bhi bimari nahi?"
    assert intro.plan(p, ask=lambda _p: "")["text"].startswith("Karni Mata ke pachchees hazaar chuhe")


def test_the_setting_matches_the_reels_subject(tmp_path):
    """Founder, 5 Nov 2026: "RBI means RBI building, bank means any bank, shops means in market"."""
    p = _piece(); p.script["title"] = "RBI poochh raha hai, ghar ka *haal*"; p.script["hook"] = "Kya RBI sach mein poochhta hai, ghar kaisa chal raha?"
    assert "RBI headquarters" in intro.setting_for(p) and "RBI headquarters" in intro.plan(p, ask=lambda _p: "")["prompt"]
    p.script["title"] = "Sabzi ka bill aur aapki *EMI*"; p.script["hook"] = "Aapke ghar ka sabzi bill RBI ka byaaj tay karta hai?"
    assert "RBI headquarters" in intro.setting_for(p)                       # the first match in the list order wins: RBI before market
    p.script["title"] = "Subah hara, shaam laal"; p.script["hook"] = "Sensex 829 points chadha, phir bhi shaam ko laal?"
    assert "broker's office" in intro.setting_for(p)
    m = _piece(channel="arthvan"); m.script["title"] = "*Asirgarh* ke band mandir mein taaze phool"; m.script["hook"] = "Asirgarh ke mandir mein roz phool kaun chadhata hai?"
    assert intro.setting_for(m).startswith("the courtyard of the Asirgarh temple")
    k = _piece(channel="arthvan"); k.script["title"] = "Kumbhalgarh, China ke baad sabse lambi *deewar*?"; k.script["hook"] = "Kumbhalgarh ki deewar, China ke baad duniya mein sabse lambi?"
    assert intro.setting_for(k).startswith("the ramparts of Kumbhalgarh fort")
    t = _piece(channel="arthvan"); t.script["title"] = "Tirupati ke *Balaji* ka Kubera wala karza"; t.script["hook"] = "Tirupati ke Balaji, Kubera ka karza aaj bhi chuka rahe hain?"
    t.script["scenes"] = [{"vo": "Mandir ka karza, bank nahi."}]
    assert "Tirupati" in intro.setting_for(t) and "bank" not in intro.setting_for(t)      # a Myth place beats a money word
    s2 = _piece(channel="arthvan"); s2.script["title"] = "Sanchi Stupa ke andar *asthiyan* thi?"; s2.script["hook"] = "1822 mein Sanchi stupa ko khazane ke liye cheera gaya."
    assert intro.setting_for(s2).startswith("the courtyard of the Sanchi temple")
    q = _piece(); q.script["title"] = "Kuch aur"; q.script["hook"] = "Ek sawaal"; q.script["scenes"] = []
    assert intro.setting_for(q) in intro.SETTINGS["sglearning"]                 # nothing known: the rotating list
    assert intro.prompt_for(q, {"closing": "x.", "setting": "a tea stall"}).count("Setting: a tea stall") == 1


def test_a_first_upload_drops_the_other_copies_of_its_slot(tmp_path, monkeypatch):
    """5 Nov 2026: two sweeps in parallel uploaded the same piece twice; YouTube Studio showed Tirupati and Unakoti twice, Karni Mata thrice."""
    from engine import youtube
    p = _piece(); p.status = "intro-wait"; p.ids["intro_sent"] = "x"
    p.topic["intro"] = intro.plan(p, ask=lambda _p: "Aapka paisa doobta hai"); pieces.save(p, tmp_path)
    out = tmp_path / "out" / p.id; out.mkdir(parents=True); (out / "reel.mp4").write_bytes(b"reel")
    c = intro.clip_path(tmp_path, p); c.parent.mkdir(parents=True, exist_ok=True); c.write_bytes(b"clip")
    deleted = []
    monkeypatch.setattr(intro, "duration", lambda path: 9.9)
    monkeypatch.setattr(youtube, "access_token", lambda ch, env=None: "t")
    monkeypatch.setattr(youtube, "delete", lambda tok, vid: deleted.append(vid) or True)
    monkeypatch.setattr(intro, "existing_uploads", lambda pc, tok, call=None: [{"id": "twin", "uploaded": None, "duration": ""}, {"id": pc.ids["yt_id"], "uploaded": None, "duration": ""}])
    deps = _Deps(); sent = []
    action, q = intro.collect(p, deps, tmp_path, now=datetime(2026, 11, 6, 9, 0, tzinfo=timezone.utc), notify=sent.append,
                              transcribe=lambda c: p.topic["intro"]["text"].lower(), compose_fn=lambda *a: None)
    assert action == "uploaded-intro" and deleted == ["twin"] and q.ids["yt_duplicates_removed"] == ["twin"]
