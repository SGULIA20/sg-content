import json
from datetime import date

import pytest

from engine import digest, linkedin, pieces

URN = "urn:li:person:abc"


class FakeCall:
    def __init__(self, parts=1, statuses=("PROCESSING", "AVAILABLE"), size=10):
        self.calls, self.parts, self.statuses, self.size = [], parts, list(statuses), size

    def __call__(self, method, url, token, body=None, data=None, headers=None):
        self.calls.append({"method": method, "url": url, "body": body, "data": data, "headers": dict(headers or {})})
        if "initializeUpload" in url:
            step = -(-self.size // self.parts)
            ins = [{"uploadUrl": f"https://up/{i}", "firstByte": i * step, "lastByte": min(self.size, (i + 1) * step) - 1} for i in range(self.parts)]
            return {}, {"value": {"video": "urn:li:video:v1", "uploadToken": "ut", "uploadInstructions": ins}}
        if url.startswith("https://up/"):
            return {"etag": "etag" + url[-1]}, {}
        if "finalizeUpload" in url:
            return {}, {}
        if url.startswith("/videos/"):
            return {}, {"status": self.statuses.pop(0)}
        if url == "/posts":
            return {"x-restli-id": "urn:li:share:7"}, {}
        raise AssertionError(url)


def _video(tmp_path, size=10):
    f = tmp_path / "reel.mp4"
    f.write_bytes(bytes(range(size)))
    return f


def test_post_video_sequence_and_headers(tmp_path):
    fc = FakeCall()
    out = linkedin.post_video(URN, "tok", _video(tmp_path), "hello", "Title", call=fc, sleep=lambda s: None, ver="202606")
    assert out == "urn:li:share:7"
    seq = [c["url"].split("?")[-1] if "?" in c["url"] else c["url"] for c in fc.calls]
    assert seq == ["action=initializeUpload", "https://up/0", "action=finalizeUpload", "/videos/urn%3Ali%3Avideo%3Av1", "/videos/urn%3Ali%3Avideo%3Av1", "/posts"]
    init = fc.calls[0]["body"]["initializeUploadRequest"]
    assert init["owner"] == URN and init["fileSizeBytes"] == 10
    for c in fc.calls:
        if not c["url"].startswith("https://up/"):
            assert c["headers"]["LinkedIn-Version"] == "202606" and c["headers"]["X-Restli-Protocol-Version"] == "2.0.0"
    assert fc.calls[1]["method"] == "PUT" and fc.calls[1]["data"] == bytes(range(10))
    post = fc.calls[-1]["body"]
    assert post["author"] == URN and post["visibility"] == "PUBLIC" and post["lifecycleState"] == "PUBLISHED"
    assert post["distribution"]["feedDistribution"] == "MAIN_FEED" and post["content"]["media"] == {"title": "Title", "id": "urn:li:video:v1"}


def test_multi_part_upload_sends_slices_and_etags(tmp_path):
    fc = FakeCall(parts=3, statuses=("AVAILABLE",), size=10)
    linkedin.post_video(URN, "tok", _video(tmp_path), "x", "T", call=fc, sleep=lambda s: None, ver="202606")
    puts = [c for c in fc.calls if c["method"] == "PUT"]
    assert b"".join(c["data"] for c in puts) == bytes(range(10)) and len(puts) == 3
    fin = next(c for c in fc.calls if "finalizeUpload" in c["url"])["body"]["finalizeUploadRequest"]
    assert fin == {"video": "urn:li:video:v1", "uploadToken": "ut", "uploadedPartIds": ["etag0", "etag1", "etag2"]}


def test_processing_failure_and_bounded_wait(tmp_path):
    with pytest.raises(linkedin.LinkedInError, match="failed"):
        linkedin.post_video(URN, "t", _video(tmp_path), "x", "T", call=FakeCall(statuses=("PROCESSING_FAILED",)), sleep=lambda s: None)
    fc = FakeCall(statuses=["PROCESSING"] * 5)
    with pytest.raises(linkedin.LinkedInError, match="not AVAILABLE"):
        linkedin.post_video(URN, "t", _video(tmp_path), "x", "T", call=fc, sleep=lambda s: None, max_polls=5)
    assert not any(c["url"] == "/posts" for c in fc.calls)


def test_text_over_limit_is_refused(tmp_path):
    with pytest.raises(linkedin.LinkedInError):
        linkedin.post_video(URN, "t", _video(tmp_path), "y" * 3001, "T", call=FakeCall(), sleep=lambda s: None)


def test_escape_reserved_characters():
    assert linkedin.escape("a (b) [c] {d} <e> @f #g *h _i ~j |k \\l") == "a \\(b\\) \\[c\\] \\{d\\} \\<e\\> \\@f \\#g \\*h \\_i \\~j \\|k \\\\l"


def _piece(channel="sglearning", text="Dividend (free?) liya. Yeh investment advice nahi hai. #PaiseKiKhabar #Finance", yt="ab_c"):
    p = pieces.Piece(id=f"2026-10-21-{channel}-short", channel=channel, kind="short", publish_day=date(2026, 10, 21))
    p.ids = {"yt_id": yt} if yt else {}
    p.script = {"title": "t", "captions": {"youtube": {"title": "Dividend ka ₹6.50 free hai?", "description": "", "tags": [], "chapters": []},
                                           "instagram": {"caption": "c\nYeh investment advice nahi hai", "hashtags": ["#Paise_Ki", "#B", "#C", "#D"]},
                                           "threads": {"text": text}}}
    return p


def test_text_for_content():
    t = linkedin.text_for(_piece())
    assert t.startswith("Dividend ka ₹6.50 free hai?\n\n") and "Dividend \\(free?\\) liya." in t
    assert "#PaiseKiKhabar" not in t and "#Finance" not in t
    assert t.count("Yeh investment advice nahi hai") == 1
    assert "https://youtu.be/ab\\_c" in t
    assert t.endswith("{hashtag|\\#|Paise_Ki} {hashtag|\\#|B} {hashtag|\\#|C}")


def test_text_for_adds_disclaimer_only_for_finance_and_link_only_with_yt_id():
    t = linkedin.text_for(_piece(text="Dividend liya."))
    assert "Yeh investment advice nahi hai." in t
    m = linkedin.text_for(_piece(channel="arthvan", text="Ram Setu kya hai?", yt=None))
    assert "investment advice" not in m and "youtu.be" not in m


def test_text_for_stays_under_limit():
    t = linkedin.text_for(_piece(text="(x) " * 2000))
    assert len(t) <= linkedin.MAX_TEXT and "youtu.be" in t and t.endswith("{hashtag|\\#|C}")
    assert "\\(x\\)" in t and not t.split("\n\n")[1].rstrip("…").endswith("\\")


def test_record_expiry_keeps_other_dates_and_digest_alerts(tmp_path):
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / "tokens.json").write_text(json.dumps({"instagram_expires": "2026-12-01"}))
    assert linkedin.record_expiry(5184000, tmp_path, date(2026, 8, 26)) == "2026-10-25"
    data = json.loads((tmp_path / "logs" / "tokens.json").read_text())
    assert data == {"instagram_expires": "2026-12-01", "linkedin_expires": "2026-10-25"}
    alerts = digest.alerts(tmp_path, date(2026, 10, 20))
    assert any("LinkedIn token" in a and "--auth" in a for a in alerts) and not any("Instagram token" in a for a in alerts)


def test_configured_needs_both_secrets(tmp_path, monkeypatch):
    from engine import secrets
    monkeypatch.setattr(secrets, "DOTENV", tmp_path / ".env")
    assert not linkedin.configured({"LINKEDIN_ACCESS_TOKEN": "tok123"})
    assert linkedin.configured({"LINKEDIN_ACCESS_TOKEN": "tok123", "LINKEDIN_PERSON_URN": URN})


def test_version_overridable():
    assert linkedin.version({"LINKEDIN_VERSION": "202701"}) == "202701" and linkedin.version({}) == linkedin.DEFAULT_VERSION
