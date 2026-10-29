import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from engine import config, lint, pieces, pipeline, writebatch, writer
from tests.test_writer import FakeMessages, fake_client, good_script


def test_story_word_limit_is_soft_at_260():
    assert config.STORY_WORDS == (150, 260) and config.story_words("sglearning") == (85, 125)


def test_patchable_means_only_fixable_checks_over_the_limit():
    assert writer.patchable(["numbers without a source: 4500", "advice: guarantee", "label: scene 3 has no evidence label"])
    assert writer.patchable(["length: 271 words, allowed 150-260"])
    assert not writer.patchable(["length: 121 words, allowed 150-260"])           # too short: a full rewrite
    assert not writer.patchable(["originality: too close to an earlier script"])
    assert not writer.patchable(["numbers without a source: 5", "originality: too close"])
    assert not writer.patchable([])


def _piece():
    p = pieces.Piece(id="2026-10-27-sglearning-short", channel="sglearning", kind="short", publish_day=date(2026, 10, 27))
    p.script = good_script(); p.topic = {"title": "t", "revise": "numbers without a source: 4500"}
    return p


def test_apply_patch_replaces_only_the_named_scenes_and_fields():
    prev = good_script()
    raw = json.dumps({"scenes": [{"index": 0, "vo": "Naya pehla vaakya."}], "fields": {"threads_text": "Naya threads."}})
    out = writer.apply_patch(prev, raw)
    assert out["scenes"][0]["vo"] == "Naya pehla vaakya." and out["scenes"][1:] == prev["scenes"][1:]
    assert out["captions"]["threads"]["text"] == "Naya threads." and out["captions"]["youtube"] == prev["captions"]["youtube"]
    assert prev["scenes"][0]["vo"] != "Naya pehla vaakya."                                       # the original is untouched


def test_apply_patch_rejects_bad_indexes_and_bad_json():
    with pytest.raises(writer.WriterError):
        writer.apply_patch(good_script(), json.dumps({"scenes": [{"index": 99, "vo": "x"}]}))
    with pytest.raises(writer.WriterError):
        writer.apply_patch(good_script(), "not json")


def test_write_patches_a_fixable_rejection_with_a_small_request_and_counts_the_try(tmp_path):
    p = _piece()
    fm = FakeMessages(text=json.dumps({"scenes": [{"index": 0, "vo": "Theek kiya hua vaakya."}]}))
    out = writer.write(p, {"facts": []}, [], {}, client=fake_client(fm), spend=tmp_path / "s.json", today=date(2026, 10, 24))
    kw = fm.calls[0]
    assert out["script"]["scenes"][0]["vo"] == "Theek kiya hua vaakya." and out["note"].startswith("patched")
    assert kw["max_tokens"] == 8000 and kw["output_config"]["effort"] == "medium" and "PATCH MODE" in kw["messages"][0]["content"]
    assert "numbers without a source: 4500" in kw["messages"][0]["content"] and p.topic["patch_tries"] == 1


def test_a_failed_patch_falls_back_to_the_full_rewrite(tmp_path):
    p = _piece()
    class Seq(FakeMessages):
        n = 0
        def stream(self, **kw):
            Seq.n += 1
            self.text = "garbage" if Seq.n == 1 else json.dumps(good_script())
            return super().stream(**kw)
    fm = Seq(text="x")
    out = writer.write(p, {"facts": []}, [], {}, client=fake_client(fm), spend=tmp_path / "s.json", today=date(2026, 10, 24))
    assert out["writer"] == "claude" and out["script"]["hook"].startswith("Crude oil") and len(fm.calls) == 2 and p.topic["patch_tries"] == writer.PATCH_TRIES


def test_a_non_fixable_rejection_goes_straight_to_a_full_rewrite(tmp_path):
    p = _piece(); p.topic["revise"] = "originality: too close to an earlier script"
    fm = FakeMessages(text=json.dumps(good_script()))
    writer.write(p, {"facts": []}, [], {}, client=fake_client(fm), spend=tmp_path / "s.json", today=date(2026, 10, 24))
    assert "PATCH MODE" not in fm.calls[0]["messages"][0]["content"]


def test_batch_lane_carries_the_patch_at_half_price(tmp_path):
    from tests.test_writebatch import FakeBatches, _client
    p = _piece(); p.id = "2026-10-25-sglearning-long"                                          # the fake batch answers for this id
    fb = FakeBatches(["ended"], text=json.dumps({"scenes": [{"index": 1, "vo": "Batch se theek kiya."}]}))
    state, script = writebatch.write_piece(p, {"facts": []}, [], {}, None, client=_client(fb), spend=tmp_path / "s.json", today=date(2026, 10, 24),
                                           sleep=lambda s: None, clock=lambda: 0.0, patch_reasons=["numbers without a source: 4500"])
    assert state == "ready" and script["scenes"][1]["vo"] == "Batch se theek kiya."
    assert fb.creates[0][0][0]["params"]["max_tokens"] == 8000


def test_daily_budgets_stop_a_looping_piece_and_reset_tomorrow():
    p = pieces.Piece(id="x", channel="sglearning", kind="short", publish_day=date(2026, 10, 27))
    assert all(pipeline._allow(p, "drafts", 3) for _ in range(3)) and not pipeline._allow(p, "drafts", 3)
    p.ids["budget"]["day"] = "2000-01-01"                                                       # an old day: the allowance resets
    assert pipeline._allow(p, "drafts", 3)


def test_the_patch_request_numbers_every_scene_from_zero():
    p = _piece()
    params = writer.patch_params(p, {"facts": []}, [], {}, p.script, ["numbers without a source: 4500"])
    body = params["messages"][0]["content"]
    assert '"index": 0' in body and f'"index": {len(p.script["scenes"]) - 1}' in body and "0-based" in body
