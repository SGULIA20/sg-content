import json
from datetime import date
from types import SimpleNamespace as NS

import pytest

from engine import pieces, writebatch, writer
from tests.test_writer import good_script


def _piece():
    p = pieces.Piece(id="2026-10-25-sglearning-long", channel="sglearning", kind="long", publish_day=date(2026, 10, 25))
    p.topic = {"title": "t"}
    return p


class FakeBatches:
    """Records creates; each retrieve returns the next status; results yield one message."""
    def __init__(self, statuses, text=None, result_type="succeeded", stop="end_turn"):
        self.creates, self.statuses, self.text, self.result_type, self.stop = [], list(statuses), text or json.dumps(good_script()), result_type, stop

    def create(self, requests, betas):
        self.creates.append((requests, betas)); return NS(id=f"msgbatch_{len(self.creates)}", processing_status="in_progress")

    def cancel(self, bid):
        self.cancelled = bid

    def retrieve(self, bid):
        return NS(id=bid, processing_status=self.statuses.pop(0) if self.statuses else "ended")

    def results(self, bid):
        msg = NS(content=[NS(type="text", text=self.text)], usage=NS(input_tokens=5000, output_tokens=2000), stop_reason=self.stop, model="claude-opus-5-5")
        yield NS(custom_id="2026-10-25-sglearning-long", result=NS(type=self.result_type, message=msg, error="boom"))


def _client(batches):
    return NS(beta=NS(messages=NS(batches=batches)))


def test_one_request_per_draft_with_the_shared_opus_params_and_half_price(tmp_path):
    fb = FakeBatches(["in_progress", "ended"])
    p = _piece()
    state, script = writebatch.write_piece(p, {"facts": [], "summary": ""}, [], {}, "F", client=_client(fb), spend=tmp_path / "s.json", today=date(2026, 10, 22),
                                           sleep=lambda s: None, clock=lambda: 0.0)
    assert state == "ready" and script["hook"].startswith("Crude oil") and "write_batch" not in p.ids
    reqs, betas = fb.creates[0]
    assert len(reqs) == 1 and reqs[0]["custom_id"] == p.id and reqs[0]["params"]["model"] == "claude-opus-5-5" and betas == writebatch.BETAS
    assert reqs[0]["params"]["output_config"]["format"]["type"] == "json_schema" and "F" in reqs[0]["params"]["system"][0]["text"]
    assert writer.spent_today(tmp_path / "s.json", date(2026, 10, 22)) == pytest.approx(0.5 * writer.cost_usd(NS(input_tokens=5000, output_tokens=2000)))


def test_a_slow_batch_parks_the_piece_and_the_next_run_collects_the_same_job(tmp_path):
    fb = FakeBatches(["in_progress", "in_progress", "ended"])
    p = _piece(); t = iter([0.0, 0.0, 700.0, 700.0])
    state, script = writebatch.write_piece(p, {"facts": []}, [], {}, "F", client=_client(fb), spend=tmp_path / "s.json", today=date(2026, 10, 22),
                                           wait_s=600, sleep=lambda s: None, clock=lambda: next(t))
    assert state == "writing" and script is None and p.ids["write_batch"]["id"] == "msgbatch_1"
    state, script = writebatch.write_piece(p, {"facts": []}, [], {}, "F", client=_client(fb), spend=tmp_path / "s.json", today=date(2026, 10, 22),
                                           sleep=lambda s: None, clock=lambda: 0.0)
    assert state == "ready" and len(fb.creates) == 1                            # polled, not resubmitted


