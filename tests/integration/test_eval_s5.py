"""S5: Scope boundary — check-scope exit 1 for file outside session allowed_files.

BC-61-T4 (S5): negative enforcement scenario. I-SCOPE-STRICT-1: when session_id
is given, resolve_scope uses GraphSessionState.allowed_files. File outside that
set → DENY regardless of declared_inputs. ScenarioResult.status = PASS when
enforcement correctly blocks the out-of-scope access.
"""
from __future__ import annotations

import json
from unittest.mock import patch

from sdd.eval.eval_fixtures import EvalFixtureTarget
from sdd.eval.eval_harness import ScenarioResult
from sdd.graph_navigation.session_state import GraphSessionState
from sdd.guards.scope_policy import ScopeDecision, resolve_scope


class TestS5ScopeBoundary:
    """S5: resolve_scope with session_id denies file outside allowed_files."""

    def _make_scope_decision_deny(self, file_path: str) -> ScopeDecision:
        """Build a baseline DENY decision as norm evaluator would produce."""
        return ScopeDecision(
            allowed=False,
            norm_id="NORM-SCOPE-002",
            reason=f"Reading from src/ forbidden unless in Task Inputs: '{file_path}'",
            operation="read",
            file_path=file_path,
        )

    def test_s5_file_outside_allowed_files_is_denied(self) -> None:
        """I-SCOPE-STRICT-1: file not in session.allowed_files → DENY."""
        # Session allows only eval_fixtures.py
        allowed_session = GraphSessionState(
            session_id="eval-s5-scope",
            phase_id=61,
            allowed_files=frozenset(["src/sdd/eval/eval_fixtures.py"]),
            trace_path=["FILE:src/sdd/eval/eval_fixtures.py"],
        )
        # Target file is outside allowed scope
        outside_file = "src/sdd/eval/eval_deep.py"

        norm_deny = self._make_scope_decision_deny(outside_file)

        with patch("sdd.guards.scope_policy.load_graph_session", return_value=allowed_session):
            decision = resolve_scope(
                norm_deny,
                declared_inputs=[outside_file],  # even declared, session gates override
                allowed_overrides=frozenset({"NORM-SCOPE-002"}),
                session_id="eval-s5-scope",
            )

        result = ScenarioResult(
            scenario_id="S5",
            status="PASS" if not decision.allowed else "FAIL",
            stdout="",
            stderr=json.dumps({"error": "SCOPE_DENIED", "file": outside_file}),
            exit_code=1 if not decision.allowed else 0,
        )
        assert result.status == "PASS", (
            f"S5: scope enforcement failed — file outside allowed_files should be denied, "
            f"got allowed={decision.allowed}, reason={decision.reason!r}"
        )
        assert result.exit_code == 1

    def test_s5_file_inside_allowed_files_is_permitted(self) -> None:
        """S5 contrast: file IN session.allowed_files → allowed (override works)."""
        fixture = EvalFixtureTarget.default()
        allowed_session = GraphSessionState(
            session_id="eval-s5-scope-ok",
            phase_id=61,
            allowed_files=frozenset([fixture.file_path]),
            trace_path=[fixture.node_id],
        )
        norm_deny = self._make_scope_decision_deny(fixture.file_path)

        with patch("sdd.guards.scope_policy.load_graph_session", return_value=allowed_session):
            decision = resolve_scope(
                norm_deny,
                declared_inputs=[fixture.file_path],
                allowed_overrides=frozenset({"NORM-SCOPE-002"}),
                session_id="eval-s5-scope-ok",
            )

        assert decision.allowed, (
            f"S5 contrast: file inside allowed_files should be permitted, got denied: "
            f"{decision.reason!r}"
        )
        assert decision.override is not None, "S5 contrast: override metadata must be emitted (I-RRL-3)"

    def test_s5_override_metadata_emitted_on_deny(self) -> None:
        """I-RRL-3: silent override forbidden — decision must carry reason even on DENY."""
        outside_file = "src/sdd/eval/eval_deep.py"
        allowed_session = GraphSessionState(
            session_id="eval-s5-metadata",
            phase_id=61,
            allowed_files=frozenset(["src/sdd/eval/eval_fixtures.py"]),
            trace_path=[],
        )
        norm_deny = self._make_scope_decision_deny(outside_file)

        with patch("sdd.guards.scope_policy.load_graph_session", return_value=allowed_session):
            decision = resolve_scope(
                norm_deny,
                declared_inputs=[],
                allowed_overrides=frozenset({"NORM-SCOPE-002"}),
                session_id="eval-s5-metadata",
            )

        assert not decision.allowed
        # DENY must carry original norm reason — not silently produce empty reason (I-RRL-3)
        assert decision.reason, "S5: DENY decision must carry a non-empty reason"
        assert decision.norm_id == "NORM-SCOPE-002"

    def test_s5_session_not_found_denies(self) -> None:
        """I-RRL-2: session not found → deterministic DENY (same inputs → same decision)."""
        outside_file = "src/sdd/guards/scope_policy.py"
        norm_deny = self._make_scope_decision_deny(outside_file)

        with patch("sdd.guards.scope_policy.load_graph_session", return_value=None):
            decision = resolve_scope(
                norm_deny,
                declared_inputs=[outside_file],
                allowed_overrides=frozenset({"NORM-SCOPE-002"}),
                session_id="eval-s5-missing-session",
            )

        assert not decision.allowed, "S5: missing session must produce DENY (I-RRL-2)"
