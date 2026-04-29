"""Unit tests for InitProjectHandler — T-3203.

Acceptance: sdd init-project --name foo creates schema p_foo and record in shared.projects
Invariants: I-DB-SCHEMA-1, I-DB-1, I-HANDLER-PURE-1
"""
from __future__ import annotations

import dataclasses
import uuid
from unittest.mock import MagicMock, call, patch

import pytest

from sdd.commands.init_project import InitProjectHandler, ProjectInitializedEvent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@dataclasses.dataclass(frozen=True)
class _Cmd:
    command_id: str
    command_type: str = "InitProject"
    payload: dict = dataclasses.field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", dict(self.payload))


def _cmd(name: str = "foo", db_url: str | None = None) -> _Cmd:
    payload: dict = {"name": name}
    if db_url is not None:
        payload["db_url"] = db_url
    return _Cmd(command_id=str(uuid.uuid4()), payload=payload)


def _make_mock_conn() -> MagicMock:
    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value = cursor
    return conn, cursor


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def db_path(pg_test_db: str) -> str:
    """Isolated PG URL for idempotency checks (I-DB-TEST-1)."""
    return pg_test_db


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestInitProjectHandler:

    def test_creates_schema_and_project_record(self, db_path):
        """Acceptance criterion: --name foo → schema p_foo + shared.projects record."""
        conn, cursor = _make_mock_conn()

        with patch("sdd.commands.init_project.open_db_connection", return_value=conn):
            handler = InitProjectHandler(db_path)
            events = handler.handle(_cmd("foo"))

        assert len(events) == 1
        event = events[0]
        assert isinstance(event, ProjectInitializedEvent)
        assert event.project_name == "foo"
        assert event.db_schema == "p_foo"
        assert event.event_type == "ProjectInitialized"

        # Verify schema creation SQL (I-DB-SCHEMA-1)
        executed_sqls = [str(c.args[0]) for c in cursor.execute.call_args_list]
        assert any("CREATE SCHEMA IF NOT EXISTS shared" in s for s in executed_sqls)
        assert any("p_foo" in s for s in executed_sqls)
        assert any("shared.projects" in s for s in executed_sqls)

        conn.commit.assert_called_once()
        conn.close.assert_called_once()

    def test_db_schema_naming_rule(self, db_path):
        """I-DB-SCHEMA-1: schema MUST be p_{name}."""
        conn, _ = _make_mock_conn()
        with patch("sdd.commands.init_project.open_db_connection", return_value=conn):
            events = InitProjectHandler(db_path).handle(_cmd("myproject"))
        assert events[0].db_schema == "p_myproject"

    def test_empty_name_raises(self, db_path):
        """I-DB-SCHEMA-1: empty name must be rejected before any DB call."""
        conn, _ = _make_mock_conn()
        with patch("sdd.commands.init_project.open_db_connection", return_value=conn):
            with pytest.raises(Exception):
                InitProjectHandler(db_path).handle(_cmd(""))
        conn.cursor.assert_not_called()

    def test_invalid_name_raises(self, db_path):
        """I-DB-SCHEMA-1: names with special chars are rejected (SQL injection guard)."""
        conn, _ = _make_mock_conn()
        with patch("sdd.commands.init_project.open_db_connection", return_value=conn):
            with pytest.raises(Exception, match="I-DB-SCHEMA-1"):
                InitProjectHandler(db_path).handle(_cmd("bad name!"))
        conn.cursor.assert_not_called()

    def test_connection_closed_on_db_error(self, db_path):
        """Connection MUST be closed even if SQL execution fails."""
        conn, cursor = _make_mock_conn()
        cursor.execute.side_effect = RuntimeError("db error")

        with patch("sdd.commands.init_project.open_db_connection", return_value=conn):
            with pytest.raises(Exception):
                InitProjectHandler(db_path).handle(_cmd("foo"))

        conn.close.assert_called_once()

    def test_registry_entry_exists(self):
        """init-project MUST be registered in REGISTRY (I-REGISTRY-COMPLETE-1)."""
        from sdd.commands.registry import REGISTRY
        assert "init-project" in REGISTRY
        spec = REGISTRY["init-project"]
        assert spec.actor == "human"
        assert spec.requires_active_phase is False
        assert spec.action == "init_project"
