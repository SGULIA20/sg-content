import json
from datetime import date
from pathlib import Path

import pytest

from engine import pieces, pipeline, voice
from tests.test_writer import good_script

FACTS = [{"text": "Brent crossed $100", "number": 100.0, "unit": "USD", "source_url": "https://e/a", "source_name": "ET", "source_date": "2026-10-19", "quote": "q", "label": "reported"},
         {"text": "India imports 88% of crude", "number": 88.0, "unit": "pct", "source_url": "https://e/b", "source_name": "PPAC", "source_date": "2026-10-19", "quote": "q", "label": "official"}]
TOPIC = {"title": "Crude oil crosses $100", "link": "https://e/a", "summary": "s", "published": None, "source": "ET"}


def deps(tmp_path, **over):
    calls = {"research": 0, "write": 0, "say": 0, "paint": 0, "build": 0, "qa": 0, "upload": 0, "topics": 0}

    def topic_fn(piece, used):
        calls["topics"] += 1
        return dict(TOPIC, link=f"https://e/{calls['topics']}")

    def research_fn(topic, channel):
        calls["research"] += 1; return {"facts": FACTS, "summary": "s"}

    def write_fn(piece, sheet, library, hashtags):
        calls["write"] += 1; return {"script": good_script(), "writer": "claude", "note": ""}

    def say_fn(text, voice_id, out_wav):
        calls["say"] += 1
        import wave
        Path(out_wav).parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(out_wav), "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000); w.writeframes(b"\x00\x00" * 24000)
        return 1.0

    def paint_fn(prompt, out, **kw):
        calls["paint"] += 1; Path(out).parent.mkdir(parents=True, exist_ok=True); Path(out).write_bytes(b"png"); return Path(out)

    def card_fn(kind, data, out, size):
        Path(out).parent.mkdir(parents=True, exist_ok=True); Path(out).write_bytes(b"png"); return Path(out)

    def build_fn(piece, lines, visuals, size, out_dir, **kw):
        calls["build"] += 1; piece.timings = [float(i) for i in range(len(lines))]
        out = Path(out_dir) / ("reel.mp4" if piece.kind == "short" else "long.mp4"); out.write_bytes(b"mp4"); return out

    def qa_fn(path, kind, voiced_seconds, caption_cues, **kw):
        calls["qa"] += 1; return []

    def upload_fn(piece, video, thumb):
        calls["upload"] += 1; return "yt123"

    d = pipeline.Deps(topic=topic_fn, research=research_fn, write=write_fn, say=say_fn, paint=paint_fn, avatar=lambda pose: Path(tmp_path / f"{pose}.png"),
                      render_card=card_fn, build=build_fn, qa=qa_fn, upload=upload_fn, lint=lambda piece, prior: [],
                      claims_check=lambda piece: [], commons=lambda q, out: None)
    for k, v in over.items():
        setattr(d, k, v)
    return d, calls


def _piece(kind="short", channel="sglearning", day=date(2026, 10, 20)):
    return pieces.Piece(id=f"{day.isoformat()}-{channel}-{kind}", channel=channel, kind=kind, publish_day=day)


def test_make_runs_all_steps_and_uploads(tmp_path, monkeypatch):
    from engine import config
    monkeypatch.setattr(config, "STORY_FORMAT", {("sglearning", "short"), ("arthvan", "short")})   # presenter-era long path
    d, calls = deps(tmp_path)
    p = pipeline.make(_piece("long"), d, tmp_path)
    assert p.status == "uploaded" and p.ids["yt_id"] == "yt123" and p.writer == "claude"
    assert calls == {"research": 1, "write": 1, "say": 3, "paint": 1, "build": 1, "qa": 1, "upload": 1, "topics": 1}
    assert (tmp_path / "out" / p.id / "long.mp4").exists()
    assert pieces.load(p.id, tmp_path).status == "uploaded"


