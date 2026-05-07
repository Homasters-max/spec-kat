"""Tests for sdd.infra.session_context — I-SESSION-CONTEXT-1."""
from __future__ import annotations

import json
import pathlib

from sdd.infra.session_context import get_current_session_id, set_current_session


def test_get_returns_none_when_file_absent(tmp_path: pathlib.Path) -> None:
    path = str(tmp_path / "no_such_file.json")
    assert get_current_session_id(session_file=path) is None


def test_get_returns_none_on_invalid_json(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "current_session.json"
    path.write_text("not valid json{{{", encoding="utf-8")
    assert get_current_session_id(session_file=str(path)) is None


def test_set_then_get_returns_uuid(tmp_path: pathlib.Path) -> None:
    path = str(tmp_path / "current_session.json")
    session_id = "550e8400-e29b-41d4-a716-446655440000"
    set_current_session(session_id, "IMPLEMENT", 55, session_file=path)
    assert get_current_session_id(session_file=path) == session_id


def test_set_writes_valid_iso8601_declared_at(tmp_path: pathlib.Path) -> None:
    from datetime import datetime

    path = str(tmp_path / "current_session.json")
    set_current_session("abc-123", "IMPLEMENT", 55, session_file=path)

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    declared_at = data["declared_at"]
    parsed = datetime.fromisoformat(declared_at)
    assert parsed.tzinfo is not None, "declared_at must be timezone-aware"


def test_set_writes_correct_fields(tmp_path: pathlib.Path) -> None:
    path = str(tmp_path / "current_session.json")
    set_current_session("my-uuid", "VALIDATE", 42, session_file=path)

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    assert data["session_id"] == "my-uuid"
    assert data["session_type"] == "VALIDATE"
    assert data["phase_id"] == 42
    assert "declared_at" in data
