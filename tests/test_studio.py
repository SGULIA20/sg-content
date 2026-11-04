import time
from pathlib import Path

from engine import studio

CFG = {"token": "TOK", "chat_id": "42"}


def _upd(uid, chat=42, caption=None, text=None, video=False, photo=False, document=None):
    m = {"chat": {"id": chat}, "date": int(time.time())}
    if caption is not None: m["caption"] = caption
    if text is not None: m["text"] = text
    if video: m["video"] = {"file_id": "V1", "file_size": 5_000_000, "duration": 10, "mime_type": "video/mp4"}
    if photo: m["photo"] = [{"file_id": "P-small", "file_size": 100}, {"file_id": "P1", "file_size": 900}]
    if document: m["document"] = document
    return {"update_id": uid, "message": m}


def _run(tmp_path, updates, **over):
    sent, confirmed, fetched, commits = [], [], [], []
    def call(token, method, body):
        if method == "getUpdates" and "offset" in body: confirmed.append(body["offset"]); return {"result": []}
        if method == "getUpdates": return {"result": updates}
        return {"ok": True}
    def fetch(cfg, file_id, out, call_):
        rel = str(out.relative_to(tmp_path)) if tmp_path in out.parents else out.name
        fetched.append((file_id, rel)); out.parent.mkdir(parents=True, exist_ok=True); out.write_bytes(b"x" * 10); return out
    def commit(root, message, paths=None, **k): commits.append((message, paths))
    import functools
    kw = dict(intro_fn=functools.partial(studio.intro_reply, fetch=fetch, commit=commit),
              thumb_fn=functools.partial(studio.thumb_reply, fetch=fetch, commit=commit, token_for=lambda ch, env=None: "yt-token",
                                         set_thumb=lambda tok, vid, jpg: True),
              xray_fn=functools.partial(studio.xray_reply, fetch=fetch, commit=commit, analyse=lambda path, note: "HOOK: ..."))
    kw.update(over)
    done = studio.poll(CFG, tmp_path, call=call, send_fn=sent.append, **kw)
    return done, sent, confirmed, fetched, commits


def test_an_intro_file_is_saved_under_its_piece_id_and_pushed(tmp_path):
    doc = {"file_id": "D1", "file_size": 9_000_000, "mime_type": "video/mp4"}
    done, sent, confirmed, fetched, commits = _run(tmp_path, [_upd(9, caption="Intro 2026-11-07-sglearning-short", document=doc)])
    assert done == [("intro", "2026-11-07-sglearning-short")] and confirmed == [10]
    assert fetched == [("D1", "inbox/intro/2026-11-07-sglearning-short.mp4")] and commits[0][1] == ["inbox/intro"]
    assert sent[0].startswith("🎬 Intro for 2026-11-07-sglearning-short saved")


def test_a_thumbnail_is_saved_and_set_on_youtube_when_the_piece_is_uploaded(tmp_path):
    from engine import pieces
    from datetime import date
    p = pieces.Piece(id="2026-11-09-sglearning-long", channel="sglearning", kind="long", publish_day=date(2026, 11, 9), status="uploaded")
    p.ids["yt_id"] = "abc"; pieces.save(p, tmp_path)
    done, sent, _c, fetched, commits = _run(tmp_path, [_upd(3, caption="thumb 2026-11-09-sglearning-long", photo=True)])
    assert done == [("thumb", "2026-11-09-sglearning-long")] and fetched[0][0] == "P1" and commits[0][1] == ["inbox/thumb"]
    assert "set on YouTube" in sent[0]


def test_other_videos_get_the_xray_strangers_are_cleared_and_text_gets_help(tmp_path):
    done, sent, confirmed, _f, _c = _run(tmp_path, [_upd(1, video=True, caption="canwe.ai hook"), _upd(2, chat=99, video=True), _upd(3, text="/help")])
    assert [d[0] for d in done] == ["xray", "help"] and confirmed == [2, 3, 4]
    assert sent[0].startswith("🎬 Got the Reel") and sent[1].startswith("🎬 Reel X-ray") and "intro <piece id>" in sent[2]


def test_an_intro_over_20_mb_is_refused(tmp_path):
    m = _upd(5, caption="intro 2026-11-07-sglearning-short", video=True)["message"]; m["video"]["file_size"] = 25_000_000
    assert studio.intro_reply(CFG, m, "2026-11-07-sglearning-short", tmp_path, fetch=lambda *a: None, commit=lambda *a, **k: None).startswith("🎬 That intro is over 20 MB")
