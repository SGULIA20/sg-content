import json
from engine import gemini


def _resp(tin=100, tout=20, thought=5, queries=("a", "b")):
    return {"candidates": [{"content": {"parts": [{"text": "ok"}]}, "groundingMetadata": {"webSearchQueries": list(queries)}}],
            "usageMetadata": {"promptTokenCount": tin, "candidatesTokenCount": tout, "thoughtsTokenCount": thought}}


def test_an_entry_records_tokens_and_search_queries():
    body = {"tools": [{"google_search": {}}], "generationConfig": {"responseModalities": ["AUDIO"]}}
    e = gemini.entry("gemini-3.8-flash", "research.fact_sheet", 200, 0, _resp(), body)
    assert (e["in"], e["out"], e["thought"], e["search"], e["search_queries"], e["modalities"]) == (100, 20, 5, True, 2, ["AUDIO"])
    assert e["caller"] == "research.fact_sheet" and e["status"] == 200


def test_a_fake_post_is_not_logged(tmp_path, monkeypatch):
    log = tmp_path / "gemini-calls.jsonl"
    monkeypatch.setattr(gemini, "LOG_FILE", log)
    gemini.generate("m", {"contents": []}, "k", post=lambda u, b, k: (200, _resp()))
    assert not log.exists()


def test_the_summary_counts_each_step_and_its_failures(tmp_path):
    log = tmp_path / "calls.jsonl"
    rows = [gemini.entry("m", "research.fact_sheet", 200, 0, _resp(tin=50, queries=("x",)), {"tools": [{"google_search": {}}]}),
            gemini.entry("m", "research.fact_sheet", 402, 0, {"error": {}}, {}),
            gemini.entry("m", "voice.speak", 200, 0, _resp(tin=10, tout=7, thought=0, queries=()), {})]
    for r in rows:
        gemini.write(r, log)
    text = gemini.usage_summary(rows[0]["at"][:10], log)
    assert "3 requests, 1 failed attempts" in text
    assert "research.fact_sheet: 2 requests (1 failed), tokens in 50 out 25, search queries 1" in text
    assert "voice.speak: 1 requests (0 failed), tokens in 10 out 7, search queries 0" in text
    assert gemini.usage_summary("1999-01-01", log) == "no Gemini calls on 1999-01-01"


def test_the_log_names_the_step_that_asked(tmp_path, monkeypatch):
    import pytest
    from engine import secrets
    log = tmp_path / "calls.jsonl"
    monkeypatch.setattr(gemini, "LOG_FILE", log)
    monkeypatch.setattr(gemini, "TRIES", 1)
    monkeypatch.setattr(secrets, "ssl_context", lambda: None)
    def no_network(*a, **k):
        raise OSError("offline in test")
    monkeypatch.setattr(gemini.urllib.request, "urlopen", no_network)
    def asking_step():
        return gemini.generate("m", {"contents": []}, "k")                  # the real post, so the call is logged
    with pytest.raises(gemini.GeminiError):
        asking_step()
    row = json.loads(log.read_text().splitlines()[0])
    assert row["caller"] == "test_gemini_log.asking_step" and row["status"] == 599
