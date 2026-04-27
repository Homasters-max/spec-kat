"""ReportErrorHandler — Spec_v4 §4.9.

Invariants: I-CMD-1, I-ERR-1
"""
from __future__ import annotations

import argparse
import sys
import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from sdd.commands._base import CommandHandlerBase, error_event_boundary
from sdd.core.errors import SDDError
from sdd.core.events import DomainEvent, ErrorEvent, classify_event_level
from sdd.core.payloads import _unpack_payload, build_command
from sdd.infra.event_log import EventLog
from sdd.infra.paths import event_store_file

# ---------------------------------------------------------------------------
# Legacy command envelope shim (I-CMD-ENV-1)
# NOT a Command subclass — standalone dataclass whose __post_init__
# auto-populates payload so handlers can use _unpack_payload uniformly.
# Name preserved for backward-compatible imports.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ReportErrorCommand:
    command_id:   str
    command_type: str
    payload:      Mapping[str, Any]
    error_type:   str
    message:      str
    source:       str
    recoverable:  bool

    def __post_init__(self) -> None:
        if not self.payload:
            object.__setattr__(self, "payload", {
                "error_type":  self.error_type,
                "message":     self.message,
                "source":      self.source,
                "recoverable": self.recoverable,
            })


@dataclass(frozen=True)
class _ErrorEventWithCmd(ErrorEvent):
    command_id: str


class ReportErrorHandler(CommandHandlerBase):
    """Manually emit an ErrorEvent — for structured error reporting outside
    automatic error_event_boundary (e.g., report_error.py tool invocation).
    Sets retry_count=0 always (manual reports are not retries).
    """

    @error_event_boundary(source=__name__)
    def handle(self, command: Any) -> list[DomainEvent]:
        if self._check_idempotent(command):
            return []

        p = _unpack_payload("ReportError", command.payload)
        now_ms = int(time.time() * 1000)

        event = _ErrorEventWithCmd(
            event_type="ErrorEvent",
            event_id=str(uuid.uuid4()),
            appended_at=now_ms,
            level=classify_event_level("ErrorEvent"),
            event_source="runtime",
            caused_by_meta_seq=None,
            error_type=p.error_type,
            source=p.source,
            recoverable=p.recoverable,
            retry_count=0,
            context=(("message", p.message),),
            command_id=command.command_id,
        )

        EventLog(self._db_path).append([event], source=__name__)
        return [event]


# ---------------------------------------------------------------------------
# CLI entry point (I-CLI-2)
# ---------------------------------------------------------------------------

def main(args: list[str] | None = None) -> int:
    if args is None:
        args = sys.argv[1:]
    parser = argparse.ArgumentParser(prog="report-error")
    parser.add_argument("--type", required=True, dest="error_type")
    parser.add_argument("--message", required=True)
    parser.add_argument("--source", default="cli")
    parser.add_argument("--recoverable", action="store_true")
    parser.add_argument("--db", default=str(event_store_file()))
    parsed = parser.parse_args(args)
    try:
        ReportErrorHandler(parsed.db).handle(build_command(
            "ReportError",
            error_type=parsed.error_type,
            message=parsed.message,
            source=parsed.source,
            recoverable=parsed.recoverable,
        ))
        return 0
    except SDDError:
        return 1
    except Exception:
        return 2
