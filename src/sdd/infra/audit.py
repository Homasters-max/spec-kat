"""BC-INFRA SENAR audit log — log_action, AuditEntry, make_entry_id, atomic_write.

Invariants: I-PK-5
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from sdd.infra.paths import audit_log_file

# AuditEntry.event_type MUST NOT equal any V1_L1_EVENT_TYPES member (governance-only, L2).
_AUDIT_EVENT_TYPE = "AuditEntry"


@dataclass(frozen=True)
class AuditEntry:
    """SENAR audit log entry. Governance metadata only — NOT a domain event (L2)."""

    entry_id: str
    event_type: str
    action: str
    actor: str
    context: Mapping[str, Any]
    timestamp_ms: int = field(default_factory=lambda: int(time.time() * 1000))

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "event_type": self.event_type,
            "action": self.action,
            "actor": self.actor,
            "context": dict(self.context),
            "timestamp_ms": self.timestamp_ms,
        }


def make_entry_id(
    action: str,
    actor: str,
    context: Mapping[str, Any],
) -> str:
    """Deterministic SHA-256 of (action, actor, context). Same inputs → same id."""
    canonical = json.dumps(
        {"action": action, "actor": actor, "context": dict(context)},
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def atomic_write(path: str, content: str) -> None:
    """Write content to path atomically via tempfile on same mount + os.replace (I-PK-5)."""
    dir_path = os.path.dirname(os.path.abspath(path))
    os.makedirs(dir_path, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=dir_path)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def log_action(
    action: str,
    actor: str,
    context: Mapping[str, Any] | None = None,
    audit_log_path: str | None = None,
) -> AuditEntry:
    """Append an AuditEntry to the JSONL audit log atomically."""
    if audit_log_path is None:
        audit_log_path = str(audit_log_file())
    ctx: Mapping[str, Any] = context if context is not None else {}
    entry = AuditEntry(
        entry_id=make_entry_id(action, actor, ctx),
        event_type=_AUDIT_EVENT_TYPE,
        action=action,
        actor=actor,
        context=ctx,
        timestamp_ms=int(time.time() * 1000),
    )

    existing = ""
    if os.path.exists(audit_log_path):
        with open(audit_log_path, encoding="utf-8") as f:
            existing = f.read()

    line = json.dumps(entry.to_dict(), sort_keys=True)
    new_content = existing + line + "\n" if existing else line + "\n"
    atomic_write(audit_log_path, new_content)
    return entry


# ─── CLI entry point (Pattern B target) ──────────────────────────────────────

def audit_cli(argv: list[str] | None = None) -> int:
    """CLI: senar_audit.py log --action <type> --actor llm|human --norm <id> --result allowed|rejected
            senar_audit.py tail [--n 10]
    """
    import json
    import sys

    args = argv if argv is not None else sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print("Usage: senar_audit.py log --action <type> --actor llm|human --norm <NORM-ID> "
              "--result allowed|rejected [--context <json>] [--log <path>]")
        print("       senar_audit.py tail [--n 10] [--log <path>]")
        return 0

    cmd = args[0]
    log_path = str(audit_log_file())
    for i, a in enumerate(args[1:], 1):
        if a == "--log" and i + 1 < len(args):
            log_path = args[i + 1]

    if cmd == "log":
        action = actor = result_str = None
        ctx: dict = {}
        i = 1
        while i < len(args):
            a = args[i]
            if a == "--action" and i + 1 < len(args):
                action = args[i + 1]; i += 2
            elif a == "--actor" and i + 1 < len(args):
                actor = args[i + 1]; i += 2
            elif a == "--norm" and i + 1 < len(args):
                ctx["norm_id"] = args[i + 1]; i += 2
            elif a == "--result" and i + 1 < len(args):
                result_str = args[i + 1]; ctx["result"] = result_str; i += 2
            elif a == "--context" and i + 1 < len(args):
                ctx.update(json.loads(args[i + 1])); i += 2
            elif a == "--log":
                i += 2
            else:
                i += 1

        missing = [k for k, v in [("--action", action), ("--actor", actor)] if not v]
        if missing:
            print(json.dumps({"error": f"Missing: {missing}"}))
            return 1

        entry = log_action(action, actor, ctx, log_path)  # type: ignore[arg-type]
        print(json.dumps({"entry_id": entry.entry_id, "timestamp_ms": entry.timestamp_ms,
                          "result": "ok"}))
        return 0

    if cmd == "tail":
        n = 10
        for i, a in enumerate(args[1:], 1):
            if a == "--n" and i + 1 < len(args):
                n = int(args[i + 1])
        if not os.path.exists(log_path):
            print("[]")
            return 0
        with open(log_path, encoding="utf-8") as f:
            lines = [l.strip() for l in f if l.strip()]
        entries = []
        for line in lines[-n:]:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                pass
        print(json.dumps(entries, indent=2))
        return 0

    print(json.dumps({"error": f"Unknown command: {cmd}"}))
    return 1
