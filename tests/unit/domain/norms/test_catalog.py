"""Tests for NormCatalog, NormEntry, load_catalog — Spec_v3 §5 I-NRM-1..3."""

from __future__ import annotations

import dataclasses
import os
import tempfile

import pytest

from sdd.core.errors import MissingContext
from sdd.domain.norms import NormCatalog, NormEntry, load_catalog

# Path to the real norm catalog used in production
_CATALOG_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "..", ".sdd", "norms", "norm_catalog.yaml"
)


def _real_catalog_path() -> str:
    return os.path.normpath(_CATALOG_PATH)


# ---------------------------------------------------------------------------
# I-NRM-1: deterministic load
# ---------------------------------------------------------------------------

def test_load_catalog_deterministic():
    path = _real_catalog_path()
    c1 = load_catalog(path)
    c2 = load_catalog(path)
    assert c1 == c2
    assert c1.entries == c2.entries


# ---------------------------------------------------------------------------
# I-NRM-1: missing file raises MissingContext
# ---------------------------------------------------------------------------

def test_load_catalog_missing_raises():
    with pytest.raises(MissingContext):
        load_catalog("/nonexistent/path/norm_catalog.yaml")


# ---------------------------------------------------------------------------
# I-NRM-2: known permitted action (explicit allow entry)
# ---------------------------------------------------------------------------

def test_is_allowed_known_permitted():
    # NORM-ACTOR-004: llm MAY emit TaskImplemented
    catalog = load_catalog(_real_catalog_path())
    assert catalog.is_allowed("llm", "TaskImplemented") is True


# ---------------------------------------------------------------------------
# I-NRM-2: known forbidden action
# ---------------------------------------------------------------------------

def test_is_allowed_known_forbidden():
    # NORM-ACTOR-001: llm MUST NOT emit SpecApproved
    catalog = load_catalog(_real_catalog_path())
    assert catalog.is_allowed("llm", "SpecApproved") is False


# ---------------------------------------------------------------------------
# I-NRM-2: unknown action non-strict → allow (open-by-default)
# ---------------------------------------------------------------------------

def test_is_allowed_unknown_action_non_strict():
    catalog = NormCatalog(entries=(), strict=False)
    assert catalog.is_allowed("llm", "completely_unknown_action") is True


# ---------------------------------------------------------------------------
# I-NRM-3: unknown action strict → deny (closed-by-default)
# ---------------------------------------------------------------------------

def test_is_allowed_unknown_action_strict():
    catalog = NormCatalog(entries=(), strict=True)
    assert catalog.is_allowed("llm", "completely_unknown_action") is False


# ---------------------------------------------------------------------------
# get_norm by norm_id
# ---------------------------------------------------------------------------

def test_get_norm_by_id():
    catalog = load_catalog(_real_catalog_path())
    entry = catalog.get_norm("NORM-ACTOR-001")
    assert entry is not None
    assert entry.norm_id == "NORM-ACTOR-001"
    assert entry.actor == "llm"
    assert entry.result == "forbidden"
    assert entry.action == "SpecApproved"
    assert catalog.get_norm("NORM-DOES-NOT-EXIST") is None


# ---------------------------------------------------------------------------
# "any" actor applies to all actors
# ---------------------------------------------------------------------------

def test_any_actor_applies_to_all():
    entry = NormEntry(
        norm_id="TEST-ANY-001",
        actor="any",
        action="forbidden_for_all",
        result="forbidden",
        description="Test any-actor norm",
        severity="hard",
    )
    catalog = NormCatalog(entries=(entry,), strict=False)
    assert catalog.is_allowed("llm", "forbidden_for_all") is False
    assert catalog.is_allowed("human", "forbidden_for_all") is False
    assert catalog.is_allowed("any", "forbidden_for_all") is False


# ---------------------------------------------------------------------------
# I-NRM-3: strict flag is immutable after construction (frozen dataclass)
# ---------------------------------------------------------------------------

def test_strict_flag_immutable():
    catalog = NormCatalog(entries=(), strict=False)
    with pytest.raises((dataclasses.FrozenInstanceError, AttributeError, TypeError)):
        catalog.strict = True  # type: ignore[misc]
