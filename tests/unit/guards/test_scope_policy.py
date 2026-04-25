"""Unit tests for scope_policy — I-RRL-1..3."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from sdd.guards.scope_policy import (
    OverrideMetadata,
    ScopeDecision,
    is_declared_input,
    is_override_allowed,
    resolve_scope,
)

_OVERRIDABLE = frozenset({"NORM-SCOPE-001", "NORM-SCOPE-002"})
_NON_OVERRIDABLE = frozenset()


def _deny(norm_id: str, file_path: str = "tests/harness/api.py") -> ScopeDecision:
    return ScopeDecision(
        allowed=False,
        norm_id=norm_id,
        reason=f"Denied by {norm_id}",
        operation="read",
        file_path=file_path,
    )


def _allow(file_path: str = "CLAUDE.md") -> ScopeDecision:
    return ScopeDecision(
        allowed=True,
        norm_id=None,
        reason="Allowed",
        operation="read",
        file_path=file_path,
    )


# ── is_declared_input ──────────────────────────────────────────────────────────


def test_is_declared_input_exact_match(tmp_path):
    f = tmp_path / "api.py"
    f.touch()
    assert is_declared_input(str(f), [str(f)])


def test_is_declared_input_relative_resolves(tmp_path, monkeypatch):
    f = tmp_path / "api.py"
    f.touch()
    monkeypatch.chdir(tmp_path)
    assert is_declared_input("api.py", [str(f)])


def test_is_declared_input_not_in_list(tmp_path):
    f = tmp_path / "api.py"
    other = tmp_path / "other.py"
    f.touch()
    other.touch()
    assert not is_declared_input(str(f), [str(other)])


def test_is_declared_input_empty_list(tmp_path):
    f = tmp_path / "api.py"
    f.touch()
    assert not is_declared_input(str(f), [])


# ── is_override_allowed ────────────────────────────────────────────────────────


def test_is_override_allowed_known_norm():
    assert is_override_allowed("NORM-SCOPE-001", _OVERRIDABLE)


def test_is_override_allowed_second_norm():
    assert is_override_allowed("NORM-SCOPE-002", _OVERRIDABLE)


def test_is_override_allowed_non_overridable():
    assert not is_override_allowed("NORM-SCOPE-003", _OVERRIDABLE)


def test_is_override_allowed_unknown_norm():
    assert not is_override_allowed("NORM-SCOPE-999", _OVERRIDABLE)


def test_is_override_allowed_empty_set():
    assert not is_override_allowed("NORM-SCOPE-001", frozenset())


# ── resolve_scope: already-allowed passthrough ────────────────────────────────


def test_resolve_scope_already_allowed_returns_unchanged():
    decision = _allow()
    result = resolve_scope(decision, ["CLAUDE.md"], _OVERRIDABLE)
    assert result is decision


# ── resolve_scope: override fires ─────────────────────────────────────────────


def test_resolve_scope_override_allows_when_declared(tmp_path, monkeypatch):
    f = tmp_path / "api.py"
    f.touch()
    monkeypatch.chdir(tmp_path)
    deny = _deny("NORM-SCOPE-001", str(f))
    result = resolve_scope(deny, [str(f)], _OVERRIDABLE)
    assert result.allowed is True


def test_resolve_scope_override_emits_metadata(tmp_path, monkeypatch):
    """I-RRL-3: override must emit override metadata."""
    f = tmp_path / "api.py"
    f.touch()
    monkeypatch.chdir(tmp_path)
    deny = _deny("NORM-SCOPE-001", str(f))
    result = resolve_scope(deny, [str(f)], _OVERRIDABLE)
    assert result.override is not None
    assert result.override.type == "TASK_INPUT_OVERRIDE"
    assert result.override.overrides_norm == "NORM-SCOPE-001"
    assert result.override.policy == "explicit_override_only"


def test_resolve_scope_reason_includes_override_tag(tmp_path, monkeypatch):
    f = tmp_path / "api.py"
    f.touch()
    monkeypatch.chdir(tmp_path)
    deny = _deny("NORM-SCOPE-001", str(f))
    result = resolve_scope(deny, [str(f)], _OVERRIDABLE)
    assert "TASK_INPUT_OVERRIDE" in result.reason


# ── resolve_scope: override does NOT fire ─────────────────────────────────────


def test_resolve_scope_no_override_when_file_not_in_inputs(tmp_path, monkeypatch):
    f = tmp_path / "api.py"
    other = tmp_path / "other.py"
    f.touch(); other.touch()
    monkeypatch.chdir(tmp_path)
    deny = _deny("NORM-SCOPE-001", str(f))
    result = resolve_scope(deny, [str(other)], _OVERRIDABLE)
    assert result.allowed is False
    assert result.override is None


def test_resolve_scope_no_override_when_inputs_empty(tmp_path, monkeypatch):
    f = tmp_path / "api.py"
    f.touch()
    monkeypatch.chdir(tmp_path)
    deny = _deny("NORM-SCOPE-001", str(f))
    result = resolve_scope(deny, [], _OVERRIDABLE)
    assert result.allowed is False


def test_resolve_scope_norm_scope_003_non_overridable(tmp_path, monkeypatch):
    """NORM-SCOPE-003 (glob) must remain blocked even if in declared inputs."""
    f = tmp_path / "api.py"
    f.touch()
    monkeypatch.chdir(tmp_path)
    deny = _deny("NORM-SCOPE-003", str(f))
    result = resolve_scope(deny, [str(f)], _OVERRIDABLE)
    assert result.allowed is False
    assert result.override is None


def test_resolve_scope_norm_scope_004_non_overridable(tmp_path, monkeypatch):
    """NORM-SCOPE-004 (.sdd/specs/) must remain blocked even if in declared inputs."""
    f = tmp_path / "SDD_Spec_v1.md"
    f.touch()
    monkeypatch.chdir(tmp_path)
    deny = _deny("NORM-SCOPE-004", str(f))
    result = resolve_scope(deny, [str(f)], _OVERRIDABLE)
    assert result.allowed is False
    assert result.override is None


def test_resolve_scope_norm_id_none_no_override():
    deny = ScopeDecision(
        allowed=False, norm_id=None,
        reason="Unknown op", operation="xyz", file_path="foo.py"
    )
    result = resolve_scope(deny, ["foo.py"], _OVERRIDABLE)
    assert result.allowed is False


# ── I-RRL-2: determinism ──────────────────────────────────────────────────────


def test_resolve_scope_deterministic(tmp_path, monkeypatch):
    """I-RRL-2: identical inputs → identical result."""
    f = tmp_path / "api.py"
    f.touch()
    monkeypatch.chdir(tmp_path)
    deny = _deny("NORM-SCOPE-001", str(f))
    r1 = resolve_scope(deny, [str(f)], _OVERRIDABLE)
    r2 = resolve_scope(deny, [str(f)], _OVERRIDABLE)
    assert r1 == r2


def test_is_declared_input_deterministic(tmp_path):
    f = tmp_path / "api.py"
    f.touch()
    r1 = is_declared_input(str(f), [str(f)])
    r2 = is_declared_input(str(f), [str(f)])
    assert r1 == r2


# ── ScopeDecision.to_dict ─────────────────────────────────────────────────────


def test_to_dict_no_override():
    d = ScopeDecision(
        allowed=True, norm_id=None, reason="ok", operation="read", file_path="f.py"
    ).to_dict()
    assert "override" not in d
    assert d["allowed"] is True


def test_to_dict_with_override():
    meta = OverrideMetadata(
        type="TASK_INPUT_OVERRIDE", overrides_norm="NORM-SCOPE-001", policy="explicit_override_only"
    )
    d = ScopeDecision(
        allowed=True, norm_id="NORM-SCOPE-001", reason="ok",
        operation="read", file_path="f.py", override=meta
    ).to_dict()
    assert d["override"]["type"] == "TASK_INPUT_OVERRIDE"
    assert d["override"]["overrides_norm"] == "NORM-SCOPE-001"
    assert d["override"]["policy"] == "explicit_override_only"
