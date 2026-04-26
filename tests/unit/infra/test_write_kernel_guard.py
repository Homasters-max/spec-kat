"""Write Kernel Guard — EventStore.append() and sdd_append() enforcement tests.

Invariants: I-DB-WRITE-2, I-DB-WRITE-3, I-KERNEL-WRITE-1, I-SPEC-EXEC-1
Spec ref: Spec_v28 §2 BC-WG-3, BC-WG-4, §5 Invariants
"""
from __future__ import annotations

from pathlib import Path

import pytest

from sdd.core.execution_context import KernelContextError, kernel_context
from sdd.infra.event_log import sdd_append
from sdd.infra.event_store import EventStore
from sdd.infra.paths import event_store_file
from tests.harness.fixtures import make_minimal_event


def _prod_store() -> EventStore:
    """Return an EventStore pointing at the test-isolated 'production' DB path."""
    return EventStore(str(event_store_file()))


def test_write_kernel_guard_raise_outside_context() -> None:
    """EventStore.append on production DB outside execute_command raises KernelContextError."""
    store = _prod_store()
    with pytest.raises(KernelContextError, match="EventStore.append"):
        store.append([make_minimal_event()], source="test")


def test_write_kernel_guard_allow_inside_context() -> None:
    """EventStore.append on production DB inside kernel_context('execute_command') succeeds.

    Empty event list is intentional: guard is checked before the empty-list short-circuit,
    so the guard logic is exercised without triggering a real DB write (I-DB-TEST-1).
    """
    store = _prod_store()
    with kernel_context("execute_command"):
        store.append([], source="test")  # guard passes; empty → no DB write


def test_write_kernel_guard_bootstrap_bypass() -> None:
    """allow_outside_kernel='bootstrap' bypasses kernel guard on production DB.

    Empty event list: guard bypass is verified before the short-circuit (I-DB-TEST-1).
    """
    store = _prod_store()
    store.append([], source="test", allow_outside_kernel="bootstrap")  # must not raise


def test_write_kernel_guard_invalid_bypass_value() -> None:
    """allow_outside_kernel with unrecognized value raises ValueError."""
    store = _prod_store()
    with pytest.raises(ValueError, match="Invalid allow_outside_kernel"):
        store.append([make_minimal_event()], source="test", allow_outside_kernel="invalid")  # type: ignore[arg-type]


def test_sdd_append_prod_guard_raise_outside_kernel() -> None:
    """sdd_append targeting production DB path raises KernelContextError outside execute_command."""
    prod_path = str(event_store_file())
    with pytest.raises(KernelContextError, match="sdd_append"):
        sdd_append("TaskImplemented", {"task_id": "T-001", "phase_id": 1}, db_path=prod_path)


def test_sdd_append_nonprod_allowed_outside_kernel(tmp_path: Path) -> None:
    """sdd_append targeting a non-production DB path does not raise KernelContextError."""
    db = str(tmp_path / "test.duckdb")
    sdd_append("TaskImplemented", {"task_id": "T-001", "phase_id": 1}, db_path=db)
