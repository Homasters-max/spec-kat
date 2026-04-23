"""Public BC-CORE API — Spec_v1 §2."""

from sdd.core.errors import SDDError
from sdd.core.events import (
    CommandEvent,
    DomainEvent,
    ErrorEvent,
    EventLevel,
    classify_event_level,
)
from sdd.core.types import CommandHandler

__all__ = [
    "SDDError",
    "DomainEvent",
    "ErrorEvent",
    "CommandEvent",
    "EventLevel",
    "CommandHandler",
    "classify_event_level",
]
