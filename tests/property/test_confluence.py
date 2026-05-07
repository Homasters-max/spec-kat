"""I-CONFLUENCE-STRONG-1: independent commands commute — order does not affect final state."""
from __future__ import annotations

from hypothesis import HealthCheck, given, settings

from tests.harness.fixtures import db_factory  # noqa: F401 — pytest fixture
from tests.harness.generators import adversarial_sequence, valid_command_sequence
from tests.property import execute_sequence, wrap


@given(cmds=valid_command_sequence(max_cmds=6))
@settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_reversed_order_same_state(db_factory, cmds):
    fwd = wrap(cmds)
    rev = wrap(list(reversed(cmds)))
    _, s_fwd = execute_sequence(fwd, db_factory())
    _, s_rev = execute_sequence(rev, db_factory())
    assert s_fwd == s_rev


@given(cmds=adversarial_sequence())
@settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_confluence_adversarial_reversed(db_factory, cmds):
    fwd = wrap(cmds)
    rev = wrap(list(reversed(cmds)))
    _, s_fwd = execute_sequence(fwd, db_factory())
    _, s_rev = execute_sequence(rev, db_factory())
    assert s_fwd == s_rev
