import json
from datetime import date

from engine import credit


def _setup(tmp_path, topups, spend):
    (tmp_path / "content").mkdir(exist_ok=True); (tmp_path / "logs").mkdir(exist_ok=True)
    (tmp_path / "content" / "gemini-credit.json").write_text(json.dumps({"topups": topups}))
    (tmp_path / "logs" / "image-spend.json").write_text(json.dumps({d: {"inr": v} for d, v in spend.items()}))
    return tmp_path / "content"


def test_counts_down_from_the_newest_top_up(tmp_path):
    # 3 Nov 2026 fix (founder: "fix the credit count"): the top-up day's pictures are counted too, since they may have come from the new balance
    content = _setup(tmp_path, [{"day": "2026-10-29", "inr": 5000}], {"2026-10-29": 999, "2026-10-30": 200, "2026-10-31": 250, "2026-11-01": 150})
    e = credit.estimate(date(2026, 11, 2), tmp_path, content)
    assert e["spent"] == 2079 and e["left"] == 2921 and e["per_day"] == 260           # (999 + 600) x 1.3, no balance reading yet
    assert credit.line(date(2026, 11, 2), tmp_path, content).startswith("💳 Gemini credit left (estimate): about ₹2921 of ₹5000, about 11 days")


def test_warns_three_days_before_it_runs_out(tmp_path):
    content = _setup(tmp_path, [{"day": "2026-10-29", "inr": 1000}], {"2026-10-30": 200, "2026-10-31": 200, "2026-11-01": 200})
    assert credit.line(date(2026, 11, 2), tmp_path, content).startswith("🔴 Gemini credit nearly gone (estimate): about ₹220 left")


def test_an_unknown_amount_asks_for_it_and_no_file_says_nothing(tmp_path):
    content = _setup(tmp_path, [{"day": "2026-10-29", "inr": None}], {})
    assert "amount not recorded yet" in credit.line(date(2026, 10, 30), tmp_path, content)
    assert credit.line(date(2026, 10, 30), tmp_path / "x", tmp_path / "y") == ""


def test_every_logged_call_is_counted_not_just_pictures(tmp_path):
    content = _setup(tmp_path, [{"day": "2026-11-01", "inr": 1000}], {"2026-11-01": 100})
    (tmp_path / "logs" / "gemini-calls.jsonl").write_text("\n".join(json.dumps(r) for r in [
        {"at": "2026-11-01T10:00:00+00:00", "in": 1_000_000, "out": 100_000, "thought": 100_000, "search_queries": 2, "modalities": []},
        {"at": "2026-11-01T10:01:00+00:00", "in": 5, "out": 5, "thought": 0, "search_queries": 0, "modalities": ["IMAGE"]}]))   # a picture row is not counted twice
    (tmp_path / "logs" / "voice-budget.json").write_text(json.dumps({"2026-11-01": 10}))
    (tmp_path / "logs" / "voice-batch.jsonl").write_text(json.dumps({"at": "2026-11-01T12:00:00+00:00", "lines": 40}))
    day = credit.day_costs(tmp_path)["2026-11-01"]
    assert round(day, 2) == round(100 + 26 + 44 + 6 + 15 + 30, 2)


def test_a_real_balance_reading_teaches_the_meter_its_factor(tmp_path):
    topups = [{"day": "2026-11-03", "inr": 1975}, {"day": "2026-11-06", "inr": 1959, "spent_since_previous": 2000}]
    content = _setup(tmp_path, topups, {"2026-11-03": 300, "2026-11-04": 200, "2026-11-05": 500, "2026-11-06": 100})
    assert credit.estimate(date(2026, 11, 6), tmp_path, content)["factor"] == 2.0       # 2000 really spent over 1000 metered
    topups[1]["spent_since_previous"] = 99999
    content = _setup(tmp_path, topups, {"2026-11-03": 300, "2026-11-04": 200, "2026-11-05": 500})
    assert credit.estimate(date(2026, 11, 6), tmp_path, content)["factor"] == 4.0       # clamped
