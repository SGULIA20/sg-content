from datetime import date, datetime, timezone

import pytest

from engine import pieces, youtube

DISCLAIMER = "Yeh investment advice nahi hai"


def _piece(kind="short", channel="sglearning"):
    p = pieces.Piece(id=f"2026-10-20-{channel}-{kind}", channel=channel, kind=kind, publish_day=date(2026, 10, 20))
    p.facts = [{"source_name": "Economic Times", "source_date": "2026-10-19", "source_url": "https://et.example/a"},
               {"source_name": "PPAC", "source_date": "2025-04-30", "source_url": "https://ppac.gov.in/x"}]
    p.script = {"hook": "Crude 100 dollar ke paar", "scenes": [{"vo": "a", "facts_used": [0]}, {"vo": "b", "facts_used": [1]}],
                "captions": {"youtube": {"title": "Crude 100 dollar: EMI par asar hoga?", "description": "Oil chadha. EMI par asar.",
                                         "tags": ["crude", "emi", "#Oil"], "chapters": ["00:00 Hook", "00:00 Asar"]}}}
    p.timings = [0.0, 31.0]
    return p


def test_short_title_keeps_suffix_within_60():
    p = _piece()
    p.script["captions"]["youtube"]["title"] = "x" * 70
    meta = youtube.metadata(p, datetime(2026, 10, 20, 14, 30, tzinfo=timezone.utc), {})
    assert meta["snippet"]["title"].endswith(" #Shorts") and len(meta["snippet"]["title"]) <= 60


def test_long_title_has_no_shorts_suffix():
    meta = youtube.metadata(_piece("long"), datetime(2026, 10, 25, 13, 30, tzinfo=timezone.utc), {})
    assert "#Shorts" not in meta["snippet"]["title"] and meta["snippet"]["categoryId"] == "22"


def test_description_lists_sources_and_disclaimer():
    d = youtube.metadata(_piece(), datetime(2026, 10, 20, 14, 30, tzinfo=timezone.utc), {})["snippet"]["description"]
    assert "Sources:" in d and "Economic Times, 2026-10-19, https://et.example/a" in d and "PPAC, 2025-04-30" in d
    assert DISCLAIMER in d and d.startswith("Crude 100 dollar ke paar")


def test_long_description_has_chapters_and_myth_has_no_disclaimer():
    p = _piece("long", "arthvan")
    d = youtube.metadata(p, datetime(2026, 10, 24, 13, 30, tzinfo=timezone.utc), {})["snippet"]["description"]
    assert "00:00 Hook" in d and "00:31 Asar" in d and DISCLAIMER not in d


def test_status_is_scheduled_private_with_synthetic_flag():
    meta = youtube.metadata(_piece(), datetime(2026, 10, 20, 14, 30, tzinfo=timezone.utc), {})
    assert meta["status"] == {"privacyStatus": "private", "publishAt": "2026-10-20T14:30:00Z",
                              "selfDeclaredMadeForKids": False, "containsSyntheticMedia": True}
    assert meta["snippet"]["tags"] == ["crude", "emi", "Oil"]


def test_unlisted_day1_has_no_publish_at():
    meta = youtube.metadata(_piece(), datetime(2026, 10, 20, 14, 30, tzinfo=timezone.utc), {"UNLISTED_DAY1": "1"})
    assert meta["status"]["privacyStatus"] == "unlisted" and "publishAt" not in meta["status"]


def test_upload_resumable_flow(tmp_path):
    video = tmp_path / "v.mp4"; video.write_bytes(b"mp4bytes")
    calls = []

    def call(method, url, token, json_body=None, data=None, headers=None):
        calls.append((method, url, headers or {}))
        if method == "POST":
            return 200, {"location": "https://upload.example/session"}, {}
        return 200, {}, {"id": "vid123"}

    assert youtube.upload("tok", video, {"snippet": {}}, call=call) == "vid123"
    assert calls[0][0] == "POST" and calls[0][2]["X-Upload-Content-Length"] == "8"
    assert calls[1] == ("PUT", "https://upload.example/session", {"Content-Type": "video/mp4"})


def test_upload_without_session_raises(tmp_path):
    video = tmp_path / "v.mp4"; video.write_bytes(b"x")
    with pytest.raises(youtube.YouTubeError):
        youtube.upload("tok", video, {}, call=lambda *a, **k: (500, {}, {}))


def test_thumbnail_403_returns_false(tmp_path):
    jpg = tmp_path / "t.jpg"; jpg.write_bytes(b"jpg")
    assert youtube.set_thumbnail("tok", "vid", jpg, call=lambda *a, **k: (403, {}, {"error": "forbidden"})) is False
    assert youtube.set_thumbnail("tok", "vid", jpg, call=lambda *a, **k: (200, {}, {"items": []})) is True


def test_access_token_uses_channel_refresh_token():
    seen = {}

    def post(url, form):
        seen.update(form); return {"access_token": "at"}

    env = {"YT_CLIENT_ID": "cid", "YT_CLIENT_SECRET": "sec", "YT_ARTHVAN_REFRESH_TOKEN": "rt-a", "YT_SGLEARNING_REFRESH_TOKEN": "rt-s"}
    assert youtube.access_token("arthvan", env, post=post) == "at" and seen["refresh_token"] == "rt-a"


def test_description_hashtags_come_from_allowed_list_not_tags():
    p = _piece(); p.script["captions"]["youtube"]["tags"] = ["bjp", "modi"]
    d = youtube.metadata(p, datetime(2026, 10, 20, 14, 30, tzinfo=timezone.utc), {})["snippet"]["description"]
    assert "#bjp" not in d and "#Finance" in d


def test_go_public_updates_privacy():
    seen = []
    def call(method, url, token, json_body=None, data=None, headers=None):
        seen.append((method, url, json_body)); return 200, {}, {"id": "v1"}
    assert youtube.go_public("tok", "v1", call=call) is True
    assert seen[0][0] == "PUT" and seen[0][2]["status"]["privacyStatus"] == "public" and seen[0][2]["id"] == "v1"


def test_unlisted_kinds_upload_unlisted_without_publish_at(monkeypatch):
    from engine import config
    monkeypatch.setattr(config, "UNLISTED_KINDS", {"long"})
    meta = youtube.metadata(_piece("long"), datetime(2026, 10, 25, 13, 30, tzinfo=timezone.utc), {})
    assert meta["status"]["privacyStatus"] == "unlisted" and "publishAt" not in meta["status"]
    meta = youtube.metadata(_piece(), datetime(2026, 10, 20, 14, 30, tzinfo=timezone.utc), {})
    assert meta["status"]["privacyStatus"] == "private"


def test_description_has_three_hashtags_first_and_cta():
    p = _piece()
    d = youtube.metadata(p, datetime(2026, 10, 20, 14, 30, tzinfo=timezone.utc), {})["snippet"]["description"]
    paras = d.split("\n\n")
    assert paras[0].startswith("Crude 100 dollar") and paras[1].count("#") == 3 and "Subscribe" in d and d.count("#") <= 15


def test_description_links_both_channels():
    d = youtube.metadata(_piece(), datetime(2026, 10, 20, 14, 30, tzinfo=timezone.utc), {})["snippet"]["description"]
    assert "youtube.com/@sanjeev_gulia" in d and "youtube.com/@sgmythworld" in d and d.count("#") <= 15
