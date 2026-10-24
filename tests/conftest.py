import pytest


@pytest.fixture(autouse=True)
def _no_voice_pacing(monkeypatch):
    """Tests never wait out the voice rate limit."""
    from engine import voice
    monkeypatch.setattr(voice, "MIN_GAP_S", 0)
    monkeypatch.setattr(voice, "_last_request", [0.0])


@pytest.fixture(autouse=True)
def _batch_ledgers_in_tmp(monkeypatch, tmp_path_factory):
    """Tests never write to the production batch ledgers (22-24 Oct 2026: the cloud runs run the tests first, so every run added fake
    batches to logs/*-batch.jsonl and inflated the digest's batch counts)."""
    from engine import artbatch, voicebatch, writebatch
    d = tmp_path_factory.mktemp("ledgers")
    monkeypatch.setattr(voicebatch, "LEDGER", d / "voice-batch.jsonl")
    monkeypatch.setattr(artbatch, "LEDGER", d / "art-batch.jsonl")
    monkeypatch.setattr(writebatch, "LEDGER", d / "write-batch.jsonl")
