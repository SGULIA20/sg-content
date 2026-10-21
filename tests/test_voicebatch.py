import base64
import io
import json
import wave
from datetime import date

import pytest

from engine import pieces, voice, voicebatch


def _wav(seconds=0.5, rate=24000):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate); w.writeframes(b"\x01\x00" * int(seconds * rate))
    return buf.getvalue()


def _done(texts):
    rows = [{"response": {"candidates": [{"content": {"parts": [{"inlineData": {"mimeType": "audio/wav", "data": base64.b64encode(_wav()).decode()}}]}}]}} for _ in texts]
    return {"metadata": {"state": "BATCH_STATE_SUCCEEDED"}, "response": {"inlinedResponses": {"inlinedResponses": rows}}}


def _piece():
    return pieces.Piece(id="2026-10-24-arthvan-long", channel="arthvan", kind="long", publish_day=date(2026, 10, 24))


def test_submit_builds_one_request_per_line_with_the_right_voice_config():
    seen = {}
    def post(url, body, key):
        seen["url"], seen["body"] = url, body; return 200, {"name": "batches/abc"}
    assert voicebatch.submit(["ek", "do"], "voice_7o0kddoq6q2z", "piece-1", key="k", post=post) == "batches/abc"
    reqs = seen["body"]["batch"]["input_config"]["requests"]["requests"]
    assert seen["url"].endswith("gemini-3.8-flash-tts:batchGenerateContent") and len(reqs) == 2
    assert reqs[0]["request"]["contents"][0]["parts"][0]["text"] == "ek"
    assert reqs[0]["request"]["generationConfig"]["speechConfig"]["voiceConfig"] == {"voice": "voice_7o0kddoq6q2z"}
    voicebatch.submit(["ek"], "Kore", "p", key="k", post=post)
    assert seen["body"]["batch"]["input_config"]["requests"]["requests"][0]["request"]["generationConfig"]["speechConfig"]["voiceConfig"] == {"prebuiltVoiceConfig": {"voiceName": "Kore"}}


def test_voice_piece_waits_collects_into_the_cache_and_say_then_costs_nothing(tmp_path):
    texts = ["Namaste.", "Doosri line."]
    p = _piece()
    states = iter([{"metadata": {"state": "BATCH_STATE_RUNNING"}}, _done(texts)])
    slept = []
    out = voicebatch.voice_piece(p, texts, "Kore", key="k", cache_dir=tmp_path / "c", post=lambda u, b, k: (200, {"name": "batches/x"}),
                                 get=lambda name, key: next(states), sleep=slept.append, clock=lambda: 0.0)
    assert out == "ready" and slept == [voicebatch.POLL_S] and "voice_batch" not in p.ids
    calls = []
    d = voice.say("Namaste.", "Kore", tmp_path / "a.wav", key="k", cache_dir=tmp_path / "c", budget=tmp_path / "b.json",
                  post=lambda *a: calls.append(1) or (500, {}))
    assert d == pytest.approx(0.5) and calls == []                                   # served from the batch result, no request


def test_voice_piece_parks_the_piece_when_the_job_outlives_the_wait(tmp_path):
    p = _piece()
    t = iter([0.0, 0.0, 700.0, 700.0])
    out = voicebatch.voice_piece(p, ["a"], "Kore", key="k", cache_dir=tmp_path / "c", wait_s=600, post=lambda u, b, k: (200, {"name": "batches/j1"}),
                                 get=lambda name, key: {"metadata": {"state": "BATCH_STATE_RUNNING"}}, sleep=lambda s: None, clock=lambda: next(t))
    assert out == "voicing" and p.ids["voice_batch"] == {"name": "batches/j1", "voice": "Kore", "lines": 1, "tries": 1}
    # next run: the same job is polled, not resubmitted
    posts = []
    out = voicebatch.voice_piece(p, ["a"], "Kore", key="k", cache_dir=tmp_path / "c", post=lambda u, b, k: posts.append(1) or (200, {"name": "batches/j2"}),
                                 get=lambda name, key: _done(["a"]), sleep=lambda s: None, clock=lambda: 0.0)
    assert out == "ready" and posts == []


def test_a_failed_job_is_resubmitted_once_then_raises(tmp_path):
    p = _piece()
    names = iter(["batches/f1", "batches/f2"])
    with pytest.raises(voicebatch.BatchError):
        voicebatch.voice_piece(p, ["a"], "Kore", key="k", cache_dir=tmp_path / "c", post=lambda u, b, k: (200, {"name": next(names)}),
                               get=lambda name, key: {"metadata": {"state": "BATCH_STATE_FAILED"}}, sleep=lambda s: None, clock=lambda: 0.0)
    assert "voice_batch" not in p.ids


def test_submit_error_is_a_batch_error():
    with pytest.raises(voicebatch.BatchError):
        voicebatch.submit(["a"], "Kore", "p", key="k", post=lambda u, b, k: (429, {"error": {"message": "quota"}}))
