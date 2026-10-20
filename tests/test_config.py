from engine import config


def test_channels_have_two_keys():
    assert set(config.CHANNELS) == {"sglearning", "arthvan"}


def test_arthvan_short_days_are_mon_wed_fri():
    assert config.CHANNELS["arthvan"].short_days == {0, 2, 4}


def test_sglearning_shorts_every_day_and_longs_wed_sun():
    ch = config.CHANNELS["sglearning"]
    assert ch.short_days == {0, 1, 2, 3, 4, 5, 6}
    assert ch.long_days == {2, 6}


def test_budgets_match_spec():
    assert config.BUDGETS == {"voice_requests_per_day": 80, "image_inr_per_day": 250, "claude_usd_per_day": 3.0}


def test_video_sizes():
    assert config.VIDEO["short"] == (1080, 1920)
    assert config.VIDEO["long"] == (1920, 1080)
    assert config.VIDEO["fps"] == 30


def test_today_ist_crosses_date_line():
    from datetime import datetime, timezone, date
    assert config.today_ist(datetime(2026, 10, 19, 22, 30, tzinfo=timezone.utc)) == date(2026, 10, 20)
    assert config.today_ist(datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)) == date(2026, 10, 19)
