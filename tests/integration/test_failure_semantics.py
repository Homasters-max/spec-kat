"""Integration tests: failure semantics determinism — I-FAIL-DETERMINISTIC-1.

Same inputs must produce identical error_type + message across repeated calls.
Three scenarios: invalid guard rejection, optimistic-lock conflict, unknown-event replay.
"""
from __future__ import annotations

import pytest

from sdd.commands.registry import REGISTRY
from sdd.core.errors import GuardViolationError, SDDError, StaleStateError
from sdd.core.types import Command
from sdd.domain.state.reducer import reduce
from sdd.infra.event_log import sdd_append, sdd_replay
from sdd.infra.event_log import EventLog

# Import harness fixtures so pytest auto-discovers them (I-VR-HARNESS-4).
from tests.harness.api import execute_sequence
from tests.harness.fixtures import db_factory, event_factory  # noqa: F401


# ---------------------------------------------------------------------------
# Test 1: invalid command ×2 → identical error_type + message
# ---------------------------------------------------------------------------


def test_invalid_command_deterministic_error(db_factory) -> None:  # type: ignore[no-redef]
    """test 1: invalid command called twice → identical error_type + message (I-FAIL-DETERMINISTIC-1).

    Calls check-dod on an empty DB (no active phase) twice.  check-dod uses
    uses_task_id=False so no TaskSet file is loaded — the phase guard runs first
    and must deny with the same GuardViolationError message on both runs even
    though the first call appends audit events to the log.
    """
    db = db_factory()

    # check-dod: uses_task_id=False → no TaskSet loading; requires_active_phase=True → phase guard runs.
    cmd = Command(
        command_id="test-cmd-det-001",
        command_type="check-dod",
        payload={},
    )
    spec = REGISTRY["check-dod"]

    errors: list[tuple[str, str]] = []
    for _ in range(2):
        try:
            execute_sequence([(spec, cmd)], db_path=db)
        except SDDError as exc:
            errors.append((type(exc).__name__, str(exc)))

    assert len(errors) == 2, "Both calls must fail with an SDDError subclass"
    assert errors[0][0] == errors[1][0], "error_type must be identical on both runs"
    assert errors[0][1] == errors[1][1], "error message must be identical on both runs"


# ---------------------------------------------------------------------------
# Test 2: StaleStateError ×2 → reproducible same seq + same error
# ---------------------------------------------------------------------------


def test_stale_state_error_deterministic(db_factory, event_factory) -> None:  # type: ignore[no-redef]
    """test 2: StaleStateError raised twice encodes identical expected + current seq (I-FAIL-DETERMINISTIC-1).

    Seeds one event via sdd_append to establish a known head seq, then calls
    EventLog.append twice with a deliberately wrong expected_head.  Both calls
    must raise StaleStateError with an identical message that includes both the
    expected and the actual current seq values.

    StaleStateError is raised inside the transaction BEFORE any INSERT, so the
    event_source of the passed events does not matter for this path.
    """
    db = db_factory()

    # Establish a known head by seeding one event via sdd_append (valid event_source).
    sdd_append("_seed_T1716", {}, db_path=db, level="L2", event_source="runtime")
    head = EventLog(db).max_seq()
    assert head is not None, "head seq must be set after seeding"

    wrong_head = 999
    store = EventLog(db)
    errors: list[tuple[str, str]] = []
    for i in range(2):
        try:
            store.append(
                [event_factory(event_source="runtime")],
                source="runtime",
                expected_head=wrong_head,
                command_id=f"stale-det-{i}",
            )
        except StaleStateError as exc:
            errors.append((type(exc).__name__, str(exc)))

    assert len(errors) == 2, "Both calls must fail with StaleStateError"
    assert errors[0][0] == errors[1][0], "StaleStateError type must be identical"
    assert errors[0][1] == errors[1][1], (
        "StaleStateError message must be identical: same expected + same current seq"
    )
    assert str(wrong_head) in errors[0][1], "Message must encode the expected seq"
    assert str(head) in errors[0][1], "Message must encode the actual current seq"


# ---------------------------------------------------------------------------
# Test 3: corrupted log → replay → concrete SDDError (not generic Exception)
# ---------------------------------------------------------------------------


def test_corrupted_log_replay_raises_sdd_error(db_factory) -> None:  # type: ignore[no-redef]
    """test 3: corrupted log → replay → concrete SDDError subclass (I-FAIL-DETERMINISTIC-1).

    Seeds the event log with an L1/runtime event of an unrecognized event_type
    (simulating a non-conformant / corrupted log entry).  Replaying and reducing
    in strict_mode must raise a concrete SDDError subclass — never a bare Exception.
    Both replay+reduce calls must produce identical errors.
    """
    db = db_factory()

    # Seed a "corrupted" L1 runtime event with an unrecognized event_type.
    # Explicit level="L1" ensures the event survives the replay filter and
    # reaches the reducer, which raises UnknownEventType(SDDError) in strict_mode.
    sdd_append(
        "_CorruptedUnknownEvent_T1716",
        {"data": "corrupt"},
        db_path=db,
        level="L1",
        event_source="runtime",
    )

    errors: list[tuple[str, str]] = []
    for _ in range(2):
        events = sdd_replay(db_path=db)
        try:
            reduce(events, strict_mode=True)
        except SDDError as exc:
            errors.append((type(exc).__name__, str(exc)))
        except Exception as exc:
            pytest.fail(
                f"Expected a concrete SDDError subclass, got {type(exc).__name__}: {exc}"
            )

    assert len(errors) == 2, "Both replay+reduce calls must fail"
    assert errors[0] == errors[1], (
        "Replay errors must be deterministic (I-FAIL-DETERMINISTIC-1)"
    )
    for name, _ in errors:
        assert name != "Exception", (
            f"Must be a concrete SDDError subclass, not bare Exception — got {name}"
        )
