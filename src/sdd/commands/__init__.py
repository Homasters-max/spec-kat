"""commands package — re-exports all Command dataclasses, Handler classes, CommandRunner,
error_event_boundary (Spec_v4 §4.11 acceptance criterion).
"""
from sdd.commands._base import CommandHandlerBase, error_event_boundary
from sdd.commands.record_decision import RecordDecisionCommand, RecordDecisionHandler
from sdd.commands.report_error import ReportErrorCommand, ReportErrorHandler
from sdd.commands.sdd_run import CommandRunner, run_guard_pipeline
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
from sdd.commands.validate_config import ValidateConfigCommand, ValidateConfigHandler
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
    "ValidateConfigCommand",
    "ValidateInvariantsCommand",
    "ValidateTaskCommand",
    # Handlers
    "CheckDoDHandler",
    "CompleteTaskHandler",
    "RecordDecisionHandler",
    "ReportErrorHandler",
    "SyncStateHandler",
    "ValidateConfigHandler",
    "ValidateInvariantsHandler",
    "ValidateTaskHandler",
    # Runner
    "CommandRunner",
    "run_guard_pipeline",
]
