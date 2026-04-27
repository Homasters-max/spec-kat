"""PhaseOrder — pure view module for logical phase ordering.

BC-41-F: единственная точка интерпретации logical_type / anchor_phase_id.
I-LOGICAL-META-1: guards и reducer НЕ вызывают этот модуль.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass

from sdd.domain.state.reducer import FrozenPhaseSnapshot


@dataclass(frozen=True)
class PhaseOrderEntry:
    phase_id:        int
    logical_type:    str | None
    anchor_phase_id: int | None


class PhaseOrder:
    @staticmethod
    def sort(snapshots: Iterable[FrozenPhaseSnapshot]) -> list[PhaseOrderEntry]:
        """Pure view: logical ordering of phases.

        Sort rules:
          - None        → execution order (phase_id)
          - "backfill"  → before anchor_phase_id
          - "patch"     → after anchor_phase_id
          - unknown str → fallback to execution order + logging.warning
          - anchor not in snapshots → fallback to execution order + logging.warning
        """
        snaps = list(snapshots)
        known_ids = {s.phase_id for s in snaps}

        def _sort_key(snap: FrozenPhaseSnapshot) -> tuple[int, int, int]:
            lt = snap.logical_type
            ap = snap.anchor_phase_id

            if lt is None:
                return (snap.phase_id, 1, snap.phase_id)

            if lt not in ("backfill", "patch"):
                logging.warning(
                    "PhaseOrder: unknown logical_type=%r for phase_id=%r — fallback to execution order",
                    lt, snap.phase_id,
                )
                return (snap.phase_id, 1, snap.phase_id)

            if ap is None or ap not in known_ids:
                logging.warning(
                    "PhaseOrder: anchor_phase_id=%r for phase_id=%r not in snapshots — fallback to execution order",
                    ap, snap.phase_id,
                )
                return (snap.phase_id, 1, snap.phase_id)

            if lt == "backfill":
                return (ap, 0, snap.phase_id)
            # lt == "patch"
            return (ap, 2, snap.phase_id)

        sorted_snaps = sorted(snaps, key=_sort_key)
        return [
            PhaseOrderEntry(
                phase_id=s.phase_id,
                logical_type=s.logical_type,
                anchor_phase_id=s.anchor_phase_id,
            )
            for s in sorted_snaps
        ]
