"""Unit tests for PG EventLog protocol, routing, production guard, projector NO-OP,
and lazy DuckDB import.

Invariants: I-ELK-PROTO-1, I-EVENT-STORE-URL-1, I-PROD-GUARD-1,
            I-PROJ-NOOP-1, I-PROJ-SAFE-1, I-FAIL-1, I-LAZY-DUCK-1
"""
from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, patch

import pytest

from sdd.core.events import TaskImplementedEvent
from sdd.infra.event_log import EventLogKernelProtocol


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_task_event() -> TaskImplementedEvent:
    return TaskImplementedEvent(
        event_type="TaskImplemented",
        event_id="proto-test-id",
        appended_at=0,
        level="L1",
        event_source="runtime",
        caused_by_meta_seq=None,
        task_id="T-001",
        phase_id=43,
        timestamp="2026-01-01T00:00:00Z",
    )


class FakeEventLog:
    """In-memory EventLog stub satisfying EventLogKernelProtocol (I-ELK-PROTO-1)."""

    def __init__(self) -> None:
        self.captured: list = []
        self._seq: int = 0

    def max_seq(self) -> int | None:
        return self._seq if self._seq > 0 else None

    def append(
        self,
        events: list,
        source: str,
        command_id: str | None = None,
        expected_head: int | None = None,
        allow_outside_kernel: str | None = None,
        batch_id: str | None = None,
    ) -> None:
        self.captured.extend(events)
        self._seq += len(events)


# ---------------------------------------------------------------------------
# Tests 1–2: FakeEventLog injection (I-ELK-PROTO-1)
# ---------------------------------------------------------------------------

def test_fake_event_log_satisfies_protocol() -> None:
    """FakeEventLog satisfies EventLogKernelProtocol structurally (I-ELK-PROTO-1)."""
    fake = FakeEventLog()
    assert isinstance(fake, EventLogKernelProtocol)

    assert fake.max_seq() is None
    fake.append([_make_task_event()], source="test")
    assert fake.max_seq() == 1
    assert fake.captured[0].task_id == "T-001"


def test_postgres_event_log_satisfies_protocol() -> None:
    """PostgresEventLog satisfies EventLogKernelProtocol without real DB (I-ELK-PROTO-1)."""
    from sdd.infra.event_log import PostgresEventLog

    with patch("sdd.infra.event_log.open_sdd_connection", return_value=MagicMock()):
        el = PostgresEventLog("postgresql://fake/test")

    assert isinstance(el, EventLogKernelProtocol)


# ---------------------------------------------------------------------------
# Tests 3–4: event_store_url routing (I-EVENT-STORE-URL-1)
# ---------------------------------------------------------------------------

def test_event_store_url_returns_pg_url_when_env_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """event_store_url() returns SDD_DATABASE_URL when set (I-EVENT-STORE-URL-1)."""
    from sdd.infra.paths import event_store_url

    monkeypatch.setenv("SDD_DATABASE_URL", "postgresql://host/sdd_prod")
    assert event_store_url() == "postgresql://host/sdd_prod"


def test_event_store_url_raises_when_sdd_database_url_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    """event_store_url() raises EnvironmentError when SDD_DATABASE_URL not set (I-NO-DUCKDB-1)."""
    from sdd.infra.paths import event_store_url

    monkeypatch.delenv("SDD_DATABASE_URL", raising=False)
    with pytest.raises(EnvironmentError, match="SDD_DATABASE_URL"):
        event_store_url()


# ---------------------------------------------------------------------------
# Tests 5–6: is_production_event_store (I-PROD-GUARD-1)
# ---------------------------------------------------------------------------

def test_is_production_event_store_true_for_matching_pg_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """is_production_event_store() returns True when db_path == SDD_DATABASE_URL (I-PROD-GUARD-1)."""
    from sdd.infra.paths import is_production_event_store

    pg_url = "postgresql://host/sdd_prod"
    monkeypatch.setenv("SDD_DATABASE_URL", pg_url)
    assert is_production_event_store(pg_url) is True


def test_is_production_event_store_false_for_different_pg_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """is_production_event_store() returns False for a different URL (I-PROD-GUARD-1)."""
    from sdd.infra.paths import is_production_event_store

    monkeypatch.setenv("SDD_DATABASE_URL", "postgresql://host/sdd_prod")
    assert is_production_event_store("postgresql://host/other_db") is False


# ---------------------------------------------------------------------------
# Test 7: Projector NOOP (I-PROJ-NOOP-1)
# ---------------------------------------------------------------------------

def test_projector_apply_noop_for_unknown_event_type() -> None:
    """Projector.apply() with unknown event_type must not raise or touch DB (I-PROJ-NOOP-1)."""
    from sdd.infra.projector import Projector

    mock_conn = MagicMock()

    with patch("sdd.infra.projector.open_db_connection", return_value=mock_conn):
        projector = Projector("postgresql://fake/test")
        mock_conn.reset_mock()

        unknown_event = types.SimpleNamespace(event_type="TotallyUnknownEventType")
        projector.apply(unknown_event)  # must not raise

    mock_conn.cursor.assert_not_called()


# ---------------------------------------------------------------------------
# Test 8: _apply_projector_safe swallows (I-PROJ-SAFE-1, I-FAIL-1)
# ---------------------------------------------------------------------------

def test_apply_projector_safe_swallows_exception() -> None:
    """_apply_projector_safe must not raise for None projector or a failing apply() (I-PROJ-SAFE-1, I-FAIL-1)."""
    from sdd.commands.registry import _apply_projector_safe

    event = _make_task_event()

    # None projector: must be a no-op
    _apply_projector_safe(None, [event])

    class BrokenProjector:
        def apply(self, ev: object) -> None:
            raise RuntimeError("simulated DB failure")

    # Broken projector: must swallow the exception
    _apply_projector_safe(BrokenProjector(), [event])


# ---------------------------------------------------------------------------
# Test 9: lazy duckdb import (I-LAZY-DUCK-1)
# ---------------------------------------------------------------------------

def test_open_sdd_connection_rejects_non_pg_url() -> None:
    """open_sdd_connection() must reject non-PostgreSQL URLs (I-NO-DUCKDB-1)."""
    from sdd.infra.db import open_sdd_connection

    with pytest.raises(ValueError, match="I-NO-DUCKDB-1"):
        open_sdd_connection("/tmp/test.duckdb")


# ---------------------------------------------------------------------------
# Test 10: JSONB dict guard (R-3)
# ---------------------------------------------------------------------------

def test_postgres_event_log_replay_jsonb_dict_payload() -> None:
    """R-3: psycopg3 returns JSONB as dict; replay() must not json.loads it again."""
    from sdd.infra.event_log import PostgresEventLog

    payload_dict = {"task_id": "T-001", "phase_id": 43}
    mock_conn = MagicMock()
    mock_conn.execute.return_value.fetchall.return_value = [
        # (sequence_id, event_id, event_type, payload, level, event_source, caused_by_meta_seq, expired, created_at)
        (1, "uuid-1", "TaskImplemented", payload_dict, "L1", "runtime", None, False, "2026-01-01"),
    ]

    with patch("sdd.infra.event_log.open_sdd_connection", return_value=mock_conn):
        el = PostgresEventLog("postgresql://fake/test")
        rows = el.replay()

    assert len(rows) == 1
    # same object returned — dict guard bypassed json.loads (R-3)
    assert rows[0]["payload"] is payload_dict
    assert isinstance(rows[0]["payload"], dict)