def test_make_rejected_script_tries_next_topic_up_to_three(tmp_path):
    d, calls = deps(tmp_path, lint=lambda piece, prior: ["advice: kharid lo"])
    p = pipeline.make(_piece(), d, tmp_path)
    assert p.status == "rejected" and calls["topics"] == 3 and calls["say"] == 0
    assert any("advice" in r for r in p.reasons)


def test_make_number_without_source_rejects(tmp_path):
    d, calls = deps(tmp_path, claims_check=lambda piece: [12.0])
    p = pipeline.make(_piece(), d, tmp_path)
    assert p.status == "rejected" and any("12" in r for r in p.reasons)


def test_make_voice_budget_marks_failed_voice_and_returns(tmp_path):
    def say_fn(text, voice_id, out_wav):
        raise voice.VoiceBudget("cap")
    d, calls = deps(tmp_path, say=say_fn)
    p = pipeline.make(_piece(), d, tmp_path)
    assert p.status == "failed-voice" and calls["build"] == 0 and pieces.load(p.id, tmp_path).status == "failed-voice"


def test_make_qa_failure_is_not_uploaded(tmp_path):
    d, calls = deps(tmp_path, qa=lambda *a, **k: ["loudness: -22 LUFS"])
    p = pipeline.make(_piece(), d, tmp_path)
    assert p.status == "qa_failed" and calls["upload"] == 0


def test_dry_run_never_calls_upload(tmp_path):
    d, calls = deps(tmp_path)
    p = pipeline.make(_piece(), d, tmp_path, dry_run=True)
    assert p.status == "assembled" and calls["upload"] == 0


def test_make_is_idempotent_for_uploaded_piece(tmp_path):
    d, calls = deps(tmp_path)
    p = _piece(); p.status = "uploaded"; p.ids["yt_id"] = "x"; pieces.save(p, tmp_path)
    pipeline.make(p, d, tmp_path)
    assert calls["write"] == 0


def test_myth_short_reuses_long_scenes(tmp_path, monkeypatch):
    from engine import config
    monkeypatch.setattr(config, "STORY_FORMAT", {("sglearning", "short")})
    long_p = _piece("long", "arthvan", date(2026, 10, 20))
    s = good_script(); s["scenes"] = s["scenes"] * 4                         # 12 scenes
    long_p.script = s; long_p.facts = FACTS; long_p.status = "uploaded"; long_p.topic = {"id": "dwarka-underwater", "hooks": ["h1", "h2", "h3"]}
    pieces.save(long_p, tmp_path)
    d, calls = deps(tmp_path)
    p = pipeline.make(_piece("short", "arthvan", date(2026, 10, 21)), d, tmp_path)
    assert calls["research"] == 0 and calls["write"] == 1                   # no new research; the writer cuts the Short from the long's scenes
    assert p.topic["from_long"] == "2026-10-20-arthvan-long" and p.status == "uploaded"


def test_myth_short_without_long_fails_cleanly(tmp_path, monkeypatch):
    from engine import config
    monkeypatch.setattr(config, "STORY_FORMAT", {("sglearning", "short")})
    d, calls = deps(tmp_path)
    p = pipeline.make(_piece("short", "arthvan", date(2026, 10, 21)), d, tmp_path)
    assert p.status == "failed-topic" and calls["write"] == 0


def test_myth_short_teases_next_long_when_previous_missing(tmp_path, monkeypatch):
    from engine import config
    monkeypatch.setattr(config, "STORY_FORMAT", {("sglearning", "short")})
    long_p = _piece("long", "arthvan", date(2026, 10, 24))
    long_p.script = good_script(); long_p.facts = FACTS; long_p.status = "uploaded"; long_p.topic = {"id": "dwarka-underwater", "hooks": ["h1", "h2", "h3"]}
    pieces.save(long_p, tmp_path)
    d, calls = deps(tmp_path)
    p = pipeline.make(_piece("short", "arthvan", date(2026, 10, 21)), d, tmp_path)
    assert p.topic["from_long"] == "2026-10-24-arthvan-long" and p.status == "uploaded"


