import wave

from engine import sfx, storyframe


def test_effects_land_on_the_first_word_each_picture_change_and_before_the_reveal():
    """Founder, 24 Nov 2026: 'yes, upgrade the sound'."""
    cues = sfx.cue_points([0, 4, 9, 15, 21, 27, 33, 40, 46, 52], 58.0)
    assert cues["hit"] == [0.0] and cues["whoosh"] == [4, 9, 15, 21, 27, 33, 40, 46, 52]
    assert cues["riser"] == [40.0]                                    # the scene starting nearest two thirds of the way in
    long_ = sfx.cue_points([i * 1.0 for i in range(60)], 60.0)
    assert len(long_["whoosh"]) < 25                                  # a fast-cut long is not whooshed on every picture


def test_the_tracks_are_the_right_length_and_not_silent(tmp_path):
    fx = sfx.track([0, 4, 9, 15, 21], 25.0, tmp_path / "fx.wav")
    g = sfx.groove("suspense", 25.0, tmp_path / "g.wav")
    for f, secs in ((fx, 25.5), (g, 25.0)):
        with wave.open(str(f)) as w:
            assert w.getframerate() == sfx.RATE and w.getnchannels() == 2 and abs(w.getnframes() / sfx.RATE - secs) < 0.1
            assert max(w.readframes(w.getnframes())) > 0
    assert sfx.MOODS == {"sglearning": "upbeat", "arthvan": "suspense"}


def test_the_designed_mix_ducks_the_music_under_the_voice_and_can_be_switched_off(tmp_path):
    graph = storyframe.designed_mix(58.0)
    assert "sidechaincompress" in graph and "[4:a]" in graph and graph.endswith("[aout]")
    assert "sidechaincompress" not in storyframe.plain_mix(58.0)
    (tmp_path / "content").mkdir(); (tmp_path / "content" / "sound.json").write_text('{"design": false}')
    assert sfx.on(tmp_path) is False and sfx.on(tmp_path / "nowhere") is True
