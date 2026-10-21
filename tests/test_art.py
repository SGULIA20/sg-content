import base64
import json
from datetime import date

import pytest

from engine import art

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")


class FakePost:
    def __init__(self):
        self.calls = []

    def __call__(self, url, body, key):
        self.calls.append((url, body))
        return 200, {"candidates": [{"content": {"parts": [{"inlineData": {"mimeType": "image/png", "data": base64.b64encode(PNG).decode()}}]}}]}


def test_paint_is_cached_by_prompt(tmp_path):
    fp = FakePost()
    kw = dict(key="k", cache_dir=tmp_path / "cache", spend=tmp_path / "spend.json", post=fp, today=date(2026, 10, 20))
    a = art.paint("a calm desk", tmp_path / "a.png", **kw)
    b = art.paint("a calm desk", tmp_path / "b.png", **kw)
    assert a.read_bytes() == PNG and b.read_bytes() == PNG and len(fp.calls) == 1
    assert art.spent_today(tmp_path / "spend.json", date(2026, 10, 20)) == pytest.approx(3.0)


def test_paint_sends_references_inline(tmp_path):
    fp = FakePost()
    ref = tmp_path / "ref.jpg"; ref.write_bytes(b"\xff\xd8jpegdata")
    art.paint("same man smiling", tmp_path / "a.png", refs=[ref], key="k", cache_dir=tmp_path / "c", spend=tmp_path / "s.json", post=fp)
    parts = fp.calls[0][1]["contents"][0]["parts"]
    assert parts[0]["inlineData"]["mimeType"] == "image/jpeg" and parts[-1]["text"].startswith("same man smiling")
    assert fp.calls[0][1]["generationConfig"]["responseModalities"] == ["IMAGE"]
    assert fp.calls[0][0].endswith("models/gemini-3.1-flash-lite-image:generateContent")


def test_image_budget_stops_at_cap(tmp_path):
    fp = FakePost()
    spend = tmp_path / "s.json"
    spend.write_text(json.dumps({"2026-10-20": {"inr": 898.5, "requests": 300}}))
    kw = dict(key="k", cache_dir=tmp_path / "c", spend=spend, post=fp, today=date(2026, 10, 20))
    art.paint("p1", tmp_path / "1.png", **kw)                         # 898.5 + 3 allowed (was under the cap before)
    with pytest.raises(art.ImageBudget):
        art.paint("p2", tmp_path / "2.png", **kw)
    assert len(fp.calls) == 1


def test_commons_rejects_non_free_licence(tmp_path):
    def fetch(url):
        if "generator=search" in url:
            return json.dumps({"query": {"pages": {"1": {"title": "File:A.jpg", "imageinfo": [{"url": "https://u/a.jpg", "extmetadata": {
                "LicenseShortName": {"value": "CC BY-NC 4.0"}, "Artist": {"value": "X"}}}]},
                "2": {"title": "File:B.jpg", "imageinfo": [{"url": "https://u/b.jpg", "extmetadata": {
                    "LicenseShortName": {"value": "CC BY-SA 4.0"}, "Artist": {"value": "<a href='x'>Photographer</a>"}}}]}}}}).encode()
        return PNG
    got = art.commons_photo("Dwarka underwater", tmp_path, fetch=fetch)
    assert got["credit"] == "Photographer, CC BY-SA 4.0, Wikimedia Commons" and got["path"].read_bytes() == PNG
    assert got["title"] == "File:B.jpg"


def test_commons_returns_none_when_nothing_free(tmp_path):
    fetch = lambda url: json.dumps({"query": {"pages": {"1": {"title": "File:A.jpg", "imageinfo": [{"url": "https://u/a.jpg", "extmetadata": {
        "LicenseShortName": {"value": "Fair use"}}}]}}}}).encode()
    assert art.commons_photo("x", tmp_path, fetch=fetch) is None


def test_avatar_uses_three_reference_photos(tmp_path):
    fp = FakePost()
    refdir = tmp_path / "reference"; refdir.mkdir()
    for i in range(1, 23):
        (refdir / f"founder-{i:02d}.jpg").write_bytes(b"\xff\xd8" + bytes([i]))
    (tmp_path / "avatar-library.yaml").write_text("explaining_front:\n  prompt: explaining to camera\n  refs: [founder-01.jpg, founder-05.jpg, founder-11.jpg]\n")
    out = art.avatar("explaining_front", assets=tmp_path, library=tmp_path / "avatar-library.yaml", key="k", spend=tmp_path / "s.json", post=fp)
    assert out == tmp_path / "avatar" / "explaining_front.png" and out.exists()
    parts = fp.calls[0][1]["contents"][0]["parts"]
    assert sum(1 for p in parts if "inlineData" in p) == 3
    art.avatar("explaining_front", assets=tmp_path, library=tmp_path / "avatar-library.yaml", key="k", spend=tmp_path / "s.json", post=fp)
    assert len(fp.calls) == 1                                                  # generated once, reused


def test_avatar_unknown_pose_raises(tmp_path):
    (tmp_path / "avatar-library.yaml").write_text("explaining_front:\n  prompt: x\n  refs: [a.jpg]\n")
    with pytest.raises(KeyError):
        art.avatar("dancing", assets=tmp_path, library=tmp_path / "avatar-library.yaml", key="k")


def test_library_has_thirty_poses_with_real_refs():
    lib = art.load_library()
    assert len(lib) >= 30
    for pose, spec in lib.items():
        assert len(spec["refs"]) == 3 and all((art.ASSETS_DIR / "reference" / r).exists() for r in spec["refs"]), pose
