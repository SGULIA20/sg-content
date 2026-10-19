from datetime import date

import pytest

from engine import pieces, secrets


def _piece():
    return pieces.Piece(id="2026-10-20-sglearning-short", channel="sglearning", kind="short", publish_day=date(2026, 10, 20))


def test_new_piece_is_planned():
    assert _piece().status == "planned"


def test_save_then_load_roundtrip(tmp_path):
    p = _piece()
    p.topic = {"title": "Crude oil 100 dollar"}
    path = pieces.save(p, root=tmp_path)
    assert path == tmp_path / "pieces" / "2026-10-20-sglearning-short.json"
    q = pieces.load(p.id, root=tmp_path)
    assert q.topic == p.topic and q.publish_day == date(2026, 10, 20) and q.status == "planned"


def test_load_missing_returns_none(tmp_path):
    assert pieces.load("nope", root=tmp_path) is None


def test_transition_appends_reason_on_reject():
    p = pieces.transition(_piece(), "rejected", reason="advice: kharid lo")
    assert p.status == "rejected" and p.reasons == ["advice: kharid lo"] and p.updated


def test_save_refuses_secret_values(tmp_path):
    secrets.remember("sk-ant-secret-value")
    p = _piece()
    p.topic = {"note": "key sk-ant-secret-value leaked"}
    with pytest.raises(ValueError):
        pieces.save(p, root=tmp_path)


def test_list_all_sorted_by_id(tmp_path):
    a, b = _piece(), _piece()
    b.id, b.publish_day = "2026-10-19-arthvan-long", date(2026, 10, 19)
    pieces.save(a, root=tmp_path); pieces.save(b, root=tmp_path)
    assert [p.id for p in pieces.list_all(root=tmp_path)] == [b.id, a.id]
