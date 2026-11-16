import dataclasses

import pytest

from engine import config

# The logic tests were written around the 18:30 India Instagram slot of Learning with SG. The live slot moved to 21:40 on 16 Nov 2026
# (founder: "same time as SG-MYTH, 5-10 minutes apart"); the tests keep their clock so they still test the rules, and
# test_workflows.test_the_live_learning_slot checks the live value.
LIVE_LEARNING_SLOT = config.CHANNELS["sglearning"].ig_slot_ist


@pytest.fixture(autouse=True)
def _learning_slot_of_the_tests(monkeypatch):
    monkeypatch.setitem(config.CHANNELS, "sglearning", dataclasses.replace(config.CHANNELS["sglearning"], ig_slot_ist="18:30"))


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


@pytest.fixture(autouse=True)
def _hinglish_unless_the_test_is_about_language(monkeypatch, request):
    """The older tests use dates after 23 Nov 2026 and were written for Hinglish; only tests/test_lang.py reads the live language file."""
    if request.module.__name__.endswith("test_lang"):
        return
    from engine import lang
    monkeypatch.setattr(lang, "_config", lambda root=None: {})
