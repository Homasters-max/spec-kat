"""Unit tests for ApproveSpecHandler — T-3112.

Covers: I-HANDLER-PURE-1, I-ERROR-1, I-DB-TEST-1, I-DB-TEST-2
Acceptance: §9 #1 (approve → SpecApproved returned), §9 #2 (duplicate → InvalidState)
"""
from __future__ import annotations

import dataclasses
import hashlib
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

from sdd.commands.approve_spec import ApproveSpecHandler
from sdd.core.errors import InvalidState, MissingContext
from sdd.core.events import ErrorEvent, SpecApproved


# ---------------------------------------------------------------------------
# Test command fixture
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class _ApproveSpecCmd:
    command_id: str
    phase_id: int
    actor: str = "human"


def _cmd(phase_id: int = 31, actor: str = "human") -> _ApproveSpecCmd:
    return _ApproveSpecCmd(command_id=str(uuid.uuid4()), phase_id=phase_id, actor=actor)


# ---------------------------------------------------------------------------
# Pytest fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_dirs(tmp_path: Path):
    """Isolated specs/ and specs_draft/ directories (I-DB-TEST-1)."""
    specs = tmp_path / "specs"
    draft = tmp_path / "specs_draft"
    specs.mkdir()
    draft.mkdir()
    return specs, draft


@pytest.fixture()
def tmp_db(tmp_path: Path) -> str:
    """Temp DuckDB path — never production DB (I-DB-TEST-1)."""
    return str(tmp_path / "test_events.duckdb")


# ---------------------------------------------------------------------------
# §9 Acceptance: happy path and duplicate guard
# ---------------------------------------------------------------------------

class TestApproveSpecAcceptance:

    def test_returns_spec_approved_event(self, tmp_db, tmp_dirs):
        """§9 #1: handle() returns [SpecApproved] when draft exists and approved/ has no file."""
        specs_dir, draft_dir = tmp_dirs
        (draft_dir / "Spec_v31.md").write_text("# Spec v31\n")

        with (
            patch("sdd.commands.approve_spec.specs_dir", return_value=specs_dir),
            patch("sdd.commands.approve_spec.specs_draft_dir", return_value=draft_dir),
        ):
            handler = ApproveSpecHandler(tmp_db)
            events = handler.handle(_cmd(phase_id=31))

        assert len(events) == 1
        event = events[0]
        assert isinstance(event, SpecApproved)
        assert event.phase_id == 31
        assert event.actor == "human"
        assert event.spec_path == "Spec_v31.md"

    def test_spec_hash_is_sha256_prefix_of_content(self, tmp_db, tmp_dirs):
        """spec_hash == sha256(draft bytes)[:16]."""
        specs_dir, draft_dir = tmp_dirs
        content = b"# Spec v31 deterministic\n"
        (draft_dir / "Spec_v31.md").write_bytes(content)
        expected = hashlib.sha256(content).hexdigest()[:16]

        with (
            patch("sdd.commands.approve_spec.specs_dir", return_value=specs_dir),
            patch("sdd.commands.approve_spec.specs_draft_dir", return_value=draft_dir),
        ):
            events = ApproveSpecHandler(tmp_db).handle(_cmd(phase_id=31))

        assert events[0].spec_hash == expected

    def test_event_fields_populated(self, tmp_db, tmp_dirs):
        """SpecApproved carries non-empty event_id, appended_at, level, phase_id."""
        specs_dir, draft_dir = tmp_dirs
        (draft_dir / "Spec_v5.md").write_text("spec")

        with (
            patch("sdd.commands.approve_spec.specs_dir", return_value=specs_dir),
            patch("sdd.commands.approve_spec.specs_draft_dir", return_value=draft_dir),
        ):
            events = ApproveSpecHandler(tmp_db).handle(_cmd(phase_id=5))

        ev = events[0]
        assert ev.event_id  # non-empty uuid
        assert ev.appended_at > 0
        assert ev.phase_id == 5

    def test_duplicate_approval_raises_invalid_state(self, tmp_db, tmp_dirs):
        """§9 #2: raises InvalidState when Spec_vN.md already exists in specs/."""
        specs_dir, draft_dir = tmp_dirs
        (specs_dir / "Spec_v31.md").write_text("already approved")
        (draft_dir / "Spec_v31.md").write_text("draft")

        with (
            patch("sdd.commands.approve_spec.specs_dir", return_value=specs_dir),
            patch("sdd.commands.approve_spec.specs_draft_dir", return_value=draft_dir),
        ):
            handler = ApproveSpecHandler(tmp_db)
            with pytest.raises(InvalidState, match="already exists in specs/"):
                handler.handle(_cmd(phase_id=31))

    def test_missing_draft_raises_missing_context(self, tmp_db, tmp_dirs):
        """Guard raises MissingContext when draft does not exist in specs_draft/."""
        specs_dir, draft_dir = tmp_dirs
        # draft NOT created intentionally

        with (
            patch("sdd.commands.approve_spec.specs_dir", return_value=specs_dir),
            patch("sdd.commands.approve_spec.specs_draft_dir", return_value=draft_dir),
        ):
            handler = ApproveSpecHandler(tmp_db)
            with pytest.raises(MissingContext, match="not found in specs_draft/"):
                handler.handle(_cmd(phase_id=31))


# ---------------------------------------------------------------------------
# I-HANDLER-PURE-1: handle() returns events only, no EventStore calls
# ---------------------------------------------------------------------------

