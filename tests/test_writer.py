import json
from datetime import date
from types import SimpleNamespace

import pytest

from engine import pieces, schema, writer

DISCLAIMER = "Yeh investment advice nahi hai"


def good_script():
    return {
        "title": "Crude *100 dollar* ke paar 💥",
        "hook": "Crude oil 100 dollar ke paar. Aapki EMI par asar?",
        "scenes": [
            {"vo": "Crude oil 100 dollar ke paar gaya.", "visual": {"type": "avatar", "prompt": "explaining_front", "card": None}, "facts_used": [0], "label": "reported"},
            {"vo": "India apna 88 pratishat tel bahar se khareedta hai.", "visual": {"type": "card", "prompt": "", "card": {"big_number": "88%", "line": "tel import", "source": "PPAC"}}, "facts_used": [1], "label": "official"},
            {"vo": DISCLAIMER + ".", "visual": {"type": "art", "prompt": "a calm desk with a notebook", "card": None}, "facts_used": [], "label": "reported"},
        ],
        "end_question": "Aapko kya lagta hai?",
        "cards": [{"big_number": "88%", "line": "tel import", "source": "PPAC"}],
        "captions": {"youtube": {"title": "Oil 100 dollar: EMI par asar?", "description": "d", "tags": ["oil"], "chapters": []},
                     "instagram": {"caption": "Oil 100 dollar. " + DISCLAIMER + " Share karo us dost ko jo petrol daily bharta hai.", "hashtags": ["#PaiseKiKhabar", "#SeedhiBaat", "#CrudeOil", "#EMI", "#RBI"]},
                     "threads": {"text": "Oil 100 dollar?"}},
        "carousel": False,
        "thumbnail": {"words": ["100 DOLLAR", "EMI?"], "scene": "PAPA stares at the petrol pump meter, eyes wide, mouth open"},
    }


def _piece():
    p = pieces.Piece(id="2026-10-20-sglearning-short", channel="sglearning", kind="short", publish_day=date(2026, 10, 20))
    p.topic = {"title": "Crude oil crosses $100"}
    return p


class FakeMessages:
    def __init__(self, text=None, stop_reason="end_turn", raise_exc=None):
        self.text, self.stop_reason, self.raise_exc, self.calls = text, stop_reason, raise_exc, []

    def stream(self, **kw):
        self.calls.append(kw)
        if self.raise_exc:
            raise self.raise_exc
        msg = SimpleNamespace(stop_reason=self.stop_reason, content=[SimpleNamespace(type="text", text=self.text or "")],
                              usage=SimpleNamespace(input_tokens=5000, output_tokens=1500))
        return FakeStream(msg)


class FakeStream:
    def __init__(self, msg):
        self.msg = msg

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get_final_message(self):
        return self.msg


def fake_client(messages):
    return SimpleNamespace(beta=SimpleNamespace(messages=messages))


def test_request_uses_opus_schema_and_fallbacks(tmp_path):
    fm = FakeMessages(text=json.dumps(good_script()))
    p = _piece(); p.kind = "long"
    out = writer.write(p, {"facts": [], "summary": ""}, [], {}, formula="FORMULA", client=fake_client(fm), spend=tmp_path / "s.json")
    kw = fm.calls[0]
    assert kw["model"] == "claude-opus-5-5"
    assert kw["output_config"]["format"] == {"type": "json_schema", "schema": schema.api_schema(schema.PIECE_SCHEMA)}
    assert kw["max_tokens"] >= 64000
    assert kw["output_config"]["effort"] == "high"
    assert kw["betas"] == ["server-side-fallback-2026-07-01"] and kw["fallbacks"] == "default"
    assert kw["system"][0]["cache_control"] == {"type": "ephemeral"} and "FORMULA" in kw["system"][0]["text"]
    assert out["script"]["hook"].startswith("Crude oil") and out["writer"] == "claude"


def test_refusal_falls_back_to_gemini_and_marks_writer(tmp_path):
    fm = FakeMessages(text="", stop_reason="refusal")
    g = lambda model, body, key=None: {"candidates": [{"content": {"parts": [{"text": json.dumps(good_script())}]}}]}
    p = _piece(); p.kind = "long"
    out = writer.write(p, {"facts": []}, [], {}, formula="F", client=fake_client(fm), gemini_ask=g, spend=tmp_path / "s.json")
    assert out["writer"] == "gemini" and out["script"]["carousel"] is False


