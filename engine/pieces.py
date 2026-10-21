"""Piece records: one JSON file per piece under pieces/, the pipeline's durable state (spec §3, §7)."""
import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

from . import secrets
from .config import ROOT

STATUSES = {"voicing","planned", "researched", "written", "rejected", "voiced", "drawn", "assembled", "qa_failed", "uploaded", "posted",
            "awaiting-clips", "awaiting-confirm"}


@dataclass
class Piece:
    id: str
    channel: str
    kind: str
    publish_day: date
    status: str = "planned"
    topic: dict = field(default_factory=dict)
    facts: list = field(default_factory=list)
    script: dict | None = None
    timings: list = field(default_factory=list)
    ids: dict = field(default_factory=dict)
    writer: str = ""
    reasons: list = field(default_factory=list)
    updated: str = ""


def _dir(root: Path) -> Path:
    return Path(root) / "pieces"


def _default(o):
    if isinstance(o, (datetime, date)):
        return o.isoformat()
    raise TypeError(f"not serialisable: {type(o).__name__}")


def _to_json(p: Piece) -> str:
    d = asdict(p)
    d["publish_day"] = p.publish_day.isoformat()
    return json.dumps(d, ensure_ascii=False, sort_keys=True, indent=1, default=_default)


def save(p: Piece, root: Path = ROOT) -> Path:
    text = _to_json(p)
    if secrets.scrub(text) != text:
        raise ValueError(f"piece {p.id} contains a secret value; refusing to save")
    _dir(root).mkdir(parents=True, exist_ok=True)
    path = _dir(root) / f"{p.id}.json"
    path.write_text(text + "\n")
    return path


def load(piece_id: str, root: Path = ROOT) -> Piece | None:
    path = _dir(root) / f"{piece_id}.json"
    if not path.exists():
        return None
    d = json.loads(path.read_text())
    d["publish_day"] = date.fromisoformat(d["publish_day"])
    return Piece(**d)


def list_all(root: Path = ROOT) -> list:
    if not _dir(root).exists():
        return []
    return [load(p.stem, root) for p in sorted(_dir(root).glob("*.json"))]


def transition(p: Piece, status: str, reason: str | None = None) -> Piece:
    if status not in STATUSES and not status.startswith("failed-"):
        raise ValueError(f"unknown status {status}")
    p.status = status
    if reason:
        p.reasons.append(reason)
    p.updated = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return p
