"""commands package — re-exports all Command dataclasses, Handler classes,
error_event_boundary (Spec_v4 §4.11 acceptance criterion).
"""
from sdd.commands._base import CommandHandlerBase, error_event_boundary
from sdd.commands.record_decision import RecordDecisionCommand, RecordDecisionHandler
from sdd.commands.report_error import ReportErrorCommand, ReportErrorHandler
from sdd.commands.update_state import (
    CheckDoDCommand,
    CheckDoDHandler,
    CompleteTaskCommand,
    CompleteTaskHandler,
    SyncStateCommand,
    SyncStateHandler,
    ValidateTaskCommand,
    ValidateTaskHandler,
)
from sdd.commands.validate_config import ConfigValidationError, validate_project_config
from sdd.commands.validate_invariants import ValidateInvariantsCommand, ValidateInvariantsHandler

__all__ = [
    # Base
    "CommandHandlerBase",
    "error_event_boundary",
    # Commands
    "CheckDoDCommand",
    "CompleteTaskCommand",
    "RecordDecisionCommand",
    "ReportErrorCommand",
    "SyncStateCommand",
    "ValidateInvariantsCommand",
    "ValidateTaskCommand",
    # Handlers
    "CheckDoDHandler",
    "CompleteTaskHandler",
    "RecordDecisionHandler",
    "ReportErrorHandler",
    "SyncStateHandler",
    "ValidateInvariantsHandler",
    "ValidateTaskHandler",
    # validate_config
    "ConfigValidationError",
    "validate_project_config",
]