def test_make_resumes_from_written_script_without_rewriting(tmp_path):
    d, calls = deps(tmp_path)
    p = _piece(); p.script = good_script(); p.facts = FACTS; p.topic = dict(TOPIC); p.status = "failed-voice"; p.writer = "claude"
    pieces.save(p, tmp_path)
    q = pipeline.make(p, d, tmp_path)
    assert calls["research"] == 0 and calls["write"] == 0 and calls["say"] == 3 and q.status == "uploaded"


def test_make_voice_api_error_marks_failed_voice(tmp_path):
    def say_fn(text, voice_id, out_wav):
        raise voice.VoiceError("429 quota")
    d, calls = deps(tmp_path, say=say_fn)
    p = pipeline.make(_piece(), d, tmp_path)
    assert p.status == "failed-voice" and "429" in p.reasons[-1]


def test_make_research_error_parks_piece_and_tries_next_topic(tmp_path):
    from engine import research
    n = {"calls": 0}

    def research_fn(topic, channel):
        n["calls"] += 1
        if n["calls"] == 1:
            raise research.ResearchError("empty reply")
        return {"facts": FACTS, "summary": "s"}

    d, calls = deps(tmp_path, research=research_fn)
    p = pipeline.make(_piece(), d, tmp_path)
    assert n["calls"] == 2 and p.status == "uploaded" and any("empty reply" in r for r in p.reasons)


def test_make_all_research_fails_marks_failed_research(tmp_path):
    from engine import gemini

    def research_fn(topic, channel):
        raise gemini.GeminiError("503 busy")

    d, calls = deps(tmp_path, research=research_fn)
    p = pipeline.make(_piece(), d, tmp_path)
    assert p.status == "failed-research" and calls["write"] == 0


def test_produce_keeps_resumable_status(tmp_path, monkeypatch):
    from engine import produce
    seen = {}
    p = _piece(); p.script = good_script(); p.facts = FACTS; p.topic = dict(TOPIC); p.status = "failed-voice"
    pieces.save(p, tmp_path)
    d, calls = deps(tmp_path)
    produce.run(tmp_path, date(2026, 10, 20), max_pieces=1, dry_run=True, only={"sglearning:short"}, deps=d, notify=lambda t: True)
    assert calls["write"] == 0 and calls["say"] == 3


def test_source_strip_follows_each_scenes_fact(tmp_path, monkeypatch):
    from engine import config
    monkeypatch.setattr(config, "STORY_FORMAT", {("sglearning", "short"), ("arthvan", "short")})   # presenter-era long path
    d, calls = deps(tmp_path)
    rendered = []
    def card_fn(kind, data, out, size):
        rendered.append((kind, data.get("name"))); Path(out).parent.mkdir(parents=True, exist_ok=True); Path(out).write_bytes(b"png"); return Path(out)
    d.render_card = card_fn
    p = _piece("long"); p.facts = [dict(FACTS[0], source_name="ET"), dict(FACTS[1], source_name="PPAC")]
    pipeline.make(p, d, tmp_path)
    assert {n for k, n in rendered if k == "source"} == {"ET", "PPAC"}


def test_commons_credit_reaches_description_and_scene(tmp_path, monkeypatch):
    from engine import config
    monkeypatch.setattr(config, "STORY_FORMAT", {("sglearning", "short"), ("arthvan", "short")})   # presenter-era long path
    d, calls = deps(tmp_path)
    def commons(q, out):
        Path(out).mkdir(parents=True, exist_ok=True); (Path(out) / "x.jpg").write_bytes(b"j")
        return {"path": Path(out) / "x.jpg", "credit": "Photographer, CC BY-SA 4.0, Wikimedia Commons", "title": "File:x.jpg", "url": "u"}
    d.commons = commons
    def write_fn(piece, sheet, library, hashtags):
        s = good_script(); s["scenes"][2]["visual"] = {"type": "photo", "prompt": "Dwarka", "card": None}; return {"script": s, "writer": "claude", "note": ""}
    d.write = write_fn
    p = pipeline.make(_piece("long"), d, tmp_path)
    assert p.script["scenes"][2].get("credit", "").startswith("Photographer")
    from engine import youtube
    from datetime import datetime, timezone
    assert "Photos:" in youtube.metadata(p, datetime(2026, 10, 20, 14, 30, tzinfo=timezone.utc), {})["snippet"]["description"]


