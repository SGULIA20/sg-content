import pytest


@pytest.fixture(autouse=True)
def _no_voice_pacing(monkeypatch):
    """Tests never wait out the voice rate limit."""
    from engine import voice
    monkeypatch.setattr(voice, "MIN_GAP_S", 0)
    monkeypatch.setattr(voice, "_last_request", [0.0])
