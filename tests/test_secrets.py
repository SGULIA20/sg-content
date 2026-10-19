import pytest

from engine import secrets


def test_env_wins_over_dotenv(tmp_path):
    (tmp_path / ".env").write_text("GEMINI_API_KEY=fromfile\n")
    assert secrets.get("GEMINI_API_KEY", env={"GEMINI_API_KEY": "fromenv"}, dotenv=tmp_path / ".env") == "fromenv"


def test_dotenv_used_when_env_empty(tmp_path):
    (tmp_path / ".env").write_text("# comment\nGEMINI_API_KEY='quoted'\n")
    assert secrets.get("GEMINI_API_KEY", env={}, dotenv=tmp_path / ".env") == "quoted"


def test_missing_secret_raises(tmp_path):
    with pytest.raises(secrets.MissingSecret):
        secrets.get("NOPE", env={}, dotenv=tmp_path / ".env")


def test_get_remembers_value_for_scrub(tmp_path):
    (tmp_path / ".env").write_text("TELEGRAM_BOT_TOKEN=12345:abcdef\n")
    secrets.get("TELEGRAM_BOT_TOKEN", env={}, dotenv=tmp_path / ".env")
    assert "12345:abcdef" not in secrets.scrub("sent to 12345:abcdef ok")


def test_scrub_blanks_known_values():
    secrets.remember("abc123")
    out = secrets.scrub("token abc123 here")
    assert "abc123" not in out and "here" in out


def test_ssl_context_is_a_context():
    import ssl
    assert isinstance(secrets.ssl_context(), ssl.SSLContext)
