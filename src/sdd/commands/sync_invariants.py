"""sync-invariants — emits InvariantRegistered for each norm in norm_catalog.yaml.

I-SYNC-INVARIANTS-1: every norm present in norm_catalog.yaml MUST have a corresponding
InvariantRegistered event in the EventLog after sdd sync-invariants runs.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import yaml

from sdd.commands._base import CommandHandlerBase, error_event_boundary
from sdd.core.events import DomainEvent, EventLevel, InvariantRegistered
from sdd.infra.paths import norm_catalog_file


@dataclass(frozen=True)
class SyncInvariantsCommand:
    command_id: str
    command_type: str
    payload: Any        # {phase_id, norm_path}
    phase_id: int
    norm_path: str = ""


class SyncInvariantsHandler(CommandHandlerBase):
    """Emits InvariantRegistered for each norm in norm_catalog.yaml (I-SYNC-INVARIANTS-1).

    Idempotency: compute_command_id hashes the payload (phase_id + norm_path).
    Re-running with the same catalog and phase produces the same command_id → EventLog dedup.
    """

    @error_event_boundary(source=__name__)
    def handle(self, cmd: Any) -> list[DomainEvent]:
        norm_path = getattr(cmd, "norm_path", "") or str(norm_catalog_file())
        with open(norm_path, encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)

        norms: list[dict[str, Any]] = raw.get("norms", [])
        phase_id: int = getattr(cmd, "phase_id", 0)
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        events: list[DomainEvent] = []
        for norm in norms:
            norm_id = norm.get("norm_id", "")
            description = norm.get("description", "")
            if not norm_id:
                continue
            events.append(
                InvariantRegistered(
                    event_type=InvariantRegistered.EVENT_TYPE,
                    event_id=str(uuid.uuid4()),
                    appended_at=int(time.time() * 1000),
                    level=EventLevel.L1,
                    event_source="runtime",
                    caused_by_meta_seq=None,
                    invariant_id=norm_id,
                    phase_id=phase_id,
                    statement=description,
                    timestamp=timestamp,
                )
            )
        return events
