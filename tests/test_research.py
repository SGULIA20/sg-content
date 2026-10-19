import json
from datetime import date

import pytest

from engine import gemini, research

TODAY = date(2026, 10, 19)


def fact(**kw):
    base = {"text": "Brent crossed $100", "number": 100.0, "unit": "USD/bbl", "source_url": "https://example.com/a",
            "source_name": "ET", "source_date": "2026-10-19", "quote": "Brent crude crossed $100", "label": "reported"}
    base.update(kw)
    return base


def test_fact_without_url_is_dropped():
    sheet = {"facts": [fact(), fact(source_url="")], "summary": "x"}
    assert len(research.clean(sheet, "sglearning", TODAY, news=True)["facts"]) == 1


def test_old_finance_fact_is_dropped_for_news():
    sheet = {"facts": [fact(source_date="2026-10-09")], "summary": "x"}
    assert research.clean(sheet, "sglearning", TODAY, news=True)["facts"] == []
    assert len(research.clean(sheet, "sglearning", TODAY, news=False)["facts"]) == 1


def test_myth_fact_needs_label():
    sheet = {"facts": [fact(label="maybe"), fact(label="archaeology")], "summary": "x"}
    kept = research.clean(sheet, "arthvan", TODAY)["facts"]
    assert [f["label"] for f in kept] == ["archaeology"]


def test_finance_label_defaults_to_reported():
    sheet = {"facts": [fact(label="")], "summary": "x"}
    assert research.clean(sheet, "sglearning", TODAY)["facts"][0]["label"] == "reported"


def test_fact_sheet_uses_grounding_tool_and_json():
    seen = {}

    def fake_ask(model, body, key):
        seen["model"], seen["body"] = model, body
        return {"candidates": [{"content": {"parts": [{"text": json.dumps({"facts": [fact()], "summary": "s"})}]}}]}

    topic = {"title": "Crude oil crosses $100", "link": "https://example.com/a", "summary": "..."}
    sheet = research.fact_sheet(topic, "sglearning", key="k", ask=fake_ask, today=TODAY)
    assert seen["model"] == "gemini-3.8-flash"
    assert seen["body"]["tools"] == [{"google_search": {}}]
    assert "responseMimeType" not in seen["body"]["generationConfig"]          # JSON mode + grounding returns an empty candidate
    assert seen["body"]["generationConfig"]["temperature"] == 0
    assert "Crude oil crosses $100" in seen["body"]["contents"][0]["parts"][0]["text"]
    assert sheet["facts"][0]["number"] == 100.0


def test_fact_sheet_strips_code_fence():
    def fake_ask(model, body, key):
        return {"candidates": [{"content": {"parts": [{"text": "```json\n" + json.dumps({"facts": [fact()], "summary": "s"}) + "\n```"}]}}]}
    sheet = research.fact_sheet({"title": "t", "link": "u", "summary": ""}, "sglearning", key="k", ask=fake_ask, today=TODAY)
    assert len(sheet["facts"]) == 1


def test_gemini_generate_retries_on_503(monkeypatch):
    calls = []

    def fake_post(url, body, key):
        calls.append(url)
        return (503, {"error": {"message": "busy"}}) if len(calls) == 1 else (200, {"ok": True})

    monkeypatch.setattr(gemini.time, "sleep", lambda s: None)
    assert gemini.generate("gemini-3.8-flash", {"contents": []}, key="k", post=fake_post) == {"ok": True}
    assert len(calls) == 2 and calls[0].endswith("models/gemini-3.8-flash:generateContent")


def test_gemini_generate_raises_after_three_failures(monkeypatch):
    monkeypatch.setattr(gemini.time, "sleep", lambda s: None)
    with pytest.raises(gemini.GeminiError):
        gemini.generate("m", {}, key="k", post=lambda u, b, k: (429, {"error": {"message": "quota"}}))


def test_gemini_text_helper_extracts_first_text():
    r = {"candidates": [{"content": {"parts": [{"text": "hello"}]}}]}
    assert gemini.text(r) == "hello"


def test_fact_sheet_extracts_json_from_prose():
    def fake_ask(model, body, key):
        return {"candidates": [{"content": {"parts": [{"text": "Here is the sheet:\n" + json.dumps({"facts": [fact()], "summary": "s"}) + "\nDone."}]}}]}
    sheet = research.fact_sheet({"title": "t", "link": "u", "summary": ""}, "sglearning", key="k", ask=fake_ask, today=TODAY)
    assert len(sheet["facts"]) == 1


def test_fact_sheet_empty_reply_raises_research_error():
    with pytest.raises(research.ResearchError):
        research.fact_sheet({"title": "t", "link": "u", "summary": ""}, "sglearning", key="k", ask=lambda m, b, k: {"candidates": [{}]}, today=TODAY)


def test_fact_sheet_repairs_broken_json_with_second_call():
    calls = []

    def fake_ask(model, body, key):
        calls.append(body)
        if len(calls) == 1:
            return {"candidates": [{"content": {"parts": [{"text": '{"facts": [{"text": "Brent crossed $100", "number": 100.0 "unit": "USD"}], "summary": "s"}'}]}}]}
        return {"candidates": [{"content": {"parts": [{"text": json.dumps({"facts": [fact()], "summary": "s"})}]}}]}

    sheet = research.fact_sheet({"title": "t", "link": "u", "summary": ""}, "sglearning", key="k", ask=fake_ask, today=TODAY)
    assert len(sheet["facts"]) == 1 and len(calls) == 2
    assert "tools" not in calls[1] and calls[1]["generationConfig"]["responseMimeType"] == "application/json"
    assert "Brent crossed" in calls[1]["contents"][0]["parts"][0]["text"]
