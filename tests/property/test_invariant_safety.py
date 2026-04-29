"""I-VR-STABLE-1/2/3: all generated command sequences produce a safe, non-None state."""
from __future__ import annotations

from hypothesis import HealthCheck, given, settings

from tests.harness.fixtures import db_factory  # noqa: F401 — pytest fixture
from tests.harness.generators import adversarial_sequence, valid_command_sequence
from tests.property import execute_sequence, wrap


@given(cmds=valid_command_sequence())
@settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_valid_sequence_safe_state(db_factory, cmds):
    events, state = execute_sequence(wrap(cmds), db_factory())
    assert state is not None
    assert isinstance(events, list)


@given(cmds=adversarial_sequence())
@settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_adversarial_sequence_safe_state(db_factory, cmds):
    events, state = execute_sequence(wrap(cmds), db_factory())
    assert state is not None
    assert isinstance(events, list)
