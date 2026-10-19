import base64
import io
import json
import wave
from datetime import date

import pytest

from engine import voice


def _wav_bytes(seconds=1.0, rate=24000):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes(b"\x00\x00" * int(seconds * rate))
    return buf.getvalue()


class FakePost:
    def __init__(self):
        self.calls = []

    def __call__(self, url, body, key):
        self.calls.append((url, body))
        if url.endswith("/voices"):
            return 200, {"id": "voice_test123", "display_name": body["voice"]["display_name"]}
        return 200, {"steps": [{"type": "model_output", "content": [{"type": "audio", "mime_type": "audio/wav",
                                                                    "data": base64.b64encode(_wav_bytes(1.5)).decode()}]}]}


def test_cached_line_costs_no_request(tmp_path):
    fp = FakePost()
    kw = dict(key="k", cache_dir=tmp_path / "cache", budget=tmp_path / "b.json", post=fp, today=date(2026, 10, 20))
    d1 = voice.say("Crude oil 100 dollar.", "voice_x", tmp_path / "a.wav", **kw)
    d2 = voice.say("Crude oil 100 dollar.", "voice_x", tmp_path / "b.wav", **kw)
    assert d1 == pytest.approx(1.5) and d2 == pytest.approx(1.5)
    assert len(fp.calls) == 1 and (tmp_path / "b.wav").exists()
    assert voice.requests_today(tmp_path / "b.json", date(2026, 10, 20)) == 1


def test_request_shape_uses_interactions_api(tmp_path):
    fp = FakePost()
    voice.say("Namaste.", "voice_x", tmp_path / "a.wav", key="k", cache_dir=tmp_path / "c", budget=tmp_path / "b.json", post=fp)
    url, body = fp.calls[0]
    assert url.endswith("/v1beta/interactions")
    assert body["model"] == "gemini-3.8-flash-tts"
    assert body["generation_config"]["speech_config"] == [{"voice": "voice_x"}]
    assert body["input"][0]["content"][0]["text"] == "Namaste."
    assert body["response_format"] == {"type": "audio"}


def test_budget_hit_mid_piece_keeps_cache(tmp_path):
    fp = FakePost()
    budget = tmp_path / "b.json"
    budget.write_text(json.dumps({"2026-10-20": 79}))
    kw = dict(key="k", cache_dir=tmp_path / "cache", budget=budget, post=fp, today=date(2026, 10, 20))
    voice.say("line one", "v", tmp_path / "1.wav", **kw)                       # request 80: allowed
    with pytest.raises(voice.VoiceBudget):
        voice.say("line two", "v", tmp_path / "2.wav", **kw)                   # request 81: refused before calling
    assert len(fp.calls) == 1 and len(list((tmp_path / "cache").glob("*.wav"))) == 1
    budget.write_text(json.dumps({"2026-10-20": 0}))
    voice.say("line one", "v", tmp_path / "1.wav", **kw)
    voice.say("line two", "v", tmp_path / "2.wav", **kw)
    assert len(fp.calls) == 2                                                  # only the uncached line was paid for again


def test_enrol_builds_replicated_body(tmp_path):
    fp = FakePost()
    ref, consent = tmp_path / "ref.wav", tmp_path / "consent.wav"
    ref.write_bytes(_wav_bytes(20)); consent.write_bytes(_wav_bytes(10))
    vid = voice.enrol(ref, consent, key="k", display_name="SG test", post=fp)
    assert vid == "voice_test123"
    body = fp.calls[0][1]
    assert body["store"] is True and body["voice"]["type"] == "replicated" and body["voice"]["model"] == "gemini-3.8-flash-tts"
    rep = body["voice"]["replicated"]
    assert rep["source_audio"]["mime_type"] == "audio/wav" and rep["consent_audio"]["mime_type"] == "audio/wav"
    assert base64.b64decode(rep["source_audio"]["data"]) == _wav_bytes(20)


def test_lines_voices_every_scene_in_order(tmp_path):
    fp = FakePost()
    from engine import pieces
    p = pieces.Piece(id="x", channel="sglearning", kind="short", publish_day=date(2026, 10, 20))
    p.script = {"scenes": [{"vo": "ek"}, {"vo": "do"}, {"vo": "teen"}]}
    out = voice.lines(p, "v", tmp_path / "vo", key="k", cache_dir=tmp_path / "c", budget=tmp_path / "b.json", post=fp)
    assert [d for _p, d in out] == [pytest.approx(1.5)] * 3 and [b["input"][0]["content"][0]["text"] for _u, b in fp.calls] == ["ek", "do", "teen"]


def test_voice_ids_default_and_fallback(tmp_path):
    (tmp_path / "voice.json").write_text(json.dumps({"default": "voice_a", "fallback": "voice_b"}))
    assert voice.voice_ids(tmp_path) == ("voice_a", "voice_b")
    assert voice.voice_ids(tmp_path / "missing") == ("voice_9c6x5lerrbm4", "voice_7w9h8qkiqz03")


def test_no_audio_in_response_raises(tmp_path):
    def post(url, body, key):
        return 200, {"steps": [{"type": "model_output", "content": [{"type": "text", "text": "no audio"}]}]}
    with pytest.raises(voice.VoiceError):
        voice.say("x", "v", tmp_path / "a.wav", key="k", cache_dir=tmp_path / "c", budget=tmp_path / "b.json", post=post)
