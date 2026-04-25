"""I-CONFLUENCE-STRONG-1: independent commands commute — order does not affect final state."""
from __future__ import annotations

import os
import tempfile

from hypothesis import given, settings

from tests.harness.generators import adversarial_sequence, valid_command_sequence
from tests.property import execute_sequence, wrap


@given(cmds=valid_command_sequence(max_cmds=6))
@settings(max_examples=25, deadline=None)
def test_reversed_order_same_state(cmds):
    fwd = wrap(cmds)
    rev = wrap(list(reversed(cmds)))
    with tempfile.TemporaryDirectory() as d:
        _, s_fwd = execute_sequence(fwd, os.path.join(d, "fwd.duckdb"))
        _, s_rev = execute_sequence(rev, os.path.join(d, "rev.duckdb"))
        assert s_fwd == s_rev


@given(cmds=adversarial_sequence())
@settings(max_examples=20, deadline=None)
def test_confluence_adversarial_reversed(cmds):
    fwd = wrap(cmds)
    rev = wrap(list(reversed(cmds)))
    with tempfile.TemporaryDirectory() as d:
        _, s_fwd = execute_sequence(fwd, os.path.join(d, "fwd.duckdb"))
        _, s_rev = execute_sequence(rev, os.path.join(d, "rev.duckdb"))
        assert s_fwd == s_rev
