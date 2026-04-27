"""SDDError hierarchy — Spec_v1 §4.1."""

from __future__ import annotations


class SDDError(Exception): ...


class ScopeViolation(SDDError): ...


class PhaseGuardError(SDDError): ...


class MissingContext(SDDError): ...


class Inconsistency(SDDError): ...


class VersionMismatch(SDDError): ...


class MissingState(SDDError): ...


class InvalidState(SDDError): ...


class NormViolation(SDDError): ...


class CyclicDependency(SDDError): ...


class ParallelGroupConflict(SDDError): ...


class DoDNotMet(SDDError): ...


class InvalidActor(SDDError): ...


class AlreadyActivated(SDDError): ...


class UnknownEventType(SDDError):
    """Raised by EventReducer in strict_mode=True when event_type is not in
    _EVENT_SCHEMA and not in _KNOWN_NO_HANDLER.
    In default mode (strict_mode=False): NO-OP + logging.warning only.
    """


# Phase 15 error hierarchy — Spec_v15 §0 A-11/A-15/A-16; I-ERROR-1, I-ERROR-CODE-1
class GuardViolationError(SDDError):
    error_code: int = 1


class InvariantViolationError(SDDError):
    error_code: int = 2


class ExecutionError(SDDError):
    error_code: int = 3


class CommitError(SDDError):
    error_code: int = 4


class ProjectionError(SDDError):
    error_code: int = 5


class StaleStateError(SDDError):
    error_code: int = 6


class KernelInvariantError(SDDError):
    error_code: int = 7


class InvalidPhaseSequence(SDDError):
    """Phase activation would skip one or more phases (I-PHASE-SEQ-FORWARD-1)."""


class DependencyNotMet(SDDError):
    """Raised when a task's declared dependency is not yet DONE (BC-32-6, I-CMD-IDEM-2)."""
