"""CommandHandlerBase + error_event_boundary — Spec_v4 §4.1, §4.2.

Invariants: I-ERR-1, I-CMD-2, I-CMD-2b, I-CMD-3
"""
from __future__ import annotations

import dataclasses
import functools
import hashlib
import logging
import time
import uuid
from collections.abc import Callable, Mapping
from typing import Any

from sdd.core.errors import SDDError
from sdd.core.events import DomainEvent, ErrorEvent, EventLevel
from sdd.core.types import Command
from sdd.infra.event_log import (
    canonical_json,
    exists_command,
    exists_semantic,
    get_error_count,
)

_fallback_log = logging.getLogger(__name__)


class RecoverableError(SDDError):
    """Marker base class for exceptions that may safely be retried."""


def command_payload_hash(command: Command) -> str:
    """sha256 of canonical_json(command fields ∖ command_id) (I-CMD-2b)."""
    d: dict[str, Any] = {}
    for field in dataclasses.fields(command):
        if field.name == "command_id":
            continue
        val = getattr(command, field.name)
        if isinstance(val, Mapping):
            val = dict(val)
        d[field.name] = val
    return hashlib.sha256(canonical_json(d).encode()).hexdigest()


def error_event_boundary(source: str) -> Callable:
    """Decorator factory for CommandHandler.handle() methods (Spec_v5 §4.4).

    On any exception raised by the decorated method:
      1. Queries get_error_count(command.command_id) for retry_count (best-effort, non-atomic)
         If get_error_count raises: logs to fallback_log, sets retry_count=0 (I-CMD-3)
      2. Builds ErrorEvent and attaches to exc._sdd_error_events — NO sdd_append call (I-ES-1)
      3. Re-raises original exception — never suppresses (I-CMD-3)
      CommandRunner catches and appends via EventStore.append (sole write path).

    Idempotency check runs BEFORE try/except (I-CMD-2b).
    """
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(self: CommandHandlerBase, command: Command) -> list[DomainEvent]:
            # Idempotency runs BEFORE try/except — idempotent returns skip boundary (I-CMD-2b)
            if self._check_idempotent(command):
                return []
            try:
                return fn(self, command)
            except Exception as exc:
                try:
                    retry_count = get_error_count(self._db_path, command_id=command.command_id)
                except Exception as count_exc:
                    _fallback_log.error(
                        "error_event_boundary get_error_count failed: %s; original: %s",
                        count_exc,
                        exc,
                    )
                    retry_count = 0
                error_event = ErrorEvent(
                    event_type="ErrorEvent",
                    event_id=str(uuid.uuid4()),
                    appended_at=int(time.time() * 1000),
                    level=EventLevel.L2,
                    event_source="runtime",
                    caused_by_meta_seq=None,
                    error_type=type(exc).__name__,
                    source=source,
                    recoverable=isinstance(exc, RecoverableError),
                    retry_count=retry_count,
                    context={"message": str(exc)},
                )
                exc._sdd_error_events = [error_event]
                raise
        return wrapper
    return decorator


class CommandHandlerBase:
    """Base class for all command handlers (Spec_v4 §4.2).

    Holds only db_path — no EventStore reference.
    Concrete handlers apply @error_event_boundary(source=__name__) to handle().
    """

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    def _check_idempotent(self, command: Command) -> bool:
        """Return True if command already processed (I-CMD-1, I-CMD-2b).

        Two-level check (True if EITHER matches):
          1. Structural:  exists_command(command_id) — exact replay guard
          2. Semantic:    exists_semantic(command_type, task_id, phase_id, payload_hash)
                          — prevents duplicate effects even with a new command_id
        """
        if exists_command(self._db_path, command_id=command.command_id):
            return True
        return exists_semantic(
            self._db_path,
            command_type=type(command).__name__,
            task_id=getattr(command, "task_id", None),
            phase_id=getattr(command, "phase_id", None),
            payload_hash=command_payload_hash(command),
        )
