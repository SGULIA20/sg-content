import pytest

from engine import threads


class FakeCall:
    def __init__(self):
        self.calls = []

    def __call__(self, method, path, token, params=None):
        self.calls.append((method, path, dict(params or {})))
        if path.endswith("/threads"):
            return {"id": "c9"}
        if path.endswith("/threads_publish"):
            return {"id": "post9"}
        return {"status": "FINISHED"}


def test_post_video_creates_then_publishes():
    fc = FakeCall()
    assert threads.post_video("uid", "tok", "https://x/reel.mp4", "Oil 100? #PaiseKiKhabar", call=fc, sleep=lambda s: None) == "post9"
    create = fc.calls[0]
    assert create[1] == "/uid/threads" and create[2]["media_type"] == "VIDEO" and create[2]["video_url"] == "https://x/reel.mp4"
    assert fc.calls[-1][1] == "/uid/threads_publish" and fc.calls[-1][2]["creation_id"] == "c9"


def test_threads_text_within_500():
    with pytest.raises(threads.ThreadsError):
        threads.post_video("uid", "tok", "https://x/r.mp4", "y" * 501, call=FakeCall(), sleep=lambda s: None)


def test_text_builder_joins_two_hashtags():
    assert threads.text_for({"text": "Oil 100?", "hashtags": ["#A", "#B"]}) == "Oil 100?\n\n#A #B"
