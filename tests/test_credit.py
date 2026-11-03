import json
from datetime import date

from engine import credit


def _setup(tmp_path, topups, spend):
    (tmp_path / "content").mkdir(); (tmp_path / "logs").mkdir()
    (tmp_path / "content" / "gemini-credit.json").write_text(json.dumps({"topups": topups}))
    (tmp_path / "logs" / "image-spend.json").write_text(json.dumps({d: {"inr": v} for d, v in spend.items()}))
    return tmp_path / "content"


def test_counts_down_from_the_newest_top_up(tmp_path):
    # 3 Nov 2026 fix (founder: "fix the credit count"): the top-up day's pictures are counted too, since they may have come from the new balance
    content = _setup(tmp_path, [{"day": "2026-10-29", "inr": 5000}], {"2026-10-29": 999, "2026-10-30": 200, "2026-10-31": 250, "2026-11-01": 150})
    e = credit.estimate(date(2026, 11, 2), tmp_path, content)
    assert e["spent"] == 2558 and e["left"] == 2442 and e["per_day"] == 320           # (999 + 600) x 1.6
    assert credit.line(date(2026, 11, 2), tmp_path, content).startswith("💳 Gemini credit left (estimate): about ₹2442 of ₹5000, about 8 days")


def test_warns_three_days_before_it_runs_out(tmp_path):
    content = _setup(tmp_path, [{"day": "2026-10-29", "inr": 1000}], {"2026-10-30": 200, "2026-10-31": 200, "2026-11-01": 200})
    assert credit.line(date(2026, 11, 2), tmp_path, content).startswith("🔴 Gemini credit nearly gone (estimate): about ₹40 left")


def test_an_unknown_amount_asks_for_it_and_no_file_says_nothing(tmp_path):
    content = _setup(tmp_path, [{"day": "2026-10-29", "inr": None}], {})
    assert "amount not recorded yet" in credit.line(date(2026, 10, 30), tmp_path, content)
    assert credit.line(date(2026, 10, 30), tmp_path / "x", tmp_path / "y") == ""
