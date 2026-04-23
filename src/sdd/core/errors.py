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
