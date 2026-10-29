from pathlib import Path
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
    voice.say("line one", "voice_v", tmp_path / "1.wav", **kw)                       # request 80: allowed
    with pytest.raises(voice.VoiceBudget):
        voice.say("line two", "voice_v", tmp_path / "2.wav", **kw)                   # request 81: refused before calling
    assert len(fp.calls) == 1 and len(list((tmp_path / "cache").glob("*.wav"))) == 1
    budget.write_text(json.dumps({"2026-10-20": 0}))
    voice.say("line one", "voice_v", tmp_path / "1.wav", **kw)
    voice.say("line two", "voice_v", tmp_path / "2.wav", **kw)
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
    out = voice.lines(p, "voice_v", tmp_path / "vo", key="k", cache_dir=tmp_path / "c", budget=tmp_path / "b.json", post=fp)
    assert [d for _p, d in out] == [pytest.approx(1.5)] * 3 and [b["input"][0]["content"][0]["text"] for _u, b in fp.calls] == ["ek", "do", "teen"]


def test_voice_ids_default_and_fallback(tmp_path):
    (tmp_path / "voice.json").write_text(json.dumps({"default": "voice_a", "fallback": "voice_b"}))
    assert voice.voice_ids(tmp_path) == ("voice_a", "voice_b")
    assert voice.voice_ids(tmp_path / "missing") == ("voice_9c6x5lerrbm4", "voice_7w9h8qkiqz03")


def test_no_audio_in_response_raises(tmp_path):
    def post(url, body, key):
        return 200, {"steps": [{"type": "model_output", "content": [{"type": "text", "text": "no audio"}]}]}
    with pytest.raises(voice.VoiceError):
        voice.say("x", "voice_v", tmp_path / "a.wav", key="k", cache_dir=tmp_path / "c", budget=tmp_path / "b.json", post=post)


def test_pick_rotates_through_pool_deterministically(tmp_path):
    (tmp_path / "voice.json").write_text(json.dumps({"default": "voice_a", "fallback": "voice_b", "pool": ["voice_a", "voice_c", "Puck"]}))
    picks = {voice.pick(f"2026-10-{d:02d}-sglearning-short", tmp_path) for d in range(1, 31)}
    assert picks == {"voice_a", "voice_c", "Puck"}
    assert voice.pick("2026-10-21-sglearning-short", tmp_path) == voice.pick("2026-10-21-sglearning-short", tmp_path)
    (tmp_path / "voice.json").write_text(json.dumps({"default": "voice_a", "fallback": "voice_b"}))
    assert voice.pick("x", tmp_path) == "voice_a"                              # no pool: the default


def test_say_uses_prebuilt_voice_names_through_generate_content(tmp_path):
    seen = {}
    def post(url, body, key):
        seen["url"], seen["body"] = url, body
        import base64
        pcm = b"\x00\x00" * 24000                                             # one second of silence, raw 16-bit 24 kHz
        return 200, {"candidates": [{"content": {"parts": [{"inlineData": {"mimeType": "audio/L16;rate=24000", "data": base64.b64encode(pcm).decode()}}]}}]}
    d = voice.say("Namaste.", "Puck", tmp_path / "a.wav", key="k", cache_dir=tmp_path / "c", budget=tmp_path / "b.json", post=post)
    assert seen["url"].endswith(":generateContent") and seen["body"]["generationConfig"]["speechConfig"]["voiceConfig"]["prebuiltVoiceConfig"]["voiceName"] == "Puck"
    assert seen["body"]["contents"][0]["parts"][0]["text"] == "Namaste."          # the style note is never in the spoken text (prebuilt voices read it aloud)
    assert d == pytest.approx(1.0, abs=0.05)


def test_rate_limit_waits_and_retries_without_spending_budget(tmp_path):
    calls, slept = [], []
    ok = FakePost()

    def post(url, body, key):
        calls.append(url)
        if len(calls) == 1:
            return 429, {"error": {"message": "Rate limit exceeded. Please retry in 58s or upgrade your tier."}}
        return ok(url, body, key)
    d = voice.say("Ek line.", "voice_x", tmp_path / "a.wav", key="k", cache_dir=tmp_path / "c", budget=tmp_path / "b.json",
                  post=post, today=date(2026, 10, 21), sleep=slept.append)
    assert d == pytest.approx(1.5) and len(calls) == 2 and slept == [59.0]
    assert voice.requests_today(tmp_path / "b.json", date(2026, 10, 21)) == 1          # the refused request is not counted


def test_lines_are_paced_under_ten_a_minute(tmp_path, monkeypatch):
    monkeypatch.setattr(voice, "MIN_GAP_S", 6.5)
    now = [100.0]; slept = []
    sleep = lambda s: (slept.append(round(s, 1)), now.__setitem__(0, now[0] + s))
    kw = dict(key="k", cache_dir=tmp_path / "c", budget=tmp_path / "b.json", post=FakePost(), today=date(2026, 10, 21), sleep=sleep, clock=lambda: now[0])
    voice.say("one", "voice_x", tmp_path / "1.wav", **kw)
    voice.say("two", "voice_x", tmp_path / "2.wav", **kw)
    assert slept == [6.5]


def _speech_like(path, parts, rate=24000, gap=0.6):
    """Loud noisy bursts (one per text) separated by `gap` seconds of silence, like narration with paragraph pauses."""
    import numpy as np
    rng = np.random.default_rng(1)
    chunks = []
    for secs in parts:
        chunks.append((rng.normal(0, 6000, int(secs * rate))).astype(np.int16))
        chunks.append(np.zeros(int(gap * rate), dtype=np.int16))
    pcm = np.concatenate(chunks[:-1])
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate); w.writeframes(pcm.tobytes())
    return path


