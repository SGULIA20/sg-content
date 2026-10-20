"""Secrets: os.environ first, then ROOT/.env. Values are remembered so scrub() can blank them from any log line."""
import os
import ssl
from pathlib import Path
from typing import Mapping

from .config import ROOT

DOTENV = ROOT / ".env"
_CAFILE = "/etc/ssl/cert.pem"
_KNOWN: set = set()


class MissingSecret(KeyError):
    pass


def _read_dotenv(path: Path) -> dict:
    out = {}
    if not Path(path).exists():
        return out
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def get(name: str, env: Mapping | None = None, dotenv: Path | None = None) -> str:
    env = os.environ if env is None else env
    value = env.get(name) or _read_dotenv(DOTENV if dotenv is None else dotenv).get(name)
    if not value:
        raise MissingSecret(name)
    remember(value)
    return value


def remember(value: str) -> None:
    if value and len(value) >= 6:
        _KNOWN.add(value)


def scrub(text: str) -> str:
    for v in _KNOWN:
        text = text.replace(v, "***")
    return text


def ssl_context() -> ssl.SSLContext:
    return ssl.create_default_context(cafile=_CAFILE) if os.path.exists(_CAFILE) else ssl.create_default_context()
