"""I-EL-KERNEL-1 enforcement: el_kernel.py must not import psycopg (BC-47-A)."""
from __future__ import annotations

import ast
import importlib
from pathlib import Path


def test_el_kernel_no_psycopg_import() -> None:
    """I-EL-KERNEL-1: EventLogKernel must contain no psycopg imports at any depth."""
    src = Path(__file__).parents[3] / "src" / "sdd" / "infra" / "el_kernel.py"
    tree = ast.parse(src.read_text())
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            else:
                names = [node.module or ""]
            for name in names:
                assert "psycopg" not in (name or ""), (
                    f"I-EL-KERNEL-1 violated: el_kernel.py imports '{name}' — "
                    "psycopg must not be imported in the kernel layer"
                )


def test_el_kernel_importable_without_psycopg() -> None:
    """el_kernel module must be importable in isolation (no DB side-effects)."""
    from sdd.infra.el_kernel import EventLogKernel  # noqa: PLC0415

    kernel = EventLogKernel()
    assert hasattr(kernel, "resolve_batch_id")
    assert hasattr(kernel, "check_optimistic_lock")
    assert hasattr(kernel, "filter_duplicates")


# --- T-4705: unit-тесты методов EventLogKernel (5 тестов) ---

def test_el_kernel_resolve_batch_id_multi() -> None:
    """I-EL-BATCH-ID-1: 2+ events → UUID4 string."""
    import re
    from sdd.infra.el_kernel import EventLogKernel  # noqa: PLC0415

    kernel = EventLogKernel()
    result = kernel.resolve_batch_id(["e1", "e2"])
    assert isinstance(result, str)
    assert re.match(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
        result,
    ), f"Expected UUID4, got: {result!r}"


def test_el_kernel_resolve_batch_id_single() -> None:
    """I-EL-BATCH-ID-1: 1 event → None."""
    from sdd.infra.el_kernel import EventLogKernel  # noqa: PLC0415

    kernel = EventLogKernel()
    result = kernel.resolve_batch_id(["e1"])
    assert result is None


def test_el_kernel_check_optimistic_lock_pass() -> None:
    """I-OPTLOCK-1: current == expected → no exception."""
    from sdd.infra.el_kernel import EventLogKernel  # noqa: PLC0415

    kernel = EventLogKernel()
    kernel.check_optimistic_lock(current_max=5, expected_head=5)


def test_el_kernel_check_optimistic_lock_fail() -> None:
    """I-OPTLOCK-1: current ≠ expected → StaleStateError."""
    import pytest
    from sdd.core.errors import StaleStateError  # noqa: PLC0415
    from sdd.infra.el_kernel import EventLogKernel  # noqa: PLC0415

    kernel = EventLogKernel()
    with pytest.raises(StaleStateError):
        kernel.check_optimistic_lock(current_max=7, expected_head=5)


def test_el_kernel_filter_duplicates() -> None:
    """I-IDEM-SCHEMA-1: known pair skipped; new pair passed through."""
    from sdd.infra.el_kernel import EventLogKernel  # noqa: PLC0415

    kernel = EventLogKernel()
    existing = {("cmd-abc", 0), ("cmd-abc", 1)}
    events = [
        {"command_id": "cmd-abc", "event_index": 0},   # duplicate → skipped
        {"command_id": "cmd-abc", "event_index": 1},   # duplicate → skipped
        {"command_id": "cmd-xyz", "event_index": 0},   # new → to_insert
        {"command_id": None, "event_index": 0},        # no cmd_id → to_insert
    ]
    to_insert, skipped = kernel.filter_duplicates(events, existing)
    assert len(to_insert) == 2
    assert len(skipped) == 2
    assert to_insert[0]["command_id"] == "cmd-xyz"
    assert to_insert[1]["command_id"] is None
