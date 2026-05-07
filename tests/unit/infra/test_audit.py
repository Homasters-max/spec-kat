from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from sdd.infra.audit import atomic_write, log_action, make_entry_id


def test_atomic_write_no_partial(tmp_path: object) -> None:
    """Simulate crash between write and replace — target must not exist (I-PK-5)."""
    import pathlib

    target = str(pathlib.Path(str(tmp_path)) / "output.txt")
    assert not os.path.exists(target)

    with patch("sdd.infra.audit.os.replace", side_effect=OSError("simulated crash")):
        with pytest.raises(OSError, match="simulated crash"):
            atomic_write(target, "some content")

    # Target must never have been created
    assert not os.path.exists(target)


def test_log_action_deterministic_id(tmp_path: object) -> None:
    """Same inputs → same entry_id (I-PK-5 determinism)."""
    import pathlib

    log_path = str(pathlib.Path(str(tmp_path)) / "audit.jsonl")

    id1 = make_entry_id("deploy", "llm", {"phase": 1})
    id2 = make_entry_id("deploy", "llm", {"phase": 1})
    assert id1 == id2

    entry1 = log_action("deploy", "llm", {"phase": 1}, audit_log_path=log_path)
    entry2 = log_action("deploy", "llm", {"phase": 1}, audit_log_path=log_path)
    assert entry1.entry_id == entry2.entry_id
