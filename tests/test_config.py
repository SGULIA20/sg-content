from engine import config


def test_channels_have_two_keys():
    assert set(config.CHANNELS) == {"sglearning", "arthvan"}


def test_arthvan_shorts_every_day_and_longs_thu_sun():
    assert config.CHANNELS["arthvan"].short_days == {0, 1, 2, 3, 4, 5, 6}
    assert config.CHANNELS["arthvan"].long_days == {3, 6}


def test_sglearning_shorts_every_day_and_longs_wed_sat():
    ch = config.CHANNELS["sglearning"]
    assert ch.short_days == {0, 1, 2, 3, 4, 5, 6}
    assert ch.long_days == {2, 5}


def test_budgets_match_spec():
    assert config.BUDGETS == {"voice_requests_per_day": 80, "image_inr_per_day": 900, "claude_usd_per_day": 10.0,
                              "image_inr_per_month": 6000, "claude_usd_per_month": 45.0}


def test_video_sizes():
    assert config.VIDEO["short"] == (1080, 1920)
    assert config.VIDEO["long"] == (1920, 1080)
    assert config.VIDEO["fps"] == 30


def test_today_ist_crosses_date_line():
    from datetime import datetime, timezone, date
    assert config.today_ist(datetime(2026, 10, 19, 22, 30, tzinfo=timezone.utc)) == date(2026, 10, 20)
    assert config.today_ist(datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)) == date(2026, 10, 19)


def test_today_pacific_follows_the_gemini_quota_window():
    from datetime import datetime, timezone
    from engine.config import today_pacific
    assert today_pacific(datetime(2026, 10, 21, 6, 59, tzinfo=timezone.utc)).isoformat() == "2026-10-20"   # 23:59 PDT the day before
    assert today_pacific(datetime(2026, 10, 21, 7, 1, tzinfo=timezone.utc)).isoformat() == "2026-10-21"