def test_mid_scene_avatar_uses_avatar_card(tmp_path, monkeypatch):
    from engine import config
    monkeypatch.setattr(config, "STORY_FORMAT", {("sglearning", "short"), ("arthvan", "short")})   # presenter-era long path
    d, calls = deps(tmp_path)
    kinds = []
    def card_fn(kind, data, out, size):
        kinds.append(kind); Path(out).parent.mkdir(parents=True, exist_ok=True); Path(out).write_bytes(b"png"); return Path(out)
    d.render_card = card_fn
    def write_fn(piece, sheet, library, hashtags):
        s = good_script(); s["scenes"][1]["visual"] = {"type": "avatar", "prompt": "thinking", "card": None}; return {"script": s, "writer": "claude", "note": ""}
    d.write = write_fn
    pipeline.make(_piece("long"), d, tmp_path)
    assert kinds[:2] == ["hook", "avatar"]


def test_length_only_reject_asks_writer_to_revise_same_topic(tmp_path):
    n = {"lint": 0}

    def lint_fn(piece, prior):
        n["lint"] += 1
        return ["length: 150 words, allowed 90-135"] if n["lint"] == 1 else []

    seen = []

    def write_fn(piece, sheet, library, hashtags):
        seen.append(dict(piece.topic)); return {"script": good_script(), "writer": "claude", "note": ""}

    d, calls = deps(tmp_path, lint=lint_fn, write=write_fn)
    p = pipeline.make(_piece(), d, tmp_path)
    assert p.status == "uploaded" and calls["topics"] == 1 and calls["research"] == 1 and len(seen) == 2
    assert "revise" not in seen[0] and "150 words" in seen[1]["revise"]


def test_pack_mode_stops_after_script_and_sends_pack(tmp_path):
    d, calls = deps(tmp_path)
    sent = []
    d.pack = lambda piece: sent.append(piece.id) or [{"part": 1, "scene": 0, "narration": "n", "prompt": "p"}]
    d.pack_send = lambda piece, text: sent.append(("sent", piece.id)) or Path(tmp_path / "pack.txt")
    p = pipeline.make(_piece(), d, tmp_path, pack_mode=True)
    assert calls["say"] == 0 and calls["build"] == 0 and p.topic["pack"][0]["narration"] == "n" and ("sent", p.id) in sent


def test_produce_fallback_renders_stale_pack_near_slot(tmp_path):
    from datetime import datetime, timezone
    from engine import produce
    p = _piece(); p.script = good_script(); p.facts = FACTS; p.topic = dict(TOPIC, pack=[{"part": 1, "scene": 0, "narration": "n", "prompt": "p"}])
    p.status = "awaiting-clips"; pieces.save(p, tmp_path)
    d, calls = deps(tmp_path)
    # 20:00 IST slot on 20 Oct = 14:30 UTC; now = 12:00 UTC is within the 3-hour fallback window
    produce.run(tmp_path, date(2026, 10, 20), max_pieces=1, dry_run=True, only={"sglearning:short"}, deps=d, notify=lambda t: True,
                now_utc=datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc))
    q = pieces.load(p.id, tmp_path)
    assert calls["say"] == 3 and q.status == "assembled" and "pack cancelled" in q.reasons[-1]


def test_produce_leaves_fresh_pack_alone(tmp_path):
    from datetime import datetime, timezone
    from engine import produce
    p = _piece(); p.script = good_script(); p.facts = FACTS; p.topic = dict(TOPIC, pack=[{"part": 1, "scene": 0, "narration": "n", "prompt": "p"}])
    p.status = "awaiting-clips"; pieces.save(p, tmp_path)
    d, calls = deps(tmp_path)
    produce.run(tmp_path, date(2026, 10, 20), max_pieces=1, dry_run=True, only={"sglearning:short"}, deps=d, notify=lambda t: True,
                now_utc=datetime(2026, 10, 20, 3, 0, tzinfo=timezone.utc))
    assert calls["say"] == 0 and pieces.load(p.id, tmp_path).status == "awaiting-clips"


