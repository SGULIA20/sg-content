import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from engine import metaboost, pieces

NOW = datetime(2026, 11, 8, 3, 30, tzinfo=timezone.utc)
CFG = json.loads((Path(__file__).resolve().parent.parent / "content" / "meta-boost.json").read_text())
ENV = {"META_ACCESS_TOKEN": "t", "META_AD_ACCOUNT_ID": "123", "META_PAGE_ID": "p1", "IG_USER_ID": "ig1"}


def _piece(root, pid, day, ig="r1", intro=True, extra=None):
    p = pieces.Piece(id=pid, channel="sglearning", kind="short", publish_day=day)
    p.status = "posted"; p.ids = {"ig_reel_id": ig, **({"intro": {"ok": 1}} if intro else {}), **(extra or {})}
    pieces.save(p, root); return p


def _metrics(root, rows):
    (root / "logs").mkdir(exist_ok=True)
    (root / "logs" / "diagnosis.json").write_text(json.dumps({"rows": rows}))


GOOD = {"ig_views": 900, "ig_skip_rate": 30, "ig_watch_s": 25}


class FakeMeta:
    def __init__(self, currency="INR"):
        self.calls, self.currency, self.n = [], currency, 0

    def __call__(self, method, path, token, params=None):
        self.calls.append((method, path, params))
        if method == "GET" and "insights" in path:
            return {"data": [{"spend": "349.5", "reach": "4000"}]}
        if method == "GET":
            return {"currency": self.currency}
        self.n += 1
        return {"id": f"id{self.n}"}


def test_the_gate_picks_the_best_reel_with_the_intro(tmp_path):
    _piece(tmp_path, "2026-11-07-sglearning-short", date(2026, 11, 7))
    _piece(tmp_path, "2026-11-07-arthvan-short", date(2026, 11, 7), ig="r2", extra={})
    _piece(tmp_path, "2026-11-06-sglearning-short", date(2026, 11, 6), ig="r3", intro=False)          # no intro: never boosted
    _piece(tmp_path, "2026-11-05-sglearning-short", date(2026, 11, 5), ig="r4", extra={"ig_reposted_from": {"x": 1}})   # stale numbers
    _metrics(tmp_path, [{"id": "2026-11-07-sglearning-short", **GOOD},
                        {"id": "2026-11-07-arthvan-short", "ig_views": 900, "ig_skip_rate": 55, "ig_watch_s": 30},      # skipped too often
                        {"id": "2026-11-06-sglearning-short", **GOOD}, {"id": "2026-11-05-sglearning-short", **GOOD}])
    got = [p.id for _s, p, _r in metrics_candidates(tmp_path)]
    assert got == ["2026-11-07-sglearning-short"]


def metrics_candidates(root):
    return metaboost.candidates(root, CFG, NOW)


def test_probe_mode_creates_everything_paused_and_spends_nothing(tmp_path):
    _piece(tmp_path, "2026-11-07-sglearning-short", date(2026, 11, 7)); _metrics(tmp_path, [{"id": "2026-11-07-sglearning-short", **GOOD}])
    meta, notes = FakeMeta(), []
    out = metaboost.run(tmp_path, NOW, ENV, notes.append, dict(CFG, mode="probe"), meta)
    assert out == "probe: 2026-11-07-sglearning-short"
    posts = [c for c in meta.calls if c[0] == "POST"]
    assert [c[1].split("/")[-1] for c in posts] == ["campaigns", "adsets", "adcreatives", "ads"]
    assert all(c[2].get("status", "PAUSED") == "PAUSED" for c in posts)
    assert posts[1][2]["daily_budget"] == 35000 and posts[2][2]["source_instagram_media_id"] == "r1"
    assert "PAUSED" in notes[0]
    assert metaboost.spent(metaboost._state(tmp_path), date(2026, 11, 1)) == 0               # a probe costs nothing


def test_live_mode_switches_the_three_objects_on_and_one_boost_a_day(tmp_path):
    _piece(tmp_path, "2026-11-07-sglearning-short", date(2026, 11, 7)); _metrics(tmp_path, [{"id": "2026-11-07-sglearning-short", **GOOD}])
    meta = FakeMeta()
    assert metaboost.run(tmp_path, NOW, ENV, lambda t: None, dict(CFG, mode="live"), meta) == "live: 2026-11-07-sglearning-short"
    assert len([c for c in meta.calls if c[0] == "POST" and (c[2] or {}).get("status") == "ACTIVE"]) == 3
    assert metaboost.run(tmp_path, NOW, ENV, lambda t: None, dict(CFG, mode="live"), meta).startswith("no boost: today's boost")


def test_caps_use_meta_spend_and_stop_a_boost_that_would_pass_them(tmp_path):
    live = lambda d, spend=None: {"day": f"2026-11-0{d}", "piece": f"p{d}", "mode": "live", "planned": 350, "spend": spend}
    state = {"boosts": [live(d) for d in range(3, 9)]}                    # 6 x 350 planned = 2100 in the window; one more fits (2450)
    assert metaboost.room(dict(CFG), state, date(2026, 11, 9)) is None
    state["boosts"][-1] = live(8, 420.0)                                   # Meta says the last one really cost 420: 2170 + 350 > 2500
    assert "7-day cap" in metaboost.room(dict(CFG), state, date(2026, 11, 9))
    probe = {"day": "2026-11-09", "piece": "x", "mode": "probe", "planned": 350}
    assert metaboost.spent({"boosts": [probe]}, date(2026, 11, 1)) == 0    # a probe is never counted as spend


def test_a_wrong_currency_or_missing_secrets_create_nothing(tmp_path):
    _piece(tmp_path, "2026-11-07-sglearning-short", date(2026, 11, 7)); _metrics(tmp_path, [{"id": "2026-11-07-sglearning-short", **GOOD}])
    meta, notes = FakeMeta("USD"), []
    assert metaboost.run(tmp_path, NOW, ENV, notes.append, dict(CFG), meta).startswith("failed:")
    assert not [c for c in meta.calls if c[0] == "POST"] and "USD" in notes[0]
    assert metaboost.run(tmp_path, NOW, {}, lambda t: None, dict(CFG), FakeMeta()).startswith("skipped:")
    assert metaboost.run(tmp_path, NOW, ENV, lambda t: None, dict(CFG, enabled=False), FakeMeta()) == "off"


def test_the_founders_pause_pauses_live_boosts(tmp_path, monkeypatch):
    monkeypatch.setattr(metaboost.telegram, "paused", lambda root=None: True)
    metaboost._save(tmp_path, {"boosts": [{"day": "2026-11-07", "piece": "p", "mode": "live", "ids": {"campaign": "c", "adset": "s", "ad": "a"}, "planned": 350}]})
    meta = FakeMeta()
    assert metaboost.run(tmp_path, NOW, ENV, lambda t: None, dict(CFG), meta) == "paused by the founder"
    assert [c[1] for c in meta.calls] == ["/a", "/s", "/c"] and all(c[2] == {"status": "PAUSED"} for c in meta.calls)
