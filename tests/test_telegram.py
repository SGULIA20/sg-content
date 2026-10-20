import json

from engine import secrets, telegram


def test_send_posts_to_chat_and_scrubs_secrets():
    seen = {}

    def post(url, body):
        seen["url"], seen["body"] = url, body
        return {"ok": True}

    secrets.remember("supersecrettoken1")
    env = {"TELEGRAM_BOT_TOKEN": "123:abc", "TELEGRAM_CHAT_ID": "42"}
    assert telegram.send("made 2, token supersecrettoken1", env, post=post) is True
    assert seen["url"].endswith("/bot123:abc/sendMessage") and seen["body"]["chat_id"] == "42"
    assert "supersecrettoken1" not in seen["body"]["text"]


def test_send_returns_false_without_config(tmp_path, monkeypatch):
    monkeypatch.setattr(secrets, "DOTENV", tmp_path / "no.env")          # the real .env on this machine must not leak into the test
    assert telegram.send("x", {}, post=lambda u, b: {"ok": True}) is False


def test_poll_commands_pause_and_resume(tmp_path):
    updates = {"result": [{"update_id": 7, "message": {"chat": {"id": 42}, "text": "/pause"}},
                          {"update_id": 8, "message": {"chat": {"id": 99}, "text": "/pause"}}]}
    env = {"TELEGRAM_BOT_TOKEN": "t", "TELEGRAM_CHAT_ID": "42"}
    sent = []
    cmds = telegram.poll_commands(env, state=tmp_path / "off.json", get=lambda u: updates, post=lambda u, b: sent.append(b) or {"ok": True}, root=tmp_path)
    assert cmds == ["/pause"] and (tmp_path / "logs" / "pause.json").exists()
    assert json.loads((tmp_path / "off.json").read_text())["offset"] == 9
    updates["result"] = [{"update_id": 9, "message": {"chat": {"id": 42}, "text": "/resume"}}]
    telegram.poll_commands(env, state=tmp_path / "off.json", get=lambda u: updates, post=lambda u, b: sent.append(b) or {"ok": True}, root=tmp_path)
    assert not (tmp_path / "logs" / "pause.json").exists() and any("resumed" in b["text"].lower() for b in sent)


def test_paused_flag_helper(tmp_path):
    assert telegram.paused(tmp_path) is False
    telegram.set_paused(True, tmp_path)
    assert telegram.paused(tmp_path) is True
