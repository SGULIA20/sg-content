from datetime import date
from types import SimpleNamespace as P

from engine import instagram, pieces, publish, storyframe, tracks

LIST = {"source": "https://incompetech.com/music/royalty-free/mp3-royaltyfree/",
        "arthvan": [{"title": "Five Armies", "filename": "Five Armies.mp3"}, {"title": "Heroic Age", "filename": "Heroic Age.mp3"}], "sglearning": []}


def test_a_piece_always_gets_the_same_track_and_a_channel_with_none_gets_nothing():
    """Founder, 24 Nov 2026: 'Why can't this music automised. You have everything just do it'."""
    a = tracks.pick(P(id="2026-12-03-arthvan-short", channel="arthvan"), LIST)
    assert a == tracks.pick(P(id="2026-12-03-arthvan-short", channel="arthvan"), LIST) and a["title"] in ("Five Armies", "Heroic Age")
    assert tracks.url({**a, "filename": "Five Armies.mp3"}).endswith("/mp3-royaltyfree/Five%20Armies.mp3")
    assert tracks.pick(P(id="2026-12-03-sglearning-short", channel="sglearning"), LIST) is None
    real = tracks.load()
    assert len(real["sglearning"]) >= 10 and len(real["arthvan"]) >= 10 and all(t["filename"].endswith(".mp3") for t in real["arthvan"])


def test_a_failed_or_tiny_download_gives_none_so_the_code_made_sound_is_used(tmp_path):
    t = {"title": "Five Armies", "filename": "Five Armies.mp3", "source": LIST["source"]}
    def boom(u):
        raise OSError("no network")
    assert tracks.fetch(t, tmp_path / "t.mp3", get=boom) is None
    assert tracks.fetch(t, tmp_path / "t.mp3", get=lambda u: b"<html>not found</html>") is None
    assert tracks.fetch(t, tmp_path / "t.mp3", get=lambda u: b"x" * 300_000).stat().st_size == 300_000


def test_the_credit_goes_wherever_the_video_goes():
    p = pieces.Piece(id="2026-12-03-arthvan-short", channel="arthvan", kind="short", publish_day=date(2026, 12, 3))
    p.script = {"captions": {"instagram": {"caption": "Trojan Horse sach tha?", "hashtags": ["#SGMythWorld"]}, "threads": {"text": "Trojan Horse sach tha?", "hashtags": []}}, "scenes": []}
    assert "Kevin MacLeod" not in instagram.caption_text(p) and "Kevin MacLeod" not in publish.threads_text(p)      # no track, no credit
    p.ids["music"] = {"title": "Five Armies"}
    assert 'Music: "Five Armies" Kevin MacLeod (incompetech.com), CC BY 4.0' in instagram.caption_text(p)
    assert "Kevin MacLeod (incompetech.com)" in publish.threads_text(p) and len(publish.threads_text(p)) <= 500
    full = tracks.credit(p.ids["music"])
    assert "Creative Commons: By Attribution 4.0" in full and "creativecommons.org/licenses/by/4.0" in full
    p.script["captions"]["threads"]["text"] = "x" * 480
    assert publish.threads_text(p).endswith("CC BY 4.0") and len(publish.threads_text(p)) <= 500                   # a long post is trimmed, the credit stays
    mix = storyframe.track_mix(58.0, speech_end=55.0)
    assert "[4:a]" not in mix and "I=-22" in mix and "sidechaincompress" in mix and "gt(t,55.000)" in mix          # music only, well under the voice


def test_the_engines_own_sound_check_still_passes_with_a_track_under_the_voice(tmp_path, monkeypatch):
    """24 Nov 2026: the first music mix kept the track at full level under the end card, and qa.narration_intact, which tells a lost last
    word from a kept one by the drop after the narration, turned the video down. A real mix is built here and put through that check."""
    import subprocess
    from engine import music, qa
    total, speech_end = 12.0, 9.0
    voice, song = tmp_path / "voice.wav", tmp_path / "song.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=300:duration=9", "-af",
                    "volume='if(lt(mod(t,3),2.4),1,0)':eval=frame", str(voice)], check=True)                       # speech-like bursts, the last ending at 8.4 s
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "anoisesrc=d=30:c=pink:a=0.5", str(song)], check=True)   # a dense, loud "track"
    bed = music.bed("light", total + 5, tmp_path)
    out = tmp_path / "mix.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c=black:s=320x240:d={total}", "-i", str(voice), "-stream_loop", "-1", "-i", str(bed),
                    "-stream_loop", "-1", "-i", str(song), "-filter_complex", storyframe.track_mix(total, speech_end=speech_end),
                    "-map", "0:v", "-map", "[aout]", "-t", str(total), "-c:a", "aac", str(out)], check=True, timeout=120)
    assert qa.narration_intact(out, speech_end=8.4)
    monkeypatch.delenv("SG_MUSIC", raising=False)
    assert tracks.on() is True
    monkeypatch.setenv("SG_MUSIC", "0")
    assert tracks.on() is False


def test_a_video_about_a_disaster_gets_a_quiet_track_and_learning_has_no_dance_music():
    """Founder, 24 Nov 2026: 'Motivator music looks like dancing music'; Bhopal 1984 is in the plan."""
    real = tracks.load()
    sad = pieces.Piece(id="2026-12-03-sglearning-short", channel="sglearning", kind="short", publish_day=date(2026, 12, 3))
    sad.topic = {"title": "Bhopal mein 3 December 1984 ki raat kya hua tha?", "summary": "The gas leak disaster."}
    assert tracks.sober(sad) and tracks.pick(sad, real)["title"] in {t["title"] for t in real["sober"]}
    ok = pieces.Piece(id="2026-12-04-sglearning-short", channel="sglearning", kind="short", publish_day=date(2026, 12, 4))
    ok.topic = {"title": "Film ke trailer mein poori kahani kyun dikha dete hain?"}
    assert not tracks.sober(ok)
    assert not any({"Grooving", "Bouncy"} & set(t["feel"]) for t in real["sglearning"]) and "Motivator" not in {t["title"] for t in real["sglearning"]}
