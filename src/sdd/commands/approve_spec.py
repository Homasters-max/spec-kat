"""approve-spec — emits SpecApproved event (BC-31-1, I-HANDLER-PURE-1).

Handler is pure: reads spec draft to compute hash; no EventStore/projection calls.
Write Kernel moves spec_draft/Spec_vN.md → specs/Spec_vN.md post-append (BC-31-1).
"""
from __future__ import annotations

import hashlib
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from sdd.commands._base import CommandHandlerBase, error_event_boundary
from sdd.core.errors import InvalidState, MissingContext
from sdd.core.events import DomainEvent, EventLevel, SpecApproved
from sdd.infra.paths import specs_dir, specs_draft_dir


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class ApproveSpecHandler(CommandHandlerBase):
    """Pure handler: returns [SpecApproved] without side-effects (I-HANDLER-PURE-1).

    Guard: raises InvalidState if Spec_vN.md already in specs/ (duplicate approval).
    Guard: raises MissingContext if Spec_vN.md absent from specs_draft/.
    """

    @error_event_boundary(source=__name__)
    def handle(self, cmd: Any) -> list[DomainEvent]:
        phase_id: int = cmd.phase_id
        actor: str = getattr(cmd, "actor", "human")

        spec_filename = f"Spec_v{phase_id}.md"
        approved_path = specs_dir() / spec_filename
        draft_path = specs_draft_dir() / spec_filename

        if approved_path.exists():
            raise InvalidState(
                f"{spec_filename} already exists in specs/ — approve-spec already executed"
            )

        if not draft_path.exists():
            raise MissingContext(
                f"{spec_filename} not found in specs_draft/ — draft must exist before approval"
            )

        spec_hash = hashlib.sha256(draft_path.read_bytes()).hexdigest()[:16]

        return [
            SpecApproved(
                event_type="SpecApproved",
                event_id=str(uuid.uuid4()),
                appended_at=int(time.time() * 1000),
                level=EventLevel.L1,
                event_source="runtime",
                caused_by_meta_seq=None,
                phase_id=phase_id,
                spec_hash=spec_hash,
                actor=actor,
                spec_path=spec_filename,
            )
        ]


def _build_approve_spec_spec() -> Any:
    """Deferred import to avoid circular dependency with registry.py."""
    from sdd.commands.registry import CommandSpec, ProjectionType

    return CommandSpec(
        name="approve-spec",
        handler_class=ApproveSpecHandler,
        actor="human",
        action="approve_spec",
        projection=ProjectionType.NONE,
        uses_task_id=False,
        requires_active_phase=False,
        event_schema=(SpecApproved,),
        preconditions=(
            "actor == human",
            "Spec_vN.md exists in specs_draft/",
            "Spec_vN.md NOT yet in specs/ (not already approved)",
        ),
        postconditions=(
            "SpecApproved in EventLog",
            "Write Kernel moves specs_draft/Spec_vN.md → specs/Spec_vN.md",
        ),
        description="Approve a spec draft — records SpecApproved event (BC-31-1)",
    )


approve_spec_spec = _build_approve_spec_spec()
