import wave

import numpy as np

from engine import sfx


def test_sounds_are_short_and_bounded():
    for name, fn in sfx.SOUNDS.items():
        s = fn()
        assert 0.05 < len(s) / sfx.RATE < 0.5 and np.max(np.abs(s)) <= 1.0, name


def test_events_cover_every_moving_scene_and_ticks_only_numbers():
    ev = sfx.events_for([0.0, 4.0, 8.0], [True, False, True])
    names = [n for _t, n in ev]
    assert names.count("whoosh") == 3 and names.count("pop") == 3 and names.count("tick") == 2
    assert (4.0 + sfx.POP_AT, "pop") in ev and (4.0 + sfx.TICK_AT, "tick") not in ev


def test_track_writes_a_wav_of_the_right_length(tmp_path):
    out = sfx.track(sfx.events_for([0.0, 3.0], [True, True]), 7.0, tmp_path / "s.wav")
    with wave.open(str(out)) as w:
        assert w.getnchannels() == 1 and abs(w.getnframes() / w.getframerate() - 8.0) < 0.01
