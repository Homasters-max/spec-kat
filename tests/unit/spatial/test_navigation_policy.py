"""Tests for NavigationIntent (I-NAV-7, I-NAV-8): INTENT_CEILING and _FULL_CONSTRAINTS."""
import pytest

from sdd.spatial.navigator import (
    INTENT_CEILING,
    MODE_ORDER,
    AllowedOperations,
    DenialTrace,
    NavigationIntent,
    NavigationSession,
    _FULL_CONSTRAINTS,
    _modes_up_to,
    resolve_action,
)


# ---------------------------------------------------------------------------
# INTENT_CEILING table
# ---------------------------------------------------------------------------

def test_intent_ceiling_keys():
    assert set(INTENT_CEILING.keys()) == {"explore", "locate", "analyze", "code_write", "code_modify"}


def test_intent_ceiling_values_are_valid_modes():
    for ceiling in INTENT_CEILING.values():
        assert ceiling in MODE_ORDER


def test_ceiling_explore():
    assert INTENT_CEILING["explore"] == "SUMMARY"


def test_ceiling_locate():
    assert INTENT_CEILING["locate"] == "SUMMARY"


def test_ceiling_analyze():
    assert INTENT_CEILING["analyze"] == "SIGNATURE"


def test_ceiling_code_write():
    assert INTENT_CEILING["code_write"] == "FULL"


def test_ceiling_code_modify():
    assert INTENT_CEILING["code_modify"] == "FULL"


# ---------------------------------------------------------------------------
# NavigationIntent.allowed_modes() — I-NAV-8
# ---------------------------------------------------------------------------

def test_explore_allowed_modes():
    intent = NavigationIntent(type="explore")
    assert intent.allowed_modes() == frozenset({"POINTER", "SUMMARY"})


def test_locate_allowed_modes():
    intent = NavigationIntent(type="locate")
    assert intent.allowed_modes() == frozenset({"POINTER", "SUMMARY"})


def test_analyze_allowed_modes():
    intent = NavigationIntent(type="analyze")
    assert intent.allowed_modes() == frozenset({"POINTER", "SUMMARY", "SIGNATURE"})


def test_code_write_allowed_modes():
    intent = NavigationIntent(type="code_write")
    assert intent.allowed_modes() == frozenset({"POINTER", "SUMMARY", "SIGNATURE", "FULL"})


def test_code_modify_allowed_modes():
    intent = NavigationIntent(type="code_modify")
    assert intent.allowed_modes() == frozenset({"POINTER", "SUMMARY", "SIGNATURE", "FULL"})


def test_ceiling_matches_allowed_modes():
    for intent_type in INTENT_CEILING:
        intent = NavigationIntent(type=intent_type)  # type: ignore[arg-type]
        ceiling = intent.ceiling()
        assert ceiling in intent.allowed_modes()
        ceiling_index = MODE_ORDER.index(ceiling)
        for mode in MODE_ORDER[ceiling_index + 1:]:
            assert mode not in intent.allowed_modes()


# ---------------------------------------------------------------------------
# _modes_up_to helper
# ---------------------------------------------------------------------------

def test_modes_up_to_pointer():
    assert _modes_up_to("POINTER") == frozenset({"POINTER"})


def test_modes_up_to_full():
    assert _modes_up_to("FULL") == frozenset({"POINTER", "SUMMARY", "SIGNATURE", "FULL"})


def test_modes_up_to_summary():
    assert _modes_up_to("SUMMARY") == frozenset({"POINTER", "SUMMARY"})


# ---------------------------------------------------------------------------
# _FULL_CONSTRAINTS structure
# ---------------------------------------------------------------------------

def test_full_constraints_is_list():
    assert isinstance(_FULL_CONSTRAINTS, list)
    assert len(_FULL_CONSTRAINTS) == 3


def test_full_constraints_all_target_full():
    for mode_guard, _, _, _ in _FULL_CONSTRAINTS:
        assert mode_guard == "FULL"


def test_full_constraints_reasons():
    reasons = [r for _, _, _, r in _FULL_CONSTRAINTS]
    assert "summary_required" in reasons
    assert "step_limit_exceeded" in reasons
    assert "code_intent_required" in reasons


# ---------------------------------------------------------------------------
# resolve_action — I-NAV-8: intent ceiling as single source of truth
# ---------------------------------------------------------------------------

def _fresh_session(step_id: int = 0) -> NavigationSession:
    return NavigationSession(step_id=step_id)


def test_resolve_pointer_no_intent():
    session = _fresh_session()
    result = resolve_action(None, session, "FILE:x", "POINTER")
    assert result.denial is None
    assert "POINTER" in result.modes


def test_resolve_summary_no_intent():
    session = _fresh_session()
    result = resolve_action(None, session, "FILE:x", "SUMMARY")
    assert result.denial is None


def test_resolve_signature_no_intent_denied():
    """Without intent, ceiling is SUMMARY — SIGNATURE must be denied."""
    session = _fresh_session()
    result = resolve_action(None, session, "FILE:x", "SIGNATURE")
    assert result.denial is not None
    assert "I-NAV-7" in result.denial.violated


def test_resolve_full_no_intent_denied():
    """Without intent, FULL must be denied (I-NAV-7)."""
    session = _fresh_session()
    result = resolve_action(None, session, "FILE:x", "FULL")
    assert result.denial is not None
    assert "I-NAV-7" in result.denial.violated
    assert result.denial.mode == "FULL"


