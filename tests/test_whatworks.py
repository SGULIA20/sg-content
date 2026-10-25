from datetime import date

from engine import art, pieces, whatworks

ENV = {"IG_ACCESS_TOKEN": "ig", "THREADS_ACCESS_TOKEN": "th"}


def _short(root, day, ch, yt, ig=None, th=None, look=None):
    p = pieces.Piece(id=f"{day.isoformat()}-{ch}-short", channel=ch, kind="short", publish_day=day, status="posted")
    p.ids = {"yt_id": yt, **({"ig_reel_id": ig} if ig else {}), **({"threads_id": th} if th else {})}
    p.topic = {"title": f"story {yt}", **({"look": look} if look else {})}
    pieces.save(p, root)


def test_each_short_gets_its_numbers_from_every_platform_and_old_pieces_count_as_doodle(tmp_path):
    _short(tmp_path, date(2026, 10, 20), "sglearning", "v1", ig="m1", th="t1")
    _short(tmp_path, date(2026, 10, 29), "sglearning", "v2", look="claymation")
    yt = lambda ch, s, e, env: {"v1": {"views": 300, "watched_pct": 61.5, "watched_s": 30}, "v2": {"views": 900, "watched_pct": 70.0, "watched_s": 35}}
    ig = lambda mid, tok: {"views": 1000, "saved": 4, "reels_skip_rate": 42}
    th = lambda mid, tok: {"views": 50}
    rows = whatworks.collect(date(2026, 10, 18), date(2026, 10, 31), ENV, tmp_path, yt=yt, ig=ig, th=th)
    assert [r["look"] for r in rows] == ["doodle", "claymation"]
    assert rows[0]["reach"] == 300 + 1000 + 50 and rows[0]["ig_skip_rate"] == 42 and rows[1]["reach"] == 900
    looks = whatworks.by_look(rows)
    assert looks["sglearning"]["claymation"] == {"shorts": 1, "avg_reach": 900, "avg_watched_pct": 70.0}
    out = whatworks.text(rows, looks)
    assert "report only" in out and "strongest: story v1" in out and "look claymation" in out


def test_a_platform_that_fails_never_stops_the_report(tmp_path):
    _short(tmp_path, date(2026, 10, 20), "arthvan", "v9", ig="m9")
    def broken(*a, **k):
        raise RuntimeError("analytics down")
    rows = whatworks.collect(date(2026, 10, 18), date(2026, 10, 25), ENV, tmp_path, yt=broken, ig=lambda m, t: {}, th=lambda m, t: {})
    assert rows[0]["yt_views"] == 0 and rows[0]["reach"] == 0


def test_instagram_metric_names_meta_does_not_know_are_skipped_one_by_one():
    def call(method, path, token, params):
        if "," in params["metric"] or params["metric"] == "reels_skip_rate":
            raise RuntimeError("invalid metric")
        return {"data": [{"name": params["metric"], "values": [{"value": 7}]}]}
    got = whatworks.instagram_numbers("m1", "tok", call=call)
    assert got["views"] == 7 and "reels_skip_rate" not in got


def test_the_look_name_comes_from_the_channel_style_file():
    assert art.look("sglearning") == "claymation" and art.look("arthvan") == "indian-comic"


def _row(ch, views, hook, skip=50.0):
    return {"channel": ch, "ig_views": views, "hook": hook, "ig_skip_rate": skip, "ig_watch_s": 9.0}


def test_lessons_keep_the_three_best_and_worst_openings_per_channel():
    from engine import whatworks
    rows = [_row("sglearning", v, f"h{v}") for v in (59, 1449, 1235, 300, 1358, 20)] + [_row("arthvan", 100, "x")]
    out = whatworks.lessons(rows)
    assert [b["hook"] for b in out["sglearning"]["best"]] == ["h1449", "h1358", "h1235"]
    assert [w["hook"] for w in out["sglearning"]["worst"]] == ["h20", "h59", "h300"]
    assert "arthvan" not in out                                    # one Short teaches nothing yet
    assert "sglearning" not in whatworks.lessons(rows[:5])         # five would put a Short in both lists


def test_writer_gets_the_lessons_for_its_channel_only(tmp_path):
    import json
    from engine import writer
    f = tmp_path / "hook-lessons.json"
    f.write_text(json.dumps({"end": "2026-10-25", "sglearning": {"best": [{"hook": "Dividend free hai?"}], "worst": []}}))
    got = writer.hook_lessons("sglearning", f)
    assert got["best"][0]["hook"] == "Dividend free hai?" and "never copy" in got["note"]
    assert writer.hook_lessons("arthvan", f) == {} and writer.hook_lessons("sglearning", tmp_path / "none.json") == {}
