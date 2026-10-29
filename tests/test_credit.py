import json
from datetime import date

from engine import credit


def _setup(tmp_path, topups, spend):
    (tmp_path / "content").mkdir(); (tmp_path / "logs").mkdir()
    (tmp_path / "content" / "gemini-credit.json").write_text(json.dumps({"topups": topups}))
    (tmp_path / "logs" / "image-spend.json").write_text(json.dumps({d: {"inr": v} for d, v in spend.items()}))
    return tmp_path / "content"


def test_counts_down_from_the_newest_top_up(tmp_path):
    content = _setup(tmp_path, [{"day": "2026-10-29", "inr": 3000}], {"2026-10-29": 999, "2026-10-30": 200, "2026-10-31": 250, "2026-11-01": 150})
    e = credit.estimate(date(2026, 11, 2), tmp_path, content)
    assert e["spent"] == 960 and e["left"] == 2040 and e["per_day"] == 320          # the top-up day itself is not counted
    assert credit.line(date(2026, 11, 2), tmp_path, content).startswith("💳 Gemini credit left (estimate): about ₹2040 of ₹3000, about 6 days")


def test_warns_three_days_before_it_runs_out(tmp_path):
    content = _setup(tmp_path, [{"day": "2026-10-29", "inr": 1000}], {"2026-10-30": 200, "2026-10-31": 200, "2026-11-01": 200})
    assert credit.line(date(2026, 11, 2), tmp_path, content).startswith("🔴 Gemini credit nearly gone (estimate): about ₹40 left")


def test_an_unknown_amount_asks_for_it_and_no_file_says_nothing(tmp_path):
    content = _setup(tmp_path, [{"day": "2026-10-29", "inr": None}], {})
    assert "amount not recorded yet" in credit.line(date(2026, 10, 30), tmp_path, content)
    assert credit.line(date(2026, 10, 30), tmp_path / "x", tmp_path / "y") == ""