def test_a_draft_already_ordered_is_collected_even_when_the_request_changed(tmp_path):
    fb = FakeBatches(["in_progress", "ended"])
    p = _piece()
    state, _ = writebatch.write_piece(p, {"facts": []}, [], {}, "F", client=_client(fb), spend=tmp_path / "s.json", today=date(2026, 10, 22),
                                      wait_s=0, sleep=lambda s: None, clock=lambda: 0.0)
    assert state == "writing"
    state, script = writebatch.write_piece(p, {"facts": [{"text": "new"}]}, [], {}, "F2", client=_client(fb), spend=tmp_path / "s.json",
                                           today=date(2026, 10, 22), sleep=lambda s: None, clock=lambda: 0.0)
    assert state == "ready" and len(fb.creates) == 1             # 27 Oct 2026: re-ordering on each small change kept the 2 Nov Shorts parked


def test_a_batch_running_over_two_hours_is_cancelled_and_written_directly(tmp_path):
    fb = FakeBatches(["in_progress"] * 5)
    p = _piece(); p.ids["write_batch"] = {"id": "msgbatch_old", "key": "k", "tries": 1, "at": 1000.0}
    with pytest.raises(writebatch.WriteBatchError, match="writing directly"):
        writebatch.write_piece(p, {"facts": []}, [], {}, "F", client=_client(fb), spend=tmp_path / "s.json", today=date(2026, 10, 22),
                               wait_s=0, sleep=lambda s: None, clock=lambda: 0.0, now=lambda: 1000.0 + writebatch.STALE_S)
    assert fb.cancelled == "msgbatch_old" and "write_batch" not in p.ids and fb.creates == []
    p.ids["write_batch"] = {"id": "msgbatch_new", "key": "k", "tries": 1, "at": 1000.0}           # under two hours: keep waiting
    state, _ = writebatch.write_piece(p, {"facts": []}, [], {}, "F", client=_client(fb), spend=tmp_path / "s.json", today=date(2026, 10, 22),
                                      wait_s=0, sleep=lambda s: None, clock=lambda: 0.0, now=lambda: 1000.0 + 60)
    assert state == "writing"


def test_a_revision_is_a_new_request(tmp_path):
    fb = FakeBatches(["ended", "ended"])
    p = _piece()
    writebatch.write_piece(p, {"facts": []}, [], {}, "F", client=_client(fb), spend=tmp_path / "s.json", today=date(2026, 10, 22), sleep=lambda s: None, clock=lambda: 0.0)
    p.topic["revise"] = "length: trim"
    writebatch.write_piece(p, {"facts": []}, [], {}, "F", client=_client(fb), spend=tmp_path / "s.json", today=date(2026, 10, 22), sleep=lambda s: None, clock=lambda: 0.0)
    assert len(fb.creates) == 2 and "trim" in fb.creates[1][0][0]["params"]["messages"][0]["content"]


def test_errors_become_write_batch_errors(tmp_path):
    for fb in (FakeBatches(["ended"], result_type="errored"), FakeBatches(["ended"], stop="max_tokens"), FakeBatches(["ended"], text="not json")):
        with pytest.raises((writebatch.WriteBatchError, writer.WriterError)):
            writebatch.write_piece(_piece(), {"facts": []}, [], {}, "F", client=_client(fb), spend=tmp_path / "s.json", today=date(2026, 10, 22), sleep=lambda s: None, clock=lambda: 0.0)


def test_writer_uses_the_batch_lane_then_falls_back_to_the_synchronous_request(tmp_path):
    from tests.test_writer import FakeMessages, fake_client
    p = _piece()
    out = writer.write(p, {"facts": []}, [], {}, formula="F", client=fake_client(FakeMessages(text="{}")), spend=tmp_path / "s.json", today=date(2026, 10, 22),
                       batch_fn=lambda *a, **k: ("writing", None))
    assert out["state"] == "writing" and out["script"] is None
    fm = FakeMessages(text=json.dumps(good_script()))
    def broken(*a, **k):
        raise writebatch.WriteBatchError("lane down")
    out = writer.write(p, {"facts": []}, [], {}, formula="F", client=fake_client(fm), spend=tmp_path / "s.json", today=date(2026, 10, 22), batch_fn=broken)
    assert out["writer"] == "claude" and out["script"]["hook"].startswith("Crude oil") and len(fm.calls) == 1
