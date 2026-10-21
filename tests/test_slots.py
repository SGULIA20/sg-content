from datetime import date, datetime, timezone

from engine import slots


def test_slot_utc_crosses_date_boundary():
    assert slots.utc_for(date(2026, 10, 20), "20:00") == datetime(2026, 10, 20, 14, 30, tzinfo=timezone.utc)
    assert slots.utc_for(date(2026, 10, 20), "01:00") == datetime(2026, 10, 19, 19, 30, tzinfo=timezone.utc)


def test_ist_converts_from_utc():
    assert slots.ist(datetime(2026, 10, 19, 19, 30, tzinfo=timezone.utc)).date() == date(2026, 10, 20)


def test_arthvan_shorts_every_day():
    assert len(slots.publish_dates("arthvan", "short", date(2026, 10, 19), 7)) == 7      # founder's table, 21 Oct 2026


def test_sglearning_shorts_every_day():
    assert len(slots.publish_dates("sglearning", "short", date(2026, 10, 19), 7)) == 7


def test_sglearning_long_includes_saturday():
    assert date(2026, 10, 24) in slots.publish_dates("sglearning", "long", date(2026, 10, 19), 7)


def test_arthvan_long_includes_sunday():
    assert date(2026, 10, 25) in slots.publish_dates("arthvan", "long", date(2026, 10, 19), 7)


def test_piece_id_format():
    assert slots.piece_id(date(2026, 10, 20), "sglearning", "short") == "2026-10-20-sglearning-short"


def test_ig_slot_blocks_app_job_window():
    assert not slots.ig_slot_ok(datetime(2026, 10, 20, 20, 30))
    assert not slots.ig_slot_ok(datetime(2026, 10, 20, 19, 10))
    assert slots.ig_slot_ok(datetime(2026, 10, 20, 13, 0))
    assert slots.ig_slot_ok(datetime(2026, 10, 20, 21, 30))


def test_publish_at_for_piece_kind():
    assert slots.publish_at("sglearning", "short", date(2026, 10, 20)) == datetime(2026, 10, 20, 14, 30, tzinfo=timezone.utc)
    assert slots.publish_at("arthvan", "long", date(2026, 10, 24)) == datetime(2026, 10, 24, 13, 30, tzinfo=timezone.utc)


def test_two_long_days_per_channel():
    # sglearning: Wednesday and Saturday; arthvan: Thursday and Sunday (founder's table, 21 Oct 2026)
    assert slots.publish_dates("sglearning", "long", date(2026, 10, 19), 7) == [date(2026, 10, 21), date(2026, 10, 24)]
    assert slots.publish_dates("arthvan", "long", date(2026, 10, 19), 7) == [date(2026, 10, 22), date(2026, 10, 25)]
