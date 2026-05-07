"""I-VR-STABLE-1/2/3: every prefix of a valid command sequence yields a consistent state."""
from __future__ import annotations

from hypothesis import HealthCheck, given, settings

from tests.harness.api import rollback
from tests.harness.fixtures import db_factory  # noqa: F401 — pytest fixture
from tests.harness.generators import valid_command_sequence
from tests.property import execute_sequence, wrap


@given(cmds=valid_command_sequence(max_cmds=6))
@settings(max_examples=8, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_every_prefix_yields_valid_state(db_factory, cmds):
    wrapped = wrap(cmds)
    for t in range(len(wrapped) + 1):
        prefix = rollback(wrapped, t)
        _, state = execute_sequence(prefix, db_factory())
        assert state is not None


@given(cmds=valid_command_sequence(max_cmds=3))
@settings(max_examples=6, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_prefix_state_is_deterministic(db_factory, cmds):
    """Same prefix in two isolated DBs → same state."""
    wrapped = wrap(cmds)
    for t in range(len(wrapped) + 1):
        prefix = rollback(wrapped, t)
        _, s1 = execute_sequence(prefix, db_factory())
        _, s2 = execute_sequence(prefix, db_factory())
        assert s1 == s2
