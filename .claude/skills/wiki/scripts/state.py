from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from models import IngestLogEntry, QueryLogEntry


def _ingest_log_path(vault_root: Path) -> Path:
    return vault_root / ".wiki" / "state" / "ingest_log.jsonl"


def _query_log_path(vault_root: Path) -> Path:
    return vault_root / ".wiki" / "state" / "query_log.jsonl"


def append_ingest_log(vault_root: Path, entry: IngestLogEntry) -> None:
    path = _ingest_log_path(vault_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(entry)) + "\n")


def read_ingest_log(vault_root: Path) -> list[IngestLogEntry]:
    path = _ingest_log_path(vault_root)
    if not path.exists():
        return []
    entries = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            entries.append(IngestLogEntry(**json.loads(line)))
    return entries


def append_query_log(vault_root: Path, entry: QueryLogEntry) -> None:
    path = _query_log_path(vault_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(entry)) + "\n")


def read_query_log(vault_root: Path) -> list[QueryLogEntry]:
    path = _query_log_path(vault_root)
    if not path.exists():
        return []
    entries = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            entries.append(QueryLogEntry(**json.loads(line)))
    return entries
