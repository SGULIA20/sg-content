import json
from datetime import date, datetime, timezone

from engine import commentdm, instagram, pieces, publish, threads, ytlink

NOW = datetime(2026, 10, 26, 16, 0, tzinfo=timezone.utc)          # 21:30 IST on 26 Oct


def _piece(root, pid, ch, kind, day, ids, title="t"):
    p = pieces.Piece(id=pid, channel=ch, kind=kind, publish_day=day, status="uploaded")
    p.ids = ids
    p.script = {"captions": {"youtube": {"title": title}}}
    pieces.save(p, root)
    return p


# ---- YouTube: each public Short points to the newest public long video of its channel ----
def test_a_public_short_gets_a_comment_and_a_description_line_pointing_to_the_long_video(tmp_path):
    _piece(tmp_path, "2026-10-24-sglearning-long", "sglearning", "long", date(2026, 10, 24), {"yt_id": "L1"}, "Credit card ka minimum due")
    _piece(tmp_path, "2026-10-28-sglearning-long", "sglearning", "long", date(2026, 10, 28), {"yt_id": "L2"})       # not public yet
    _piece(tmp_path, "2026-10-26-sglearning-short", "sglearning", "short", date(2026, 10, 26), {"yt_id": "S1"})
    _piece(tmp_path, "2026-10-27-sglearning-short", "sglearning", "short", date(2026, 10, 27), {"yt_id": "S2"})    # tomorrow: still private
    calls = []
    def call(method, url, token, json_body=None, **k):
        calls.append((method, url, json_body))
        if method == "GET":
            return 200, {}, {"items": [{"snippet": {"title": "x #Shorts", "categoryId": "27", "description": "old"}}]}
        return 200, {}, {"id": "c1"}
    import engine.youtube as yt
    real = yt.access_token
    yt.access_token = lambda ch, env=None: "tok"
    try:
        problems = ytlink.run(tmp_path, "sglearning", NOW, call=call)
    finally:
        yt.access_token = real
    assert problems == []
    put = next(c for c in calls if c[0] == "PUT")
    assert put[2]["snippet"]["description"].startswith("▶ Poori kahani, lambi video mein: Credit card ka minimum due\nhttps://youtu.be/L1")
    assert put[2]["snippet"]["title"] == "x #Shorts" and put[2]["snippet"]["categoryId"] == "27"           # nothing else changes
    assert any(c[0] == "POST" and "commentThreads" in c[1] for c in calls)
    assert pieces.load("2026-10-26-sglearning-short", root=tmp_path).ids["yt_long_link"] == "c1"
    assert pieces.load("2026-10-27-sglearning-short", root=tmp_path).ids.get("yt_long_link") is None


# ---- Threads: topic tag on every video post; one poll under it, never retried ----
def test_threads_video_carries_the_topic_tag_and_a_poll_reply_follows():
    seen = []
    def call(method, path, token, params=None):
        seen.append(params or {})
        if path.endswith("/threads"):
            return {"id": "c"}
        if path.endswith("/threads_publish"):
            return {"id": "p"}
        return {"status": "FINISHED"}
    threads.post_video("u", "t", "https://v", "text", call=call, sleep=lambda s: None, topic_tag="Personal Finance")
    assert seen[0]["topic_tag"] == "Personal Finance"
    threads.post_poll("u", "t", "parent1", call=call, sleep=lambda s: None)
    poll = next(p for p in seen if p.get("poll_attachment"))
    assert poll["reply_to_id"] == "parent1" and json.loads(poll["poll_attachment"]) == threads.POLL_OPTIONS


