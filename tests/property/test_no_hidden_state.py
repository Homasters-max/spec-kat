"""I-VR-STABLE-3: get_current_state is idempotent — no hidden mutable state between calls."""
from __future__ import annotations

import os
import tempfile

from hypothesis import given, settings

from tests.harness.api import replay
from tests.harness.generators import valid_command_sequence
from tests.property import execute_sequence, wrap


@given(cmds=valid_command_sequence())
@settings(max_examples=25, deadline=None)
def test_replay_matches_execute_state(cmds):
    """State from execute_sequence equals state from a subsequent replay on the same DB."""
    with tempfile.TemporaryDirectory() as d:
        db = os.path.join(d, "db.duckdb")
        events, state1 = execute_sequence(wrap(cmds), db)
        state2 = replay(events, db)
        assert state1 == state2


@given(cmds=valid_command_sequence())
@settings(max_examples=20, deadline=None)
def test_replay_is_idempotent(cmds):
    """Calling replay twice on the same DB returns the same state."""
    with tempfile.TemporaryDirectory() as d:
        db = os.path.join(d, "db.duckdb")
        events, _ = execute_sequence(wrap(cmds), db)
        s1 = replay(events, db)
        s2 = replay(events, db)
        assert s1 == s2