def test_resolve_full_explore_intent_denied():
    """explore ceiling=SUMMARY → FULL denied with I-NAV-8."""
    session = _fresh_session()
    intent = NavigationIntent(type="explore")
    result = resolve_action(intent, session, "FILE:x", "FULL")
    assert result.denial is not None
    assert "I-NAV-8" in result.denial.violated
    assert result.denial.reason == "intent_ceiling_exceeded"


def test_resolve_full_analyze_intent_denied():
    """analyze ceiling=SIGNATURE → FULL denied with I-NAV-8."""
    session = _fresh_session()
    intent = NavigationIntent(type="analyze")
    result = resolve_action(intent, session, "FILE:x", "FULL")
    assert result.denial is not None
    assert "I-NAV-8" in result.denial.violated


def test_resolve_full_code_write_no_prior_load_denied():
    """code_write allows FULL ceiling, but I-NAV-1: SUMMARY must precede FULL."""
    session = _fresh_session()
    intent = NavigationIntent(type="code_write")
    result = resolve_action(intent, session, "FILE:x", "FULL")
    assert result.denial is not None
    assert "I-NAV-1" in result.denial.violated
    assert result.denial.reason == "summary_required"


def test_resolve_full_code_write_after_summary_allowed():
    """code_write + prior SUMMARY load → FULL allowed."""
    session = _fresh_session()
    session.record_load("FILE:x", "SUMMARY")
    intent = NavigationIntent(type="code_write")
    result = resolve_action(intent, session, "FILE:x", "FULL")
    assert result.denial is None
    assert "FULL" in result.modes


def test_resolve_full_code_write_after_signature_allowed():
    """code_write + prior SIGNATURE load → FULL allowed (I-NAV-1: SIGNATURE qualifies)."""
    session = _fresh_session()
    session.record_load("FILE:x", "SIGNATURE")
    intent = NavigationIntent(type="code_write")
    result = resolve_action(intent, session, "FILE:x", "FULL")
    assert result.denial is None


def test_resolve_full_step_limit_exceeded():
    """Second FULL in same step is denied (I-NAV-3, I-NAV-6)."""
    session = _fresh_session()
    session.record_load("FILE:x", "SUMMARY")
    session.record_load("FILE:y", "SUMMARY")
    # First FULL
    session.record_load("FILE:x", "FULL")
    intent = NavigationIntent(type="code_write")
    # Second FULL in same step
    result = resolve_action(intent, session, "FILE:y", "FULL")
    assert result.denial is not None
    assert "I-NAV-3" in result.denial.violated
    assert "I-NAV-6" in result.denial.violated
    assert result.denial.reason == "step_limit_exceeded"


def test_resolve_full_allowed_after_next_step():
    """After next_step(), FULL limit resets (I-NAV-6, I-NAV-9)."""
    session = _fresh_session()
    session.record_load("FILE:x", "SUMMARY")
    session.record_load("FILE:x", "FULL")
    session.next_step()
    session.record_load("FILE:y", "SUMMARY")
    intent = NavigationIntent(type="code_modify")
    result = resolve_action(intent, session, "FILE:y", "FULL")
    assert result.denial is None


def test_resolve_full_code_intent_required():
    """explore intent: FULL denied even with prior SUMMARY (I-NAV-5 via ceiling)."""
    session = _fresh_session()
    session.record_load("FILE:x", "SUMMARY")
    intent = NavigationIntent(type="explore")
    result = resolve_action(intent, session, "FILE:x", "FULL")
    assert result.denial is not None
    assert "I-NAV-8" in result.denial.violated


def test_denial_trace_fields():
    session = _fresh_session()
    intent = NavigationIntent(type="explore")
    result = resolve_action(intent, session, "FILE:x", "FULL")
    assert result.denial is not None
    assert isinstance(result.denial.violated, list)
    assert isinstance(result.denial.mode, str)
    assert isinstance(result.denial.reason, str)


# ---------------------------------------------------------------------------
# AllowedOperations and DenialTrace are frozen dataclasses
# ---------------------------------------------------------------------------

def test_denial_trace_frozen():
    d = DenialTrace(mode="FULL", violated=["I-NAV-1"], reason="summary_required")
    with pytest.raises((AttributeError, TypeError)):
        d.mode = "SUMMARY"  # type: ignore[misc]


def test_allowed_operations_frozen():
    ao = AllowedOperations(modes=frozenset({"POINTER"}), denial=None)
    with pytest.raises((AttributeError, TypeError)):
        ao.modes = frozenset()  # type: ignore[misc]


# ---------------------------------------------------------------------------
# I-NAV-8: intent priority over session — intent ceiling cannot be expanded
# ---------------------------------------------------------------------------

def test_intent_ceiling_cannot_be_expanded_by_session():
    """Session state cannot expand beyond intent ceiling (I-NAV-8)."""
    session = _fresh_session()
    # Even with lots of history, explore ceiling=SUMMARY blocks FULL
    session.record_load("FILE:x", "SUMMARY")
    session.record_load("FILE:x", "SIGNATURE")
    intent = NavigationIntent(type="explore")
    result = resolve_action(intent, session, "FILE:x", "FULL")
    assert result.denial is not None
    assert "I-NAV-8" in result.denial.violated


def test_code_modify_full_requires_summary_first():
    """code_modify ceiling=FULL but still requires I-NAV-1: SUMMARY before FULL."""
    session = _fresh_session()
    intent = NavigationIntent(type="code_modify")
    result = resolve_action(intent, session, "FILE:x", "FULL")
    assert result.denial is not None
    assert "I-NAV-1" in result.denial.violated
