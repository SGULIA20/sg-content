import base64
import io
import json
from datetime import date
from pathlib import Path

import pytest

from engine import art, artbatch, pieces

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")


def _done(n):
    rows = [{"response": {"candidates": [{"content": {"parts": [{"inlineData": {"mimeType": "image/png", "data": base64.b64encode(PNG).decode()}}]}}]}} for _ in range(n)]
    return {"metadata": {"state": "BATCH_STATE_SUCCEEDED"}, "response": {"inlinedResponses": {"inlinedResponses": rows}}}


def _piece():
    return pieces.Piece(id="2026-10-24-arthvan-long", channel="arthvan", kind="long", publish_day=date(2026, 10, 24))


def test_submit_sends_references_by_file_uri_and_one_request_per_picture(tmp_path):
    ref = tmp_path / "sg.png"; ref.write_bytes(PNG)
    seen = {}
    def post(url, body, key):
        seen["url"], seen["body"] = url, body; return 200, {"name": "batches/img1"}
    name = artbatch.submit([("a street", [ref], "4:5"), ("a face", [], "9:16")], "piece", "k", post=post, upload=lambda p, k: "https://files/sg")
    reqs = seen["body"]["batch"]["input_config"]["requests"]["requests"]
    assert name == "batches/img1" and seen["url"].endswith(f"{art.MODEL}:batchGenerateContent") and len(reqs) == 2
    assert reqs[0]["request"]["contents"][0]["parts"][0] == {"fileData": {"mimeType": "image/png", "fileUri": "https://files/sg"}}
    assert reqs[0]["request"]["contents"][0]["parts"][1]["text"] == "a street" and reqs[0]["request"]["generationConfig"]["imageConfig"]["aspectRatio"] == "4:5"
    assert reqs[1]["request"]["contents"][0]["parts"] == [{"text": "a face"}]


def test_paint_piece_fills_the_cache_at_half_price_and_paint_then_costs_nothing(tmp_path):
    jobs = [("p1", [], "4:5"), ("p2", [], "4:5"), ("p1", [], "4:5")]                      # a repeated prompt is one picture
    p = _piece(); spend = tmp_path / "s.json"
    posts = []
    out = artbatch.paint_piece(p, jobs, key="k", cache_dir=tmp_path / "c", spend=spend, today=date(2026, 10, 22),
                               post=lambda u, b, k: posts.append(len(b["batch"]["input_config"]["requests"]["requests"])) or (200, {"name": "batches/x"}),
                               get=lambda n, k: _done(2), sleep=lambda s: None, clock=lambda: 0.0)
    assert out == "ready" and posts == [2] and "art_batch" not in p.ids
    assert art.spent_today(spend, date(2026, 10, 22)) == pytest.approx(3.0)                 # 2 pictures × ₹1.5
    calls = []
    got = art.paint("p1", tmp_path / "o.png", key="k", aspect="4:5", cache_dir=tmp_path / "c", spend=spend, post=lambda *a: calls.append(1) or (500, {}))
    assert got.read_bytes() == PNG and calls == []
    assert artbatch.paint_piece(p, jobs, key="k", cache_dir=tmp_path / "c", spend=spend, today=date(2026, 10, 22), post=lambda *a: (500, {})) == "ready"


def test_paint_piece_parks_when_the_job_outlives_the_wait_and_resumes_the_same_job(tmp_path):
    p = _piece(); t = iter([0.0, 0.0, 700.0, 700.0])
    out = artbatch.paint_piece(p, [("p", [], "4:5")], key="k", cache_dir=tmp_path / "c", spend=tmp_path / "s.json", today=date(2026, 10, 22), wait_s=600,
                               post=lambda u, b, k: (200, {"name": "batches/j"}), get=lambda n, k: {"metadata": {"state": "BATCH_STATE_RUNNING"}},
                               sleep=lambda s: None, clock=lambda: next(t))
    assert out == "painting" and p.ids["art_batch"]["name"] == "batches/j"
    posts = []
    out = artbatch.paint_piece(p, [("p", [], "4:5")], key="k", cache_dir=tmp_path / "c", spend=tmp_path / "s.json", today=date(2026, 10, 22),
                               post=lambda u, b, k: posts.append(1) or (200, {"name": "batches/new"}), get=lambda n, k: _done(1), sleep=lambda s: None, clock=lambda: 0.0)
    assert out == "ready" and posts == [] and "art_batch" not in p.ids


def test_paint_piece_respects_the_daily_and_monthly_ceilings(tmp_path):
    spend = tmp_path / "s.json"
    spend.write_text(json.dumps({"2026-10-22": {"inr": 899.0, "requests": 1}}))
    with pytest.raises(art.ImageBudget):
        artbatch.paint_piece(_piece(), [("p", [], "4:5")], key="k", cache_dir=tmp_path / "c", spend=spend, today=date(2026, 10, 22), post=lambda *a: (500, {}))
    spend.write_text(json.dumps({f"2026-10-{d:02d}": {"inr": 300.0, "requests": 1} for d in range(1, 21)}))        # ₹6,000 this month already
    with pytest.raises(art.ImageBudget):
        artbatch.paint_piece(_piece(), [("p", [], "4:5")], key="k", cache_dir=tmp_path / "c", spend=spend, today=date(2026, 10, 22), post=lambda *a: (500, {}))
    with pytest.raises(art.ImageBudget):
        art.paint("q", tmp_path / "q.png", key="k", cache_dir=tmp_path / "c", spend=spend, today=date(2026, 10, 22), post=lambda *a: (500, {}))


def test_jpeg_results_are_stored_as_png(tmp_path):
    from PIL import Image
    buf = io.BytesIO(); Image.new("RGB", (4, 4), "red").save(buf, format="JPEG")
    data = {"metadata": {"state": "BATCH_STATE_SUCCEEDED"}, "response": {"inlinedResponses": {"inlinedResponses": [
        {"response": {"candidates": [{"content": {"parts": [{"inlineData": {"mimeType": "image/jpeg", "data": base64.b64encode(buf.getvalue()).decode()}}]}}]}}]}}}
    assert artbatch.collect(data, ["t1"], tmp_path, tmp_path / "s.json", date(2026, 10, 22)) == []
    assert (tmp_path / "t1.png").read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
