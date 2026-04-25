"""I-STATE-DETERMINISTIC-1: identical input sequence → identical state in any isolated DB."""
from __future__ import annotations

import os
import tempfile

from hypothesis import given, settings

from tests.harness.generators import adversarial_sequence, valid_command_sequence
from tests.property import execute_sequence, wrap


@given(cmds=valid_command_sequence())
@settings(max_examples=25, deadline=None)
def test_determinism_valid_sequence(cmds):
    cmds = wrap(cmds)
    with tempfile.TemporaryDirectory() as d:
        _, s1 = execute_sequence(cmds, os.path.join(d, "db1.duckdb"))
        _, s2 = execute_sequence(cmds, os.path.join(d, "db2.duckdb"))
        assert s1 == s2


@given(cmds=adversarial_sequence())
@settings(max_examples=20, deadline=None)
def test_determinism_adversarial_sequence(cmds):
    cmds = wrap(cmds)
    with tempfile.TemporaryDirectory() as d:
        _, s1 = execute_sequence(cmds, os.path.join(d, "db1.duckdb"))
        _, s2 = execute_sequence(cmds, os.path.join(d, "db2.duckdb"))
        assert s1 == s2
