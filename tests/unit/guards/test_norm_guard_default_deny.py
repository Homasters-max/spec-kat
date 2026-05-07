"""Tests for NormCatalog default=DENY policy — I-CMD-12."""

from __future__ import annotations

import pytest

from sdd.domain.norms.catalog import NormCatalog, NormEntry


def _make_entry(
    norm_id: str,
    actor: str,
    action: str,
    result: str,
    severity: str = "hard",
) -> NormEntry:
    return NormEntry(
        norm_id=norm_id,
        actor=actor,
        action=action,
        result=result,
        description="test norm",
        severity=severity,
    )


def test_norm_guard_default_deny_for_unlisted_action():
    catalog = NormCatalog(entries=(), strict=True)

    assert catalog.is_allowed("llm", "unknown_action") is False
    assert catalog.is_allowed("human", "unknown_action") is False
    assert catalog.is_allowed("any", "unknown_action") is False


def test_strict_true_is_default():
    catalog = NormCatalog(entries=())
    assert catalog.strict is True
    assert catalog.is_allowed("llm", "anything") is False


def test_strict_false_allows_unlisted():
    catalog = NormCatalog(entries=(), strict=False)
    assert catalog.is_allowed("llm", "unknown_action") is True


def test_explicit_forbidden_denies_regardless_of_strict():
    entry = _make_entry("TEST-001", "llm", "forbidden_op", "forbidden")
    catalog = NormCatalog(entries=(entry,), strict=False)

    assert catalog.is_allowed("llm", "forbidden_op") is False


def test_explicit_allow_entry_permits_action():
    entry = _make_entry("TEST-002", "llm", "allowed_op", "allowed")
    catalog = NormCatalog(entries=(entry,), strict=True)

    assert catalog.is_allowed("llm", "allowed_op") is True


def test_any_actor_entry_applies_to_all_actors():
    entry = _make_entry("TEST-003", "any", "shared_action", "allowed")
    catalog = NormCatalog(entries=(entry,), strict=True)

    assert catalog.is_allowed("llm", "shared_action") is True
    assert catalog.is_allowed("human", "shared_action") is True


def test_actor_specific_allow_does_not_apply_to_others():
    entry = _make_entry("TEST-004", "human", "human_only_op", "allowed")
    catalog = NormCatalog(entries=(entry,), strict=True)

    assert catalog.is_allowed("human", "human_only_op") is True
    assert catalog.is_allowed("llm", "human_only_op") is False


def test_get_norm_returns_entry_by_id():
    entry = _make_entry("NORM-ACTOR-001", "llm", "emit_spec_approved", "forbidden")
    catalog = NormCatalog(entries=(entry,), strict=True)

    found = catalog.get_norm("NORM-ACTOR-001")
    assert found is not None
    assert found.norm_id == "NORM-ACTOR-001"
    assert found.result == "forbidden"


def test_get_norm_returns_none_for_missing_id():
    catalog = NormCatalog(entries=(), strict=True)
    assert catalog.get_norm("NONEXISTENT") is None
