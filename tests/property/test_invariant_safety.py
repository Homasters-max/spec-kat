"""I-VR-STABLE-1/2/3: all generated command sequences produce a safe, non-None state."""
from __future__ import annotations

import os
import tempfile

from hypothesis import given, settings

from tests.harness.generators import adversarial_sequence, valid_command_sequence
from tests.property import execute_sequence, wrap


@given(cmds=valid_command_sequence())
@settings(max_examples=30, deadline=None)
def test_valid_sequence_safe_state(cmds):
    with tempfile.TemporaryDirectory() as d:
        events, state = execute_sequence(wrap(cmds), os.path.join(d, "db.duckdb"))
        assert state is not None
        assert isinstance(events, list)


@given(cmds=adversarial_sequence())
@settings(max_examples=25, deadline=None)
def test_adversarial_sequence_safe_state(cmds):
    with tempfile.TemporaryDirectory() as d:
        events, state = execute_sequence(wrap(cmds), os.path.join(d, "db.duckdb"))
        assert state is not None
        assert isinstance(events, list)
