import json
from datetime import date

import pytest

from engine import pieces, subtitles


def _piece():
    p = pieces.Piece(id="2026-10-21-sglearning-long", channel="sglearning", kind="long", publish_day=date(2026, 10, 21))
    p.script = {"scenes": [{"vo": "Papa ne 20 saal pehle 5 lakh FD mein rakhe. Byaaj 7 percent, sab khush."},
                           {"vo": "Lekin mehngai 6 percent thi, toh asli kamai sirf 1 percent, matlab lagbhag kuch nahi, aur yeh baat kisi ne unko nahi batayi kabhi."}]}
    p.timings = [0.0, 10.0]
    p.ids = {"yt_id": "vid1"}
    return p


def test_cues_split_scenes_by_word_share_and_cover_the_clip():
    c = subtitles.cues(_piece(), duration=22.0)
    assert c[0][0] == 0.0 and c[-1][1] == 22.0
    assert all(e > s for s, e, _t in c) and all(len(t.split()) <= 16 for _s, _e, t in c)
    assert c[0][2].startswith("Papa ne 20 saal") and any(t.startswith("Lekin mehngai") for _s, _e, t in c)
    starts = [s for s, _e, _t in c]
    assert starts == sorted(starts) and 10.0 in starts


def test_srt_format_and_timestamps():
    text = subtitles.srt([(0.0, 1.5, "Namaste"), (61.25, 3600.0, "Bye")])
    assert text.startswith("1\n00:00:00,000 --> 00:00:01,500\nNamaste\n") and "2\n00:01:01,250 --> 01:00:00,000\nBye" in text


def test_write_all_translates_each_language_once(tmp_path):
    calls = []
    def fake_translate(lines, lang):
        calls.append(lang); return [f"{lang}:{ln}" for ln in lines]
    paths = subtitles.write_all(_piece(), tmp_path, langs=["en", "hi"], duration=22.0, translate_fn=fake_translate)
    assert set(paths) == {"en", "hi"} and (tmp_path / "subs" / "hi-Latn.srt").exists()
    assert "en:Papa ne 20 saal" in paths["en"].read_text()
    subtitles.write_all(_piece(), tmp_path, langs=["en", "hi"], duration=22.0, translate_fn=fake_translate)
    assert calls == ["en", "hi"]                                                   # cached on disk, not translated twice


def test_translate_keeps_count_and_parses_json_array():
    class FakeClient:
        class messages:
            @staticmethod
            def create(**kw):
                lines = json.loads(kw["messages"][0]["content"])
                class R: content = [type("B", (), {"text": "Here: " + json.dumps([l.upper() for l in lines])})()]
                return R()
    assert subtitles.translate(["ek do", "teen"], "en", client=FakeClient()) == ["EK DO", "TEEN"]


def test_upload_builds_multipart_and_maps_403_to_scope_hint(tmp_path):
    srt = tmp_path / "en.srt"; srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nHi\n")
    seen = {}
    def call(method, url, token, json_body=None, data=None, headers=None):
        seen.update(method=method, url=url, data=data, headers=headers); return 200, {}, {"id": "cap1"}
    assert subtitles.upload("tok", "vid1", "en", srt, call=call) == "cap1"
    assert seen["method"] == "POST" and "captions" in seen["url"] and seen["headers"]["Content-Type"].startswith("multipart/related")
    assert b'"videoId": "vid1"' in seen["data"] and b'"language": "en"' in seen["data"] and b"00:00:01,000" in seen["data"]
    with pytest.raises(subtitles.SubtitleError, match="force-ssl"):
        subtitles.upload("tok", "vid1", "en", srt, call=lambda *a, **k: (403, {}, {"error": "insufficient scope"}))


def test_upload_all_skips_done_tracks_and_records_ids(tmp_path):
    p = _piece(); p.ids["captions"] = {"en": "old"}
    for lang in ("en", "hi"):
        (tmp_path / f"{lang}.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\nx\n")
    uploaded = []
    def call(method, url, token, json_body=None, data=None, headers=None):
        uploaded.append(data); return 200, {}, {"id": f"cap{len(uploaded)}"}
    done = subtitles.upload_all("tok", p, {"en": tmp_path / "en.srt", "hi": tmp_path / "hi.srt"}, call=call)
    assert done == {"en": "old", "hi": "cap1"} and p.ids["captions"] == done and len(uploaded) == 1
