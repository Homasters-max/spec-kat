"""I-VR-STABLE-1/2/3: every prefix of a valid command sequence yields a consistent state."""
from __future__ import annotations

import os
import tempfile

from hypothesis import given, settings

from tests.harness.api import rollback
from tests.harness.generators import valid_command_sequence
from tests.property import execute_sequence, wrap


@given(cmds=valid_command_sequence(max_cmds=8))
@settings(max_examples=15, deadline=None)
def test_every_prefix_yields_valid_state(cmds):
    wrapped = wrap(cmds)
    for t in range(len(wrapped) + 1):
        prefix = rollback(wrapped, t)
        with tempfile.TemporaryDirectory() as d:
            _, state = execute_sequence(prefix, os.path.join(d, "db.duckdb"))
            assert state is not None


@given(cmds=valid_command_sequence(max_cmds=4))
@settings(max_examples=20, deadline=None)
def test_prefix_state_is_deterministic(cmds):
    """Same prefix in two isolated DBs → same state."""
    wrapped = wrap(cmds)
    for t in range(len(wrapped) + 1):
        prefix = rollback(wrapped, t)
        with tempfile.TemporaryDirectory() as d:
            _, s1 = execute_sequence(prefix, os.path.join(d, "db1.duckdb"))
            _, s2 = execute_sequence(prefix, os.path.join(d, "db2.duckdb"))
            assert s1 == s2
