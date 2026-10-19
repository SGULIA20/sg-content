import json
from datetime import date
from types import SimpleNamespace

import pytest

from engine import pieces, schema, writer

DISCLAIMER = "Yeh investment advice nahi hai"


def good_script():
    return {
        "hook": "Crude oil 100 dollar ke paar. Aapki EMI par asar?",
        "scenes": [
            {"vo": "Crude oil 100 dollar ke paar gaya.", "visual": {"type": "avatar", "prompt": "explaining_front", "card": None}, "facts_used": [0], "label": "reported"},
            {"vo": "India apna 88 pratishat tel bahar se khareedta hai.", "visual": {"type": "card", "prompt": "", "card": {"big_number": "88%", "line": "tel import", "source": "PPAC"}}, "facts_used": [1], "label": "official"},
            {"vo": DISCLAIMER + ".", "visual": {"type": "art", "prompt": "a calm desk with a notebook", "card": None}, "facts_used": [], "label": "reported"},
        ],
        "end_question": "Aapko kya lagta hai?",
        "cards": [{"big_number": "88%", "line": "tel import", "source": "PPAC"}],
        "captions": {"youtube": {"title": "Oil 100 dollar: EMI par asar?", "description": "d", "tags": ["oil"], "chapters": []},
                     "instagram": {"caption": "Oil 100 dollar. " + DISCLAIMER, "hashtags": ["#PaiseKiKhabar", "#SeedhiBaat", "#CrudeOil", "#EMI", "#RBI"]},
                     "threads": {"text": "Oil 100 dollar?"}},
        "carousel": False,
    }


def _piece():
    p = pieces.Piece(id="2026-10-20-sglearning-short", channel="sglearning", kind="short", publish_day=date(2026, 10, 20))
    p.topic = {"title": "Crude oil crosses $100"}
    return p


class FakeMessages:
    def __init__(self, text=None, stop_reason="end_turn", raise_exc=None):
        self.text, self.stop_reason, self.raise_exc, self.calls = text, stop_reason, raise_exc, []

    def create(self, **kw):
        self.calls.append(kw)
        if self.raise_exc:
            raise self.raise_exc
        return SimpleNamespace(stop_reason=self.stop_reason, content=[SimpleNamespace(type="text", text=self.text or "")],
                               usage=SimpleNamespace(input_tokens=5000, output_tokens=1500))


def fake_client(messages):
    return SimpleNamespace(beta=SimpleNamespace(messages=messages))


def test_request_uses_opus_schema_and_fallbacks(tmp_path):
    fm = FakeMessages(text=json.dumps(good_script()))
    out = writer.write(_piece(), {"facts": [], "summary": ""}, [], {}, formula="FORMULA", client=fake_client(fm), spend=tmp_path / "s.json")
    kw = fm.calls[0]
    assert kw["model"] == "claude-opus-5-5"
    assert kw["output_config"]["format"] == {"type": "json_schema", "schema": schema.PIECE_SCHEMA}
    assert kw["output_config"]["effort"] == "high"
    assert kw["betas"] == ["server-side-fallback-2026-07-01"] and kw["fallbacks"] == "default"
    assert kw["system"][0]["cache_control"] == {"type": "ephemeral"} and "FORMULA" in kw["system"][0]["text"]
    assert out["script"]["hook"].startswith("Crude oil") and out["writer"] == "claude"


def test_refusal_falls_back_to_gemini_and_marks_writer(tmp_path):
    fm = FakeMessages(text="", stop_reason="refusal")
    g = lambda model, body, key=None: {"candidates": [{"content": {"parts": [{"text": json.dumps(good_script())}]}}]}
    out = writer.write(_piece(), {"facts": []}, [], {}, formula="F", client=fake_client(fm), gemini_ask=g, spend=tmp_path / "s.json")
    assert out["writer"] == "gemini" and out["script"]["carousel"] is False


def test_api_error_falls_back_to_gemini(tmp_path):
    import anthropic
    import httpx2
    resp = httpx2.Response(529, request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages"))
    exc = anthropic.APIStatusError("boom", response=resp, body=None)
    fm = FakeMessages(raise_exc=exc)
    g = lambda model, body, key=None: {"candidates": [{"content": {"parts": [{"text": json.dumps(good_script())}]}}]}
    out = writer.write(_piece(), {"facts": []}, [], {}, formula="F", client=fake_client(fm), gemini_ask=g, spend=tmp_path / "s.json")
    assert out["writer"] == "gemini"


def test_cost_recorded_per_day(tmp_path):
    fm = FakeMessages(text=json.dumps(good_script()))
    writer.write(_piece(), {"facts": []}, [], {}, formula="F", client=fake_client(fm), spend=tmp_path / "s.json", today=date(2026, 10, 20))
    spent = json.loads((tmp_path / "s.json").read_text())
    assert spent["2026-10-20"]["usd"] == pytest.approx(5000 * 4 / 1e6 + 1500 * 20 / 1e6)
    assert writer.spent_today(tmp_path / "s.json", date(2026, 10, 20)) == pytest.approx(0.05)


def test_budget_blocks_claude_and_uses_gemini(tmp_path):
    (tmp_path / "s.json").write_text(json.dumps({"2026-10-20": {"usd": 1.0, "requests": 9}}))
    fm = FakeMessages(text=json.dumps(good_script()))
    g = lambda model, body, key=None: {"candidates": [{"content": {"parts": [{"text": json.dumps(good_script())}]}}]}
    out = writer.write(_piece(), {"facts": []}, [], {}, formula="F", client=fake_client(fm), gemini_ask=g, spend=tmp_path / "s.json", today=date(2026, 10, 20))
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
