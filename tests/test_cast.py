from pathlib import Path

from engine import cast

MEMBERS = {"sg": {"description": "SG", "refs": []}, "papa": {"description": "Papa", "refs": []}}


def test_each_channel_uses_only_its_own_drawings(tmp_path, monkeypatch):
    monkeypatch.setattr(cast, "CAST_DIR", tmp_path)
    (tmp_path / "sglearning").mkdir()
    (tmp_path / "sglearning" / "sg.png").write_bytes(b"clay")
    assert cast.refs_for("SG smiles", channel="sglearning", members=MEMBERS, draw_missing=False) == [tmp_path / "sglearning" / "sg.png"]
    assert cast.refs_for("SG smiles", channel="arthvan", members=MEMBERS, draw_missing=False) == []     # never the other channel's look


def test_a_missing_member_is_drawn_in_that_channels_style(tmp_path, monkeypatch):
    monkeypatch.setattr(cast, "CAST_DIR", tmp_path)
    prompts = []
    def paint(prompt, out, **kw):
        prompts.append(prompt); Path(out).parent.mkdir(parents=True, exist_ok=True); Path(out).write_bytes(b"png"); return Path(out)
    monkeypatch.setattr(cast.art, "paint", paint)
    got = cast.refs_for("Papa reads", channel="arthvan", members=MEMBERS)
    assert got == [tmp_path / "arthvan" / "papa.png"]
    assert "comic" in prompts[0].lower() and "one single figure only" in prompts[0].lower()


def test_both_channels_have_their_whole_cast_drawn():
    for channel in ("sglearning", "arthvan"):
        missing = [n for n in cast.load() if not (cast.CAST_DIR / channel / f"{n}.png").exists()]
        assert missing == [], f"{channel}: {missing}"
