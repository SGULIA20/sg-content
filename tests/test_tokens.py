import json
from datetime import date

from engine import tokens


def test_refresh_writes_expiry_and_returns_new_tokens(tmp_path):
    def ig_refresh(token, call=None):
        return {"access_token": "newig", "expires_in": 5184000}

    def th_refresh(token, call=None):
        return {"access_token": "newth", "expires_in": 5184000}

    env = {"IG_ACCESS_TOKEN": "oldig", "THREADS_ACCESS_TOKEN": "oldth"}
    out = tokens.refresh(env, root=tmp_path, today=date(2026, 10, 20), ig_refresh=ig_refresh, th_refresh=th_refresh)
    assert out == {"IG_ACCESS_TOKEN": "newig", "THREADS_ACCESS_TOKEN": "newth"}
    data = json.loads((tmp_path / "logs" / "tokens.json").read_text())
    assert data["instagram_expires"] == "2026-12-19" and data["threads_expires"] == "2026-12-19"


def test_refresh_failure_is_reported_not_raised(tmp_path):
    def bad(token, call=None):
        raise RuntimeError("expired")
    out = tokens.refresh({"IG_ACCESS_TOKEN": "x", "THREADS_ACCESS_TOKEN": "y"}, root=tmp_path, today=date(2026, 10, 20), ig_refresh=bad, th_refresh=bad)
    assert out == {} and json.loads((tmp_path / "logs" / "tokens.json").read_text())["errors"]


def test_store_uses_gh_when_pat_present(monkeypatch):
    ran = []
    monkeypatch.setattr(tokens.subprocess, "run", lambda args, **kw: ran.append(args) or type("R", (), {"returncode": 0})())
    assert tokens.store({"IG_ACCESS_TOKEN": "newig"}, {"ACTIONS_PAT": "pat", "GITHUB_REPOSITORY": "SGULIA20/sg-content"}) == ["IG_ACCESS_TOKEN"]
    assert ran and ran[0][:3] == ["gh", "secret", "set"] and "newig" not in " ".join(ran[0])


def test_store_without_pat_returns_empty():
    assert tokens.store({"IG_ACCESS_TOKEN": "x"}, {}) == []
