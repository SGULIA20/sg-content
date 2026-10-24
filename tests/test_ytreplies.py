from datetime import datetime, timezone
from types import SimpleNamespace

from engine import ytreplies

NOW = datetime(2026, 10, 26, 12, 0, tzinfo=timezone.utc)


class FakeClaude:
    def __init__(self, answers):
        self.answers, self.prompts = list(answers), []
        self.messages = self

    def create(self, **kw):
        self.prompts.append(kw["messages"][0]["content"])
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=self.answers.pop(0))])


def _call_factory(posted):
    def call(method, url, token, json_body=None, **k):
        if "channels?" in url:
            return 200, {}, {"items": [{"id": "OWN"}]}
        if "commentThreads" in url:
            return 200, {}, {"items": [
                {"snippet": {"topLevelComment": {"id": "c1", "snippet": {"videoId": "v1", "authorDisplayName": "Ravi", "textOriginal": "FD vs gold, kya karein?",
                                                                       "publishedAt": "2026-10-26T08:00:00Z", "authorChannelId": {"value": "X"}}}}},
                {"snippet": {"topLevelComment": {"id": "c2", "snippet": {"videoId": "v1", "authorDisplayName": "Spam", "textOriginal": "buy followers",
                                                                       "publishedAt": "2026-10-26T08:00:00Z", "authorChannelId": {"value": "Y"}}}}},
                {"snippet": {"topLevelComment": {"id": "c3", "snippet": {"videoId": "v1", "authorDisplayName": "Me", "textOriginal": "thanks",
                                                                       "publishedAt": "2026-10-26T08:00:00Z", "authorChannelId": {"value": "OWN"}}}}},
                {"snippet": {"topLevelComment": {"id": "c4", "snippet": {"videoId": "v1", "authorDisplayName": "Old", "textOriginal": "old one",
                                                                       "publishedAt": "2026-10-01T08:00:00Z", "authorChannelId": {"value": "Z"}}}}}]}
        if "videos?" in url:
            return 200, {}, {"items": [{"snippet": {"title": "Papa ki FD"}}]}
        if method == "POST" and "comments?" in url:
            posted.append(json_body["snippet"])
            return 200, {}, {"id": "r1"}
        raise AssertionError(url)
    return call


def test_new_comments_get_drafts_spam_and_own_and_old_ones_do_not_and_approved_ones_are_posted(tmp_path):
    posted, syncs = [], []
    def sync(new, done, failed=None, **kw):
        syncs.append((new, done, failed))
        return [{"id": 7, "channel": "sglearning", "comment_id": "c0", "draft": "Shukriya!"}] if len(syncs) == 1 else []
    claude = FakeClaude(["Ravi ji, video mein FD aur gold dono ka asar dikhaya hai; apne adviser se zaroor poochhiye.", "SKIP"] * 2)
    out = ytreplies.run({}, NOW, tmp_path, tmp_path / "s.json", call=_call_factory(posted), client=claude, sync=sync,
                        token_for=lambda ch, env=None: "tok")
    assert posted == [{"parentId": "c0", "textOriginal": "Shukriya!"}]                       # approved reply went out
    new, done, failed = syncs[-1]
    assert done == [7] and failed == []
    assert [d["comment_id"] for d in new] == ["c1"]                                             # c2 is spam (SKIP); c3 is our own; c4 is old
    assert new[0]["draft"].startswith("Ravi ji") and "Papa ki FD" in claude.prompts[0]
    assert out == {"posted": 1, "failed": 0, "drafts": 1}
    syncs.clear(); posted.clear()
    ytreplies.run({}, NOW, tmp_path, tmp_path / "s.json", call=_call_factory(posted), client=FakeClaude([]), sync=sync,
                  token_for=lambda ch, env=None: "tok")
    assert len(syncs) == 2 and syncs[-1][0] == []                                             # nothing is drafted twice