def test_a_failed_poll_never_holds_a_short_back_and_is_not_retried(tmp_path):
    p = pieces.Piece(id="2026-10-20-sglearning-short", channel="sglearning", kind="short", publish_day=date(2026, 10, 20), status="uploaded")
    p.ids = {"out_sha": "s", "yt_id": "y", "ig_reel_id": "r", "ig_story_id": "s1"}
    p.script = {"hook": "h", "scenes": [], "cards": [], "captions": {"instagram": {"caption": "c Yeh investment advice nahi hai", "hashtags": ["#A"]},
                                                                   "threads": {"text": "t", "hashtags": []}}}
    pieces.save(p, tmp_path)
    def bad_poll(*a):
        raise threads.ThreadsError("polls not allowed")
    env = {"IG_ACCESS_TOKEN": "t", "IG_USER_ID": "u", "THREADS_ACCESS_TOKEN": "tt", "THREADS_USER_ID": "tu", "GITHUB_REPOSITORY": "r"}
    publish.run(tmp_path, "sglearning", datetime(2026, 10, 20, 7, 30, tzinfo=timezone.utc), env, ig_publish=lambda piece, env: piece,
                threads_post=lambda *a, **k: "th1", threads_poll=bad_poll, notify=lambda t: True)
    got = pieces.load(p.id, root=tmp_path)
    assert got.status == "posted" and got.ids["threads_poll_id"].startswith("skipped")


# ---- Instagram: comment APP, get the right link by DM, once ----
def test_comments_asking_for_the_app_get_one_dm_with_the_right_link(tmp_path):
    _piece(tmp_path, "2026-10-25-arthvan-short", "arthvan", "short", date(2026, 10, 25), {"ig_reel_id": "M1"})
    sends, notes = [], []
    def call(method, path, token, params=None):
        if path.endswith("/media"):
            return {"data": [{"id": "M1", "timestamp": "2026-10-25T16:00:00+0000"}, {"id": "M2", "caption": "ScoreMyBiz new feature", "timestamp": "2026-10-25T10:00:00+0000"},
                             {"id": "OLD", "timestamp": "2026-10-01T10:00:00+0000"}]}
        if path.endswith("/comments"):
            mid = path.split("/")[1]
            return {"data": {"M1": [{"id": "c1", "text": "APP please", "timestamp": "2026-10-26T10:00:00+0000", "from": {"id": "fan"}},
                                     {"id": "c2", "text": "Happy to see this", "timestamp": "2026-10-26T10:00:00+0000", "from": {"id": "fan"}},
                                     {"id": "c3", "text": "app", "timestamp": "2026-10-26T10:00:00+0000", "from": {"id": "me"}}],
                             "M2": [{"id": "c4", "text": "link?", "timestamp": "2026-10-26T11:00:00+0000", "from": {"id": "fan2"}}]}.get(mid, [])}
        if path.endswith("/messages"):
            sends.append((json.loads(params["recipient"])["comment_id"], json.loads(params["message"])["text"]))
            return {"message_id": "x"}
        raise AssertionError(path)
    env = {"IG_ACCESS_TOKEN": "t", "IG_USER_ID": "me"}
    state = tmp_path / "dm.json"
    out = commentdm.run(env, NOW, call=call, notify=notes.append, root=tmp_path, state_path=state)
    assert out["sent"] == 2 and [s[0] for s in sends] == ["c1", "c4"]                   # "Happy" is not "app"; our own comment is skipped
    assert "waypoint" in sends[0][1] and "scoremybiz" in sends[1][1] and "utm_medium%3Ddm" in sends[0][1]
    sends.clear()
    commentdm.run(env, NOW, call=call, notify=notes.append, root=tmp_path, state_path=state)
    assert sends == []                                                                  # never twice


def test_a_missing_messaging_permission_is_reported_once_a_day(tmp_path):
    notes = []
    def call(method, path, token, params=None):
        if path.endswith("/media"):
            return {"data": [{"id": "M2", "caption": "", "timestamp": "2026-10-25T10:00:00+0000"}]}
        if path.endswith("/comments"):
            return {"data": [{"id": "c9", "text": "APP", "timestamp": "2026-10-26T11:00:00+0000", "from": {"id": "fan"}}]}
        raise instagram.InstagramError("HTTP 403: (#200) requires instagram_business_manage_messages permission")
    env = {"IG_ACCESS_TOKEN": "t", "IG_USER_ID": "me"}
    for _ in range(2):
        commentdm.run(env, NOW, call=call, notify=notes.append, root=tmp_path, state_path=tmp_path / "dm.json")
    assert len(notes) == 1 and "permission" in notes[0]


def test_instagram_captions_ask_people_to_comment_app():
    assert "Comment karein APP" in instagram.DM_ASK["sglearning"] and "Waypoint" in instagram.DM_ASK["arthvan"]
