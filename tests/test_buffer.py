from datetime import date

from engine import buffer, pieces


def _ready(root, pid, ch, kind, day, status="uploaded"):
    p = pieces.Piece(id=pid, channel=ch, kind=kind, publish_day=day); p.status = status; pieces.save(p, root)


def test_needed_orders_longs_first_then_shorts(tmp_path, monkeypatch):
    from engine import config
    monkeypatch.setattr(config, "ENABLED_KINDS", {"short", "long"})
    need = buffer.needed(tmp_path, date(2026, 10, 19))             # Monday
    assert need[0] == (date(2026, 10, 24), "arthvan", "long")        # longs are planned up to horizon_short + horizon_long days ahead
    kinds = [k for _d, _c, k in need]
    assert kinds[:2] == ["long", "long"] and all(k == "short" for k in kinds[2:])
    assert (date(2026, 10, 19), "sglearning", "short") in need and (date(2026, 10, 19), "arthvan", "short") in need


def test_needed_skips_uploaded_and_posted(tmp_path):
    _ready(tmp_path, "2026-10-19-sglearning-short", "sglearning", "short", date(2026, 10, 19))
    _ready(tmp_path, "2026-10-19-arthvan-short", "arthvan", "short", date(2026, 10, 19), "posted")
    need = buffer.needed(tmp_path, date(2026, 10, 19))
    assert (date(2026, 10, 19), "sglearning", "short") not in need and (date(2026, 10, 19), "arthvan", "short") not in need


def test_needed_retries_rejected_and_failed(tmp_path):
    _ready(tmp_path, "2026-10-19-sglearning-short", "sglearning", "short", date(2026, 10, 19), "rejected")
    _ready(tmp_path, "2026-10-20-sglearning-short", "sglearning", "short", date(2026, 10, 20), "failed-voice")
    need = buffer.needed(tmp_path, date(2026, 10, 19))
    assert (date(2026, 10, 19), "sglearning", "short") in need and (date(2026, 10, 20), "sglearning", "short") in need


def test_horizons_seven_days_shorts_and_long_within_window(tmp_path, monkeypatch):
    from engine import config
    monkeypatch.setattr(config, "ENABLED_KINDS", {"short", "long"})
    need = buffer.needed(tmp_path, date(2026, 10, 19), horizon_short=7, horizon_long=10)
    days = sorted({d for d, _c, k in need if k == "short"})
    assert days[0] == date(2026, 10, 19) and days[-1] == date(2026, 10, 25)
    assert (date(2026, 10, 25), "sglearning", "long") in need and (date(2026, 10, 24), "arthvan", "long") in need


def test_myth_short_needs_its_long(tmp_path):
    # the arthvan Short on Wed 21 Oct belongs to the long of Sat 17 Oct (the week's long is the previous Saturday's)
    assert buffer.long_for_short("arthvan", date(2026, 10, 21)) == "2026-10-17-arthvan-long"
    assert buffer.long_for_short("arthvan", date(2026, 10, 24)) == "2026-10-17-arthvan-long"
    assert buffer.long_for_short("arthvan", date(2026, 10, 25)) == "2026-10-24-arthvan-long"


def test_needed_skips_kinds_not_enabled(tmp_path, monkeypatch):
    from engine import config
    monkeypatch.setattr(config, "ENABLED_KINDS", {"short"})
    need = buffer.needed(tmp_path, date(2026, 10, 19))
    assert need and all(k == "short" for _d, _c, k in need)