def test_api_error_falls_back_to_gemini(tmp_path):
    import anthropic
    import httpx2
    resp = httpx2.Response(529, request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages"))
    exc = anthropic.APIStatusError("boom", response=resp, body=None)
    fm = FakeMessages(raise_exc=exc)
    g = lambda model, body, key=None: {"candidates": [{"content": {"parts": [{"text": json.dumps(good_script())}]}}]}
    p = _piece(); p.kind = "long"
    out = writer.write(p, {"facts": []}, [], {}, formula="F", client=fake_client(fm), gemini_ask=g, spend=tmp_path / "s.json")
    assert out["writer"] == "gemini"


def test_cost_recorded_per_day(tmp_path):
    fm = FakeMessages(text=json.dumps(good_script()))
    p = _piece(); p.kind = "long"
    writer.write(p, {"facts": []}, [], {}, formula="F", client=fake_client(fm), spend=tmp_path / "s.json", today=date(2026, 10, 20))
    spent = json.loads((tmp_path / "s.json").read_text())
    assert spent["2026-10-20"]["usd"] == pytest.approx(5000 * 4 / 1e6 + 1500 * 20 / 1e6)
    assert writer.spent_today(tmp_path / "s.json", date(2026, 10, 20)) == pytest.approx(0.05)


def test_budget_blocks_claude_and_uses_gemini(tmp_path):
    (tmp_path / "s.json").write_text(json.dumps({"2026-10-20": {"usd": 3.0, "requests": 9}}))
    fm = FakeMessages(text=json.dumps(good_script()))
    g = lambda model, body, key=None: {"candidates": [{"content": {"parts": [{"text": json.dumps(good_script())}]}}]}
    p = _piece(); p.kind = "long"
    out = writer.write(p, {"facts": []}, [], {}, formula="F", client=fake_client(fm), gemini_ask=g, spend=tmp_path / "s.json", today=date(2026, 10, 20))
    assert fm.calls == [] and out["writer"] == "gemini"


def test_schema_rejects_unknown_visual_type():
    s = good_script()
    s["scenes"][0]["visual"]["type"] = "video"
    assert any("visual.type" in e for e in schema.validate(s))
    assert schema.validate(good_script()) == []


def test_schema_rejects_missing_required_and_extra_keys():
    s = good_script(); del s["end_question"]; s["extra"] = 1
    errs = schema.validate(s)
    assert any("end_question" in e for e in errs) and any("extra" in e for e in errs)


def test_prompt_files_exist_and_carry_rules():
    sys_text = writer.system_prompt("sglearning")
    assert DISCLAIMER in sys_text and "digits" in sys_text.lower()
    assert "scripture" in writer.system_prompt("arthvan")


def test_user_message_serialises_datetime_in_topic(tmp_path):
    from datetime import datetime, timezone
    p = _piece(); p.kind = "long"; p.topic["published"] = datetime(2026, 10, 20, 3, 45, tzinfo=timezone.utc)
    fm = FakeMessages(text=json.dumps(good_script()))
    out = writer.write(p, {"facts": []}, [], {}, formula="F", client=fake_client(fm), spend=tmp_path / "s.json")
    assert out["writer"] == "claude" and "2026-10-20T03:45:00+00:00" in fm.calls[0]["messages"][0]["content"]


def test_revise_note_reaches_the_prompt(tmp_path):
    p = _piece(); p.kind = "long"; p.topic["revise"] = "length: 150 words, allowed 90-135"
    fm = FakeMessages(text=json.dumps(good_script()))
    writer.write(p, {"facts": []}, [], {}, formula="F", client=fake_client(fm), spend=tmp_path / "s.json")
    assert "REVISION" in fm.calls[0]["messages"][0]["content"] and "150 words" in fm.calls[0]["messages"][0]["content"]


def test_schema_has_title_and_story_scripts_validate():
    s = good_script(); s["title"] = "Papa ne 20 saal *FD* mein rakha… 💔"
    assert schema.validate(s) == []
    assert "title" in schema.PIECE_SCHEMA["required"]


def test_claude_writes_shorts_and_longs(tmp_path):
    fm = FakeMessages(text=json.dumps(good_script()))
    g_calls = []
    g = lambda model, body, key=None: g_calls.append(model) or {"candidates": [{"content": {"parts": [{"text": json.dumps(good_script())}]}}]}
    p = _piece()
    out = writer.write(p, {"facts": []}, [], {}, formula="F", client=fake_client(fm), gemini_ask=g, spend=tmp_path / "s.json")
    assert out["writer"] == "claude" and len(fm.calls) == 1                  # Claude writes Shorts too (founder, 20 Oct)
    p.kind = "long"
    out = writer.write(p, {"facts": []}, [], {}, formula="F", client=fake_client(fm), gemini_ask=g, spend=tmp_path / "s.json")
    assert out["writer"] == "claude"


def _keys(sch):
    if isinstance(sch, dict):
        for k, v in sch.items():
            yield k, v
            if k == "properties":
                for pv in v.values():
                    yield from _keys(pv)
            else:
                yield from _keys(v)
    elif isinstance(sch, list):
        for s in sch:
            yield from _keys(s)


def test_schema_sent_to_claude_has_no_keyword_the_api_rejects():
    """21 Oct 2026: maxItems in the thumbnail words made every Claude call a 400 and Gemini wrote everything."""
    sent = schema.api_schema(schema.PIECE_SCHEMA)
    bad = [(k, v) for k, v in _keys(sent) if k in schema.UNSUPPORTED or (k == "minItems" and v not in (0, 1))]
    assert bad == []
    assert schema.validate({**good_script(), "thumbnail": {"words": ["A", "B", "C", "D"], "scene": "x"}}) != []   # still enforced locally


def test_cut_off_gemini_reply_is_a_writer_error_not_a_crash(tmp_path):
    fm = FakeMessages(raise_exc=RuntimeError("claude down"))
    full = json.dumps(good_script()); cut = full[:len(full) // 2]       # a reply cut off mid-string, as on 21 Oct
    g = lambda model, body, key=None: {"candidates": [{"content": {"parts": [{"text": cut}]}}]}
    p = _piece(); p.kind = "long"
    with pytest.raises(writer.WriterError) as e:
        writer.write(p, {"facts": []}, [], {}, formula="F", client=fake_client(fm), gemini_ask=g, spend=tmp_path / "s.json")
    assert "claude failed" in str(e.value) and "gemini failed" in str(e.value)


def test_claude_cut_off_at_max_tokens_falls_back(tmp_path):
    fm = FakeMessages(text=json.dumps(good_script())[:500], stop_reason="max_tokens")
    g = lambda model, body, key=None: {"candidates": [{"content": {"parts": [{"text": json.dumps(good_script())}]}}]}
    p = _piece(); p.kind = "long"
    out = writer.write(p, {"facts": []}, [], {}, formula="F", client=fake_client(fm), gemini_ask=g, spend=tmp_path / "s.json")
    assert out["writer"] == "gemini" and "cut off" in out["note"]
