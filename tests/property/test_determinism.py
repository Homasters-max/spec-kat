"""I-STATE-DETERMINISTIC-1: identical input sequence → identical state in any isolated DB."""
from __future__ import annotations

from hypothesis import HealthCheck, given, settings

from tests.harness.fixtures import db_factory  # noqa: F401 — pytest fixture
from tests.harness.generators import adversarial_sequence, valid_command_sequence
from tests.property import execute_sequence, wrap


@given(cmds=valid_command_sequence())
@settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_determinism_valid_sequence(db_factory, cmds):
    cmds = wrap(cmds)
    _, s1 = execute_sequence(cmds, db_factory())
    _, s2 = execute_sequence(cmds, db_factory())
    assert s1 == s2


@given(cmds=adversarial_sequence())
@settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_determinism_adversarial_sequence(db_factory, cmds):
    cmds = wrap(cmds)
    _, s1 = execute_sequence(cmds, db_factory())
    _, s2 = execute_sequence(cmds, db_factory())
    assert s1 == s2