def test_split_group_cuts_at_the_pauses_nearest_each_scenes_word_share(tmp_path):
    texts = ["one two three four five six", "seven eight nine ten eleven twelve", "thirteen fourteen fifteen sixteen seventeen eighteen"]
    g = _speech_like(tmp_path / "g.wav", [2.0, 2.0, 2.0])
    parts = voice.split_group(g, texts, [tmp_path / f"s{i}.wav" for i in range(3)])
    assert parts and [p.name for p, _d in parts] == ["s0.wav", "s1.wav", "s2.wav"]
    assert all(1.9 <= d <= 2.9 for _p, d in parts) and abs(sum(d for _p, d in parts) - 7.2) < 0.05


def test_split_group_gives_up_when_pauses_do_not_match(tmp_path):
    g = _speech_like(tmp_path / "g.wav", [6.0])                                   # one burst, no pause at all
    assert voice.split_group(g, ["a b c", "d e f"], [tmp_path / "x.wav", tmp_path / "y.wav"]) is None


def test_batched_uses_one_request_per_group_and_falls_back_per_line(tmp_path):
    calls = []
    def fake_say(text, vid, out, **kw):
        calls.append(text)
        n = text.count(voice.JOIN) + 1
        _speech_like(out, [1.0] * n) if n > 1 or "solo" in text else _speech_like(out, [1.0], gap=0)
        return 1.0 * n
    texts = ["a a a", "b b b", "c c c", "d d d", "e e e"]
    out = voice.batched(texts, "Puck", tmp_path / "vo", say_fn=fake_say, group=4, verify=False)
    assert len(out) == 5 and [p.name for p, _d in out] == [f"vo{i:02d}.wav" for i in range(5)]
    assert len(calls) == 2 and calls[0] == voice.JOIN.join(texts[:4]) and calls[1] == "e e e"      # 2 requests instead of 5
    calls.clear()
    def no_pause_say(text, vid, out, **kw):
        calls.append(text); _speech_like(out, [1.0], gap=0); return 1.0                                  # the group came back without pauses
    out = voice.batched(["p p", "q q"], "Puck", tmp_path / "vo2", say_fn=no_pause_say, group=4, verify=False)
    assert len(out) == 2 and calls == [voice.JOIN.join(["p p", "q q"]), "p p", "q q"]                     # fallback: the lines one by one


def test_segment_matches_checks_both_edges():
    assert voice.segment_matches("Raat ko bhai ka phone chamka, news thi Zerodha par ab US stocks milenge.", "Raat ko Bhai ka phone chamka, news thi, Zerodha par ab US stocks milenge.")
    assert not voice.segment_matches("Bhai uchhal pada bola ab Nvidia Tesla", "Bhai uchhal pada, bola, ab Nvidia, Tesla, Amazon, sab phone se khareedunga.")
    assert not voice.segment_matches("Amazon, sab phone se khareedunga. Uska logic seedha tha, ye companies duniya chalati hain.", "Uska logic seedha tha, yeh companies duniya chalati hain, toh paisa bhi badhega.")


def test_batched_falls_back_when_a_segment_does_not_read_back(tmp_path):
    calls = []
    def fake_say(text, vid, out, **kw):
        calls.append(text); n = text.count(voice.JOIN) + 1; _speech_like(out, [1.0] * n); return float(n)
    out = voice.batched(["a a a", "b b b"], "Puck", tmp_path / "vo", say_fn=fake_say, verify=lambda wav, text: "b" not in text)
    assert len(out) == 2 and calls == [voice.JOIN.join(["a a a", "b b b"]), "a a a", "b b b"]


def test_line_ok_flags_double_and_cut_lines():
    text = "ek do teen chaar paanch chhe saat aath"
    assert voice.line_ok(Path("x.wav"), text, transcribe_fn=lambda w: "ek do teen chaar paanch chhe saat aath")[0]
    assert not voice.line_ok(Path("x.wav"), text, transcribe_fn=lambda w: "ek do teen chaar paanch chhe saat aath ek do teen chaar paanch chhe saat aath")[0]
    assert not voice.line_ok(Path("x.wav"), text, transcribe_fn=lambda w: "ek do teen")[0]


def test_verified_lines_resynthesises_a_line_heard_twice(tmp_path):
    made = []
    def fake_say(text, vid, out, cache_dir=None, **kw):
        made.append(text); Path(out).write_bytes(b"w"); return 1.0
    heard = iter(["a b c d e", "a b c d e a b c d e", "a b c d e"])            # line 2 comes back doubled once, then clean
    out = voice.verified_lines(["a b c d e", "a b c d e!"], "voice_x", tmp_path / "vo", say_fn=fake_say, transcribe_fn=lambda w: next(heard), cache_dir=tmp_path / "c")
    assert len(out) == 2 and made == ["a b c d e", "a b c d e!", "a b c d e!"]


def test_plain_voice_sends_the_batch_lanes_request_without_a_style_note(tmp_path):
    import base64
    from engine import voice
    sent = []
    def post(url, body, key):
        sent.append((url, body)); pcm = b"\x00\x00" * 2400
        return 200, {"candidates": [{"content": {"parts": [{"inlineData": {"mimeType": "audio/L16;rate=24000", "data": base64.b64encode(pcm).decode()}}]}}]}
    secs = voice.say("Namaste", "voice_abc", tmp_path / "a.wav", key="k", cache_dir=tmp_path / "c", budget=tmp_path / "b.json", post=post,
                     sleep=lambda s: None, plain=True)
    url, body = sent[0]
    assert url.endswith(":generateContent") and body["generationConfig"]["speechConfig"]["voiceConfig"] == {"voice": "voice_abc"}
    assert "style" not in str(body) and secs > 0