def test_avatar_scenes_use_cartoon_clips_when_enabled(tmp_path, monkeypatch):
    from engine import config
    monkeypatch.setattr(config, "STORY_FORMAT", {("sglearning", "short"), ("arthvan", "short")})   # presenter-era long path
    d, calls = deps(tmp_path)
    made = []
    def cartoon_fn(wav, seconds, size, out, mood):
        made.append(mood); Path(out).parent.mkdir(parents=True, exist_ok=True); Path(out).write_bytes(b"mp4"); return Path(out)
    d.cartoon = cartoon_fn
    seen = {}
    def build_fn(piece, lines, visuals, size, out_dir, **kw):
        seen["visuals"] = [Path(v).suffix for v in visuals]; piece.timings = [0.0, 1.0, 2.0]
        out = Path(out_dir) / "reel.mp4"; out.write_bytes(b"mp4"); return out
    d.build = build_fn
    pipeline.make(_piece("long"), d, tmp_path)
    assert made == ["explaining_front"] and seen["visuals"][0] == ".mp4"            # the hook scene (avatar) became a talking-head clip


def test_story_format_uses_panels_cast_refs_and_storyframe(tmp_path):
    d, calls = deps(tmp_path)
    painted, refs_seen, built = [], [], []
    def paint_fn(prompt, out, **kw):
        painted.append(kw.get("aspect")); refs_seen.append([Path(r).name for r in kw.get("refs", [])])
        Path(out).parent.mkdir(parents=True, exist_ok=True); Path(out).write_bytes(b"png"); return Path(out)
    def story_build(piece, lines, panels, size, out_dir):
        built.append(len(panels)); piece.timings = [0.0] * len(panels); out = Path(out_dir) / "reel.mp4"; out.write_bytes(b"mp4"); return out
    d.paint = paint_fn; d.story_build = story_build
    d.cast_refs = lambda prompt: [Path("/cast/sg.png")] if "SG" in prompt else []
    def write_fn(piece, sheet, library, hashtags):
        s = good_script(); s["title"] = "Papa ne 20 saal *FD* mein rakha 💔"
        for sc in s["scenes"]:
            sc["visual"] = {"type": "art", "prompt": "SG and PAPA at the dining table", "card": None}
        return {"script": s, "writer": "gemini", "note": ""}
    d.write = write_fn
    p = pipeline.make(_piece(), d, tmp_path)
    assert p.status == "uploaded" and built == [3] and calls["build"] == 0
    assert painted == ["4:5"] * 3 and refs_seen[0] == ["sg.png"]


def test_myth_story_short_is_standalone_and_panels_carry_labels(tmp_path, monkeypatch):
    from engine import config
    monkeypatch.setattr(config, "STORY_FORMAT", {("sglearning", "short"), ("arthvan", "short")})
    d, calls = deps(tmp_path)
    built = []
    d.story_build = lambda piece, lines, panels, size, out_dir: (built.append(piece.channel), setattr(piece, "timings", [0.0] * len(panels)), Path(out_dir, "reel.mp4").write_bytes(b"m"), Path(out_dir, "reel.mp4"))[-1]
    def write_fn(piece, sheet, library, hashtags):
        s = good_script(); s["title"] = "Samundar ke neeche *Dwarka*? 😱"
        for sc in s["scenes"]:
            sc["visual"] = {"type": "art", "prompt": "divers near stone walls", "card": None}; sc["label"] = "archaeology"
        return {"script": s, "writer": "claude", "note": ""}
    d.write = write_fn
    p = pipeline.make(_piece("short", "arthvan", date(2026, 10, 21)), d, tmp_path)
    assert p.status == "uploaded" and calls["research"] == 1 and built == ["arthvan"] and "from_long" not in p.topic