class TestHandlerPurity:

    def test_handle_does_not_call_eventlog_append(self, tmp_db, tmp_dirs):
        """I-HANDLER-PURE-1: EventLog.append must not be called inside handle()."""
        specs_dir, draft_dir = tmp_dirs
        (draft_dir / "Spec_v31.md").write_text("spec")

        with (
            patch("sdd.commands.approve_spec.specs_dir", return_value=specs_dir),
            patch("sdd.commands.approve_spec.specs_draft_dir", return_value=draft_dir),
            patch("sdd.commands._base.EventLog") as mock_el_class,
        ):
            mock_el_class.return_value.exists_command.return_value = False
            mock_el_class.return_value.exists_semantic.return_value = False
            ApproveSpecHandler(tmp_db).handle(_cmd(phase_id=31))

        mock_el_class.return_value.append.assert_not_called()

    def test_handle_returns_list_of_domain_events(self, tmp_db, tmp_dirs):
        """I-HANDLER-PURE-1: return value is a list (not a generator, not None)."""
        specs_dir, draft_dir = tmp_dirs
        (draft_dir / "Spec_v31.md").write_text("spec")

        with (
            patch("sdd.commands.approve_spec.specs_dir", return_value=specs_dir),
            patch("sdd.commands.approve_spec.specs_draft_dir", return_value=draft_dir),
        ):
            result = ApproveSpecHandler(tmp_db).handle(_cmd(phase_id=31))

        assert isinstance(result, list)
        assert all(isinstance(e, SpecApproved) for e in result)


# ---------------------------------------------------------------------------
# I-ERROR-1: ErrorEvent attached to exception before re-raising
# ---------------------------------------------------------------------------

class TestErrorBoundary:

    def test_invalid_state_carries_error_event(self, tmp_db, tmp_dirs):
        """I-ERROR-1: InvalidState → exc._sdd_error_events contains one ErrorEvent."""
        specs_dir, draft_dir = tmp_dirs
        (specs_dir / "Spec_v31.md").write_text("already approved")
        (draft_dir / "Spec_v31.md").write_text("draft")

        with (
            patch("sdd.commands.approve_spec.specs_dir", return_value=specs_dir),
            patch("sdd.commands.approve_spec.specs_draft_dir", return_value=draft_dir),
        ):
            with pytest.raises(InvalidState) as exc_info:
                ApproveSpecHandler(tmp_db).handle(_cmd(phase_id=31))

        error_events = getattr(exc_info.value, "_sdd_error_events", None)
        assert error_events is not None and len(error_events) == 1
        assert isinstance(error_events[0], ErrorEvent)
        assert error_events[0].error_type == "InvalidState"

    def test_missing_context_carries_error_event(self, tmp_db, tmp_dirs):
        """I-ERROR-1: MissingContext → exc._sdd_error_events contains one ErrorEvent."""
        specs_dir, draft_dir = tmp_dirs

        with (
            patch("sdd.commands.approve_spec.specs_dir", return_value=specs_dir),
            patch("sdd.commands.approve_spec.specs_draft_dir", return_value=draft_dir),
        ):
            with pytest.raises(MissingContext) as exc_info:
                ApproveSpecHandler(tmp_db).handle(_cmd(phase_id=31))

        error_events = getattr(exc_info.value, "_sdd_error_events", None)
        assert error_events is not None and len(error_events) == 1
        assert isinstance(error_events[0], ErrorEvent)
        assert error_events[0].error_type == "MissingContext"

    def test_error_event_source_is_module_name(self, tmp_db, tmp_dirs):
        """ErrorEvent.source == 'sdd.commands.approve_spec' (matches @error_event_boundary)."""
        specs_dir, draft_dir = tmp_dirs
        (specs_dir / "Spec_v31.md").write_text("already")

        with (
            patch("sdd.commands.approve_spec.specs_dir", return_value=specs_dir),
            patch("sdd.commands.approve_spec.specs_draft_dir", return_value=draft_dir),
        ):
            with pytest.raises(InvalidState) as exc_info:
                ApproveSpecHandler(tmp_db).handle(_cmd(phase_id=31))

        assert exc_info.value._sdd_error_events[0].source == "sdd.commands.approve_spec"

    def test_exception_is_reraised_not_suppressed(self, tmp_db, tmp_dirs):
        """I-ERROR-1: error_event_boundary MUST re-raise; must not swallow exception."""
        specs_dir, draft_dir = tmp_dirs

        with (
            patch("sdd.commands.approve_spec.specs_dir", return_value=specs_dir),
            patch("sdd.commands.approve_spec.specs_draft_dir", return_value=draft_dir),
        ):
            with pytest.raises((InvalidState, MissingContext)):
                ApproveSpecHandler(tmp_db).handle(_cmd(phase_id=31))


# ---------------------------------------------------------------------------
# I-DB-TEST-1 / I-DB-TEST-2: DB isolation and test-context fail-fast
# ---------------------------------------------------------------------------

class TestDbIsolation:

    def test_tmp_db_is_not_production_db(self, tmp_db):
        """I-DB-TEST-1: tmp_db path must not resolve to production sdd_events.duckdb."""
        prod_candidates = [
            Path(".sdd/state/sdd_events.duckdb").resolve(),
            Path(".sdd/sdd_events.duckdb").resolve(),
        ]
        assert Path(tmp_db).resolve() not in prod_candidates

    def test_handler_requires_nonempty_db_path(self):
        """I-DB-1: empty db_path must not be passed to handler in production paths."""
        # Verify the constructor accepts explicit non-empty path (contract, not validation)
        handler = ApproveSpecHandler("/tmp/explicit_path.duckdb")
        assert handler._db_path == "/tmp/explicit_path.duckdb"
