"""BootstrapManifest — transient overlay for bootstrap-mode task completion.

I-BOOTSTRAP-1: Bootstrap mode MUST NOT produce EventLog events directly.
               Bootstrap mode MUST record only reconciliation metadata.
               EventLog consistency MUST be restored via explicit reconcile-bootstrap.
I-BOOTSTRAP-2: Bootstrap tasks MUST NOT participate in normal command emission flow.
               Bootstrap tasks MAY only be reconciled via reconcile-bootstrap.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from sdd.infra.paths import bootstrap_manifest_file


def _load(path: str | None = None) -> dict[str, Any]:
    p = Path(path or str(bootstrap_manifest_file()))
    if not p.exists():
        return {}
    with p.open(encoding="utf-8") as f:
        return json.load(f)


def _save(data: dict[str, Any], path: str | None = None) -> None:
    p = Path(path or str(bootstrap_manifest_file()))
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write("\n")
    tmp.replace(p)


def contains(task_id: str, path: str | None = None) -> bool:
    """Return True if task_id is registered in the bootstrap manifest (PRE-RESOLVED).

    Used by sdd complete noop fast-path (I-BOOTSTRAP-2): bootstrap tasks skip event emission.
    """
    return task_id in _load(path)


def add_entry(task_id: str, phase: int, path: str | None = None) -> None:
    """Record task_id as bootstrap-completed. Idempotent."""
    data = _load(path)
    if task_id not in data:
        data[task_id] = {
            "status": "DONE",
            "source": "bootstrap",
            "phase": phase,
            "timestamp": int(time.time()),
            "reconciled": False,
        }
        _save(data, path)


def mark_reconciled(task_id: str, path: str | None = None) -> None:
    """Mark a bootstrap entry as reconciled after EventLog backfill."""
    data = _load(path)
    if task_id in data:
        data[task_id]["reconciled"] = True
        _save(data, path)


def list_unreconciled(path: str | None = None) -> list[dict[str, Any]]:
    """Return all unreconciled bootstrap entries for reconcile-bootstrap pass."""
    data = _load(path)
    return [
        {"task_id": tid, **entry}
        for tid, entry in data.items()
        if not entry.get("reconciled", False)
    ]
