from datetime import date

from engine import buffer, pieces


def _ready(root, pid, ch, kind, day, status="uploaded"):
    p = pieces.Piece(id=pid, channel=ch, kind=kind, publish_day=day); p.status = status; pieces.save(p, root)


def test_needed_orders_todays_shorts_then_one_long(tmp_path, monkeypatch):
    from engine import config
    monkeypatch.setattr(config, "ENABLED_KINDS", {"short", "long"})
    need = buffer.needed(tmp_path, date(2026, 10, 19))             # Monday: no long due today or tomorrow? arthvan long is Tue 20
    assert need[0] == (date(2026, 10, 19), "arthvan", "short") and need[1] == (date(2026, 10, 19), "sglearning", "short")
    assert need[2] == (date(2026, 10, 20), "arthvan", "long")          # then the earliest long, then tomorrow's Shorts
    assert {k for _d, _c, k in need} == {"short", "long"}


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
    assert (date(2026, 10, 25), "sglearning", "long") in need and (date(2026, 10, 24), "arthvan", "long") in need and (date(2026, 10, 21), "sglearning", "long") in need


def test_myth_short_needs_its_long(tmp_path):
    # the arthvan Short on Wed 21 Oct belongs to the long of Sat 17 Oct (the week's long is the previous Saturday's)
    assert buffer.long_for_short("arthvan", date(2026, 10, 21)) == "2026-10-20-arthvan-long"     # Tuesday's long
    assert buffer.long_for_short("arthvan", date(2026, 10, 24)) == "2026-10-20-arthvan-long"     # strictly before Saturday's
    assert buffer.long_for_short("arthvan", date(2026, 10, 25)) == "2026-10-24-arthvan-long"


def test_needed_skips_kinds_not_enabled(tmp_path, monkeypatch):
    from engine import config
    monkeypatch.setattr(config, "ENABLED_KINDS", {"short"})
    need = buffer.needed(tmp_path, date(2026, 10, 19))
    assert need and all(k == "short" for _d, _c, k in need)


def test_needed_puts_imminent_shorts_before_longs_and_one_long_per_batch(tmp_path, monkeypatch):
    from engine import config
    monkeypatch.setattr(config, "ENABLED_KINDS", {"short", "long"})
    need = buffer.needed(tmp_path, date(2026, 10, 21))              # Wednesday: both channels have a Short today, sglearning has a long today
    assert need[0] == (date(2026, 10, 21), "arthvan", "short") and need[1] == (date(2026, 10, 21), "sglearning", "short")
    assert need[2] == (date(2026, 10, 21), "sglearning", "long")
    assert need[3][2] == "short"                                      # the next long waits behind the next day's Shorts
