"""I-VR-STABLE-2: event log is append-only, ordered, causally consistent (P-6)."""
from __future__ import annotations

from hypothesis import HealthCheck, given, settings

from sdd.infra.db import open_sdd_connection
from tests.harness.fixtures import db_factory  # noqa: F401 — pytest fixture
from tests.harness.generators import valid_command_sequence
from tests.property import execute_sequence, wrap


def _read_seqs_and_ids(db_path: str) -> tuple[list[int], list[str]]:
    conn = open_sdd_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT sequence_id, event_id FROM event_log ORDER BY sequence_id ASC"
        ).fetchall()
    finally:
        conn.close()
    return [r[0] for r in rows], [str(r[1]) for r in rows]


@given(cmds=valid_command_sequence())
@settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_event_log_seq_monotonic(db_factory, cmds):
    """Seq numbers are strictly monotonically increasing after each append."""
    db = db_factory()
    execute_sequence(wrap(cmds), db)
    seqs, _ = _read_seqs_and_ids(db)
    for i in range(1, len(seqs)):
        assert seqs[i] > seqs[i - 1], f"seq not monotonic at index {i}: {seqs}"


@given(cmds=valid_command_sequence())
@settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_event_ids_unique(db_factory, cmds):
    """All event_ids in the log are unique."""
    db = db_factory()
    execute_sequence(wrap(cmds), db)
    _, ids = _read_seqs_and_ids(db)
    assert len(ids) == len(set(ids)), f"Duplicate event_ids: {ids}"


@given(cmds=valid_command_sequence(max_cmds=8))
@settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_event_log_append_only(db_factory, cmds):
    """Prior events are not modified after new appends (append-only invariant)."""
    wrapped = wrap(cmds)
    split = len(wrapped) // 2
    if split == 0:
        return
    first_half = wrapped[:split]
    second_half = wrapped[split:]
    db = db_factory()
    execute_sequence(first_half, db)
    seqs_before, ids_before = _read_seqs_and_ids(db)
    execute_sequence(second_half, db)
    seqs_after, ids_after = _read_seqs_and_ids(db)
    assert seqs_after[: len(seqs_before)] == seqs_before
    assert ids_after[: len(ids_before)] == ids_before
