import json
from datetime import date

from engine import intro, postmortem, pieces, writer

TODAY = date(2026, 12, 7)


def _call(method, url, token, **k):
    if "dimensions=video" in url:
        return 200, {}, {"rows": [["A1", 300, 62.0, 31], ["B2", 9, 20.0, 6]]}
    if "elapsedVideoTimeRatio" in url:
        return 200, {}, {"rows": [[0.01, 1.0], [0.05, 0.7], [0.1, 0.55], [0.25, 0.4], [0.5, 0.3], [0.75, 0.22], [1.0, 0.15]]}
    raise AssertionError(url)


def _piece(root, pid, yt, title, opening):
    ch, kind = pid.split("-")[3], pid.split("-")[4]
    p = pieces.Piece(id=pid, channel=ch, kind=kind, publish_day=date.fromisoformat(pid[:10])); p.status = "posted"; p.ids["yt_id"] = yt
    p.script = {"title": title, "scenes": [{"vo": "Pehli line."}, {"vo": "Doosri line."}]}; p.topic = {"intro": {"text": opening}}
    pieces.save(p, root)


def test_last_weeks_videos_are_reviewed_with_their_retention_and_the_viral_thumbnails(tmp_path):
    """Founder, 24 Nov 2026: 'Build the weekly post-mortem next'."""
    _piece(tmp_path, "2026-12-03-arthvan-short", "A1", "Trojan Horse *sach* tha?", "Ek ghoda. Lakdi ka. Kyun?")
    _piece(tmp_path, "2026-12-04-arthvan-short", "B2", "Lemming kyun kudte hain?", "Ek film ne badnaam kiya.")
    _piece(tmp_path, "2026-11-01-arthvan-short", "OLD", "purana", "x")                                  # outside the window
    (tmp_path / "content").mkdir()
    (tmp_path / "content" / "weekly-plan.json").write_text(json.dumps({"viral": {"arthvan": [{"id": "VID1", "title": "Japan Ramayana", "views": 9700000}]}}))
    asked, sent = [], []
    def ask(content):
        asked.append(content)
        return "```json\n" + json.dumps({"lessons": ["Name the thing in the first three words."], "thumbnail_look": "One big object, three yellow words.",
                                          "best": "Trojan Horse", "worst": "Lemming", "report": "Trojan Horse held 55% at the 10% mark."}) + "\n```"
    out = tmp_path / "pm.json"
    got = postmortem.run(tmp_path, TODAY, {}, ask=ask, notify=sent.append, token_for=lambda ch, env=None: "t", call=_call, out=out, ig_collect=lambda *a: [])
    arth = next(c for c in asked if "SG-MYTH-WORLD" in c[0]["text"])
    assert "Trojan Horse sach tha?" in arth[0]["text"] and '"10%": 55' in arth[0]["text"] and "purana" not in arth[0]["text"]
    assert '"still_watching"' not in arth[0]["text"].split("Lemming")[1].split("}")[0]                # nine views: no curve is drawn from them
    assert arth[1] == {"type": "image", "source": {"type": "url", "url": "https://i.ytimg.com/vi/VID1/hqdefault.jpg"}}
    assert got["arthvan"]["lessons"] == ["Name the thing in the first three words."] and json.loads(out.read_text())["date"] == "2026-12-07"
    assert "Weekly post-mortem" in sent[0] and "Trojan Horse held 55%" in sent[0] and "Learning with SG: no published videos" in sent[0]
    assert postmortem.lessons("arthvan", TODAY, out) == ["Name the thing in the first three words."]
    assert postmortem.lessons("arthvan", date(2026, 12, 25), out) == [] and postmortem.thumbnail_look("arthvan", date(2026, 12, 25), out) == ""   # stale: no longer followed
    assert postmortem.thumbnail_look("arthvan", TODAY, out).startswith("One big object")


def test_the_writers_and_the_thumbnail_prompt_read_the_lessons(tmp_path, monkeypatch):
    out = tmp_path / "pm.json"
    out.write_text(json.dumps({"date": date.today().isoformat(), "sglearning": {"lessons": ["Open on the number."], "thumbnail_look": "A face-sized object, two words."}}))
    monkeypatch.setattr(postmortem, "OUT", out)
    assert writer.week_lessons("sglearning")["lessons"] == ["Open on the number."] and writer.week_lessons("arthvan") == {}
    p = pieces.Piece(id="2026-12-09-sglearning-long", channel="sglearning", kind="long", publish_day=date(2026, 12, 9))
    p.script = {"title": "2008 ki mandi mein kya hua tha?", "hook": "h", "scenes": []}
    assert "A face-sized object, two words." in intro.thumb_prompt(p) and "no presenter" in intro.thumb_prompt(p)
    a = pieces.Piece(id="2026-12-10-arthvan-long", channel="arthvan", kind="long", publish_day=date(2026, 12, 10)); a.script = {"title": "Giza", "scenes": []}
    assert "most-viewed thumbnails" not in intro.thumb_prompt(a)


def test_every_morning_yesterdays_videos_are_reviewed_with_instagram_numbers_and_he_hears_only_what_changed(tmp_path):
    """Founder, 24 Nov 2026: 'I want you to review each reel or long video you are posting and take necessary actions for next reel'."""
    _piece(tmp_path, "2026-12-06-arthvan-short", "A1", "Marco Polo aur pasta", "Pasta China se aaya? Jhooth.")
    asked, sent = [], []
    reply = json.dumps({"lessons": ["Open on the name everyone knows.", "Cut the second scene's list."], "thumbnail_look": "", "best": "b", "worst": "w", "report": "r"})
    ig = lambda start, end, env, root: [{"id": "2026-12-06-arthvan-short", "ig_views": 410, "ig_skip_rate": 38.0, "ig_watch_s": 14.2}]
    kw = dict(ask=lambda c: asked.append(c) or reply, notify=sent.append, token_for=lambda ch, env=None: "t", call=_call, out=tmp_path / "pm.json", daily=True, ig_collect=ig)
    postmortem.run(tmp_path, TODAY, {}, **kw)
    arth = next(c for c in asked if "SG-MYTH-WORLD" in c[0]["text"])[0]["text"]
    assert '"ig_skipped_early_pct": 38.0' in arth and '"ig_views": 410' in arth and "swiped away in the first three seconds" in arth
    assert len(sent) == 1 and "Yesterday's videos reviewed" in sent[0] and "• Open on the name everyone knows." in sent[0] and "every video written from today" in sent[0]
    postmortem.run(tmp_path, TODAY, {}, **kw)
    assert len(sent) == 1                                                                              # the same lessons the next morning: nothing is sent
    assert postmortem.lessons("arthvan", TODAY, tmp_path / "pm.json")[0] == "Open on the name everyone knows."
