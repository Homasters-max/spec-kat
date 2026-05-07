"""Tests for register_l1_event_type, _check_c1_consistency, SDD_C1_MODE — T-707.

Covers: I-REG-1, I-REG-STATIC-1, I-C1-MODE-1
"""

from __future__ import annotations

import importlib
import inspect
import os
from collections.abc import Callable
from typing import Any
from unittest.mock import patch

import pytest

import sdd.core.events as ev


@pytest.fixture(autouse=True)
def _restore_events_module():
    """Restore events module global state after each test."""
    orig_v1 = ev.V1_L1_EVENT_TYPES
    orig_v2 = ev.V2_L1_EVENT_TYPES
    orig_no_handler = ev._KNOWN_NO_HANDLER
    orig_schema = dict(ev._EVENT_SCHEMA)
    yield
    ev.V1_L1_EVENT_TYPES = orig_v1
    ev.V2_L1_EVENT_TYPES = orig_v2
    ev._KNOWN_NO_HANDLER = orig_no_handler
    ev._EVENT_SCHEMA.clear()
    ev._EVENT_SCHEMA.update(orig_schema)


def test_register_with_handler():
    handler: Callable[..., Any] = lambda e: None  # noqa: E731
    ev.register_l1_event_type("TestWithHandler_707a", handler=handler)
    assert "TestWithHandler_707a" in ev.V1_L1_EVENT_TYPES
    assert "TestWithHandler_707a" in ev._EVENT_SCHEMA
    assert "TestWithHandler_707a" not in ev._KNOWN_NO_HANDLER


def test_register_without_handler():
    ev.register_l1_event_type("TestNoHandler_707b")
    assert "TestNoHandler_707b" in ev.V1_L1_EVENT_TYPES
    assert "TestNoHandler_707b" not in ev._EVENT_SCHEMA
    assert "TestNoHandler_707b" in ev._KNOWN_NO_HANDLER


def test_register_duplicate_raises():
    ev.register_l1_event_type("TestDuplicate_707c")
    with pytest.raises(ValueError, match="Duplicate registration"):
        ev.register_l1_event_type("TestDuplicate_707c")


def test_c1_consistent_after_registration():
    ev.register_l1_event_type("TestC1After_707d")
    with patch.dict(os.environ, {"SDD_C1_MODE": "strict"}):
        ev._check_c1_consistency()  # valid registration → must not raise


def test_c1_strict_mode_raises():
    # Inject phantom type into V1 without updating registries → C-1 violated
    ev.V1_L1_EVENT_TYPES = ev.V1_L1_EVENT_TYPES | frozenset({"__phantom_707e__"})
    with patch.dict(os.environ, {"SDD_C1_MODE": "strict"}):
        with pytest.raises(AssertionError):
            ev._check_c1_consistency()


def test_c1_warn_mode_does_not_raise():
    ev.V1_L1_EVENT_TYPES = ev.V1_L1_EVENT_TYPES | frozenset({"__phantom_707f__"})
    with patch.dict(os.environ, {"SDD_C1_MODE": "warn"}):
        ev._check_c1_consistency()  # must not raise in warn mode


def test_existing_c1_assert_replaced():
    # I-C1-MODE-1: no bare assert; module-level _check_c1_consistency() call present
    source = inspect.getsource(ev)
    assert "assert _KNOWN_NO_HANDLER" not in source
    assert "_check_c1_consistency()" in source


def test_module_import_does_not_raise_in_warn_mode():
    with patch.dict(os.environ, {"SDD_C1_MODE": "warn"}):
        importlib.reload(ev)  # module-level _check_c1_consistency() must not raise


def test_register_only_at_import_time_convention():
    # I-REG-STATIC-1: docstring must document import-time-only constraint
    doc = ev.register_l1_event_type.__doc__ or ""
    assert "import" in doc.lower(), (
        "register_l1_event_type must document the import-time-only convention (I-REG-STATIC-1)"
    )
