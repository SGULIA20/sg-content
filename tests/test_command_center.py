import json

from engine import command_center, pieces, secrets, telegram
from engine.config import ROOT


def _no_dotenv(tmp_path, monkeypatch):
    monkeypatch.setattr(secrets, "DOTENV", tmp_path / "no.env")          # the real .env on this machine must not leak into the test


def test_tmp_root_never_calls_out_and_uses_cache(tmp_path, monkeypatch):
    _no_dotenv(tmp_path, monkeypatch)
    calls = []
    env = {"SG_COMMAND_KEY": "k" * 32}
    assert command_center.remote_paused(tmp_path, env, call=lambda *a: calls.append(a)) is False
    command_center._remember(tmp_path, True)
    assert command_center.remote_paused(tmp_path, env, call=lambda *a: calls.append(a)) is True
    assert calls == []


def test_remote_answer_is_cached_and_survives_an_outage(monkeypatch, tmp_path):
    _no_dotenv(tmp_path, monkeypatch)
    monkeypatch.setattr(command_center, "_live", lambda root: True)
    env = {"SG_COMMAND_KEY": "k" * 32}
    assert command_center.remote_paused(tmp_path, env, call=lambda m, r, k, b=None: {"paused": True}) is True
    assert command_center.remote_paused(tmp_path, env, call=lambda m, r, k, b=None: None) is True    # unreachable: last answer
    assert command_center.remote_paused(tmp_path, env, call=lambda m, r, k, b=None: {"paused": False}) is False


def test_no_key_means_no_call(monkeypatch, tmp_path):
    _no_dotenv(tmp_path, monkeypatch)
    monkeypatch.setattr(command_center, "_live", lambda root: True)
    assert command_center.report(tmp_path, "x", {}, call=lambda *a: (_ for _ in ()).throw(AssertionError("called"))) is False


def test_telegram_pause_follows_the_page_flag(tmp_path, monkeypatch):
    _no_dotenv(tmp_path, monkeypatch)
    assert telegram.paused(tmp_path) is False
    command_center._remember(tmp_path, True)                     # paused from the page
    assert telegram.paused(tmp_path) is True
    telegram.set_paused(False, tmp_path)                         # /resume clears both
    assert telegram.paused(tmp_path) is False
    telegram.set_paused(True, tmp_path)
    assert telegram.paused(tmp_path) is True and command_center.cached_paused(tmp_path) is True


def test_snapshot_lists_pieces_runs_spend_and_scrubs(tmp_path, monkeypatch):
    from datetime import date
    p = pieces.Piece(id="2026-10-21-sglearning-short", channel="sglearning", kind="short", publish_day=date(2026, 10, 21),
                     status="failed-voice", reasons=["a", "b", "voice 429 key supersecretvalue9"])
    pieces.save(p, tmp_path)
    pieces.save(pieces.Piece(id="preview-x", channel="sglearning", kind="short", publish_day=date(2026, 10, 21)), tmp_path)
    logs = tmp_path / "logs"
    logs.mkdir(exist_ok=True)
    (logs / "runs.jsonl").write_text(json.dumps({"day": "2026-10-21", "ok": True}) + "\nnot json\n")
    (logs / "voice-budget.json").write_text(json.dumps({"2026-10-19": 4, "2026-10-20": 100, "2026-10-21": 13, "2026-10-18": 1}))
    secrets.remember("supersecretvalue9")
    s = command_center.snapshot(tmp_path, "produce-end")
    assert [x["id"] for x in s["pieces"]] == ["2026-10-21-sglearning-short"]
    assert s["pieces"][0]["status"] == "failed-voice" and "supersecretvalue9" not in json.dumps(s)
    assert s["runs"] == [{"day": "2026-10-21", "ok": True}]
    assert list(s["spend"]["voice_requests"]) == ["2026-10-19", "2026-10-20", "2026-10-21"]


def test_live_only_for_the_project_root(tmp_path):
    assert command_center._live(ROOT) is True and command_center._live(tmp_path) is False


def test_telegram_setup_sends_token_on_and_nothing_off(tmp_path, monkeypatch):
    _no_dotenv(tmp_path, monkeypatch)
    seen = []
    call = lambda m, r, k, b=None: seen.append((r, b)) or {"webhook": b.get("on")}
    env = {"SG_COMMAND_KEY": "k" * 32, "TELEGRAM_BOT_TOKEN": "123:abc", "TELEGRAM_CHAT_ID": "42"}
    assert command_center.telegram_setup(True, env, call=call) == {"webhook": True}
    assert seen[-1] == ("telegram-setup", {"on": True, "token": "123:abc", "chat_id": "42"})
    command_center.telegram_setup(False, env, call=call)
    assert seen[-1] == ("telegram-setup", {"on": False})
    assert command_center.telegram_setup(True, {}, call=call) is None                  # no key: nothing sent


def test_mac_inbox_reads_the_control_room_when_the_webhook_is_on(tmp_path, monkeypatch):
    _no_dotenv(tmp_path, monkeypatch)
    monkeypatch.setattr(command_center, "telegram_inbox", lambda root: ["ok 2026-10-22-sglearning-short"])
    env = {"TELEGRAM_BOT_TOKEN": "t", "TELEGRAM_CHAT_ID": "42"}
    sent = []
    got = telegram.poll_commands(env, state=tmp_path / "off.json", get=lambda u: (_ for _ in ()).throw(AssertionError("getUpdates called")),
                                 post=lambda u, b: sent.append(b) or {"ok": True}, root=tmp_path, handler=lambda text: "filed " + text)
    assert got == ["ok 2026-10-22-sglearning-short"] and sent[0]["text"] == "filed ok 2026-10-22-sglearning-short"


def test_webhook_off_falls_back_to_get_updates(tmp_path, monkeypatch):
    _no_dotenv(tmp_path, monkeypatch)
    monkeypatch.setattr(command_center, "telegram_inbox", lambda root: None)
    env = {"TELEGRAM_BOT_TOKEN": "t", "TELEGRAM_CHAT_ID": "42"}
    updates = {"result": [{"update_id": 1, "message": {"chat": {"id": 42}, "text": "/pause"}}]}
    got = telegram.poll_commands(env, state=tmp_path / "off.json", get=lambda u: updates, post=lambda u, b: {"ok": True}, root=tmp_path,
                                 handler=lambda text: None)
    assert got == ["/pause"]


def test_inbox_is_none_without_key_or_off(tmp_path, monkeypatch):
    _no_dotenv(tmp_path, monkeypatch)
    monkeypatch.setattr(command_center, "_live", lambda root: True)
    env = {"SG_COMMAND_KEY": "k" * 32}
    assert command_center.telegram_inbox(tmp_path, {}, call=lambda *a: {"webhook": True, "messages": ["x"]}) is None
    assert command_center.telegram_inbox(tmp_path, env, call=lambda *a: {"webhook": False, "messages": []}) is None
    assert command_center.telegram_inbox(tmp_path, env, call=lambda *a: {"webhook": True, "messages": ["a", "b"]}) == ["a", "b"]
